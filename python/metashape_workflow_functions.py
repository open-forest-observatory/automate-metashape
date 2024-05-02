# Derek Young and Alex Mandel
# University of California, Davis
# 2021

#### Import libraries

# import the fuctionality we need to make time stamps to measure performance
import time
import datetime
import platform
import os
import glob
import re
import yaml

### import the Metashape functionality
import Metashape


#### Helper functions and globals

# Set the log file name-value separator
# Chose ; as : is in timestamps
# TODO: Consider moving log to json/yaml formatting using a dict
sep = "; "


def stamp_time():
    """
    Format the timestamps as needed
    """
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M")
    return stamp


def diff_time(t2, t1):
    """
    Give a end and start time, subtract, and round
    """
    total = str(round(t2 - t1, 1))
    return total


# Used by add_gcps function
def get_marker(chunk, label):
    for marker in chunk.markers:
        if marker.label == label:
            return marker
    return None


# Used by add_gcps function
def get_camera(chunk, label):
    for camera in chunk.cameras:
        if camera.label.lower() == label.lower():
            return camera
    return None


#### Functions for each major step in Metashape


def project_setup(cfg, config_file):
    """
    Create output and project paths, if they don't exist
    Define a project ID based on specified project name and timestamp
    Define a project filename and a log filename
    Create the project
    Start a log file
    """

    # Make project directories (necessary even if loading an existing project because this workflow saves a new project based on the old one, leaving the old one intact
    if not os.path.exists(cfg["output_path"]):
        os.makedirs(cfg["output_path"])
    if not os.path.exists(cfg["project_path"]):
        os.makedirs(cfg["project_path"])

    ### Set a filename template for project files and output files based on the 'run_name' key of the config YML
    ## BUT if the value for run_name is "from_config_filename", then use the config filename for the run name.

    run_name = cfg["run_name"]

    if run_name == "from_config_filename" or run_name ==  "":
        file_basename = os.path.basename(config_file)  # extracts file base name from path
        run_name, _ = os.path.splitext(file_basename)  # removes extension

    ## Project file example to make: "projectID_YYYYMMDDtHHMM-jobID.psx"
    timestamp = stamp_time()
    run_id = "_".join([run_name, timestamp])
    # TODO: If there is a slurm JobID, append to time (separated with "-", not "_"). This will keep jobs initiated in the same minute distinct

    project_file = os.path.join(cfg["project_path"], ".".join([run_id, "psx"]))
    log_file = os.path.join(cfg["output_path"], ".".join([run_id + "_log", "txt"]))

    """
    Create a doc and a chunk
    """

    # create a handle to the Metashape object
    doc = Metashape.Document()  # When running via Metashape, can use: doc = Metashape.app.document

    # If specified, open existing project
    if cfg["load_project"] != "":
        doc.open(cfg["load_project"])
    else:
        # Initialize a chunk, set its CRS as specified
        chunk = doc.addChunk()
        chunk.crs = Metashape.CoordinateSystem(cfg["project_crs"])
        chunk.marker_crs = Metashape.CoordinateSystem(cfg["addGCPs"]["gcp_crs"])

    # Save doc doc as new project (even if we opened an existing project, save as a separate one so the existing project remains accessible in its original state)
    doc.save(project_file)

    """
    Log specs except for GPU
    """

    # log Metashape version, CPU specs, time, and project location to results file
    # open the results file
    # TODO: records the Slurm values for actual cpus and ram allocated
    # https://slurm.schedmd.com/sbatch.html#lbAI
    with open(log_file, "a") as file:

        # write a line with the Metashape version
        file.write(sep.join(["Project", run_id]) + "\n")
        file.write(
            sep.join(["Agisoft Metashape Professional Version", Metashape.app.version]) + "\n"
        )
        # write a line with the date and time
        file.write(sep.join(["Processing started", stamp_time()]) + "\n")
        # write a line with CPU info - if possible, improve the way the CPU info is found / recorded
        file.write(sep.join(["Node", platform.node()]) + "\n")
        file.write(sep.join(["CPU", platform.processor()]) + "\n")
        # write two lines with GPU info: count and model names - this takes multiple steps to make it look clean in the end

    return doc, log_file, run_id


def enable_and_log_gpu(log_file, cfg):
    """
    Enables GPU and logs GPU specs
    """

    gpustringraw = str(Metashape.app.enumGPUDevices())
    gpucount = gpustringraw.count("name': '")
    gpustring = ""
    currentgpu = 1
    while gpucount >= currentgpu:
        if gpustring != "":
            gpustring = gpustring + ", "
        gpustring = gpustring + gpustringraw.split("name': '")[currentgpu].split("',")[0]
        currentgpu = currentgpu + 1
    # gpustring = gpustringraw.split("name': '")[1].split("',")[0]
    gpu_mask = Metashape.app.gpu_mask

    with open(log_file, "a") as file:
        file.write(sep.join(["Number of GPUs Found", str(gpucount)]) + "\n")
        file.write(sep.join(["GPU Model", gpustring]) + "\n")
        file.write(sep.join(["GPU Mask", str(gpu_mask)]) + "\n")

        # If a GPU exists but is not enabled, enable the 1st one
        if (gpucount > 0) and (gpu_mask == 0):
            Metashape.app.gpu_mask = 1
            gpu_mask = Metashape.app.gpu_mask
            file.write(sep.join(["GPU Mask Enabled", str(gpu_mask)]) + "\n")

        # This writes down all the GPU devices available
        # file.write('GPU(s): '+str(Metashape.app.enumGPUDevices())+'\n')

    # set Metashape to *not* use the CPU during GPU steps (appears to be standard wisdom)
    Metashape.app.cpu_enable = False

    # Disable CUDA if specified
    if not cfg["use_cuda"]:
        Metashape.app.settings.setValue("main/gpu_enable_cuda", "0")

    # Set GPU multiplier to value specified (2 is default)
    Metashape.app.settings.setValue("main/depth_max_gpu_multiplier", cfg["gpu_multiplier"])

    return True


def add_photos(doc, cfg):
    """
    Add photos to project and change their labels to include their containing folder
    """
    
    photo_paths = cfg["photo_path"]
    
    # If it's a single string (i.e. one directory), make it a list of one string so we can iterate
    # over it the same as if it were a list of strings
    if (isinstance(photo_paths, str)):
        photo_paths = [photo_paths]
    
    for photo_path in photo_paths:
        
        grp = doc.chunk.addCameraGroup()

        ## Get paths to all the project photos
        a = glob.iglob(
            os.path.join(photo_path, "**", "*.*"), recursive=True
        )  # (([jJ][pP][gG])|([tT][iI][fF]))
        b = [path for path in a]
        photo_files = [
            x
            for x in b
            if (re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)", x) and (not re.search("dem_usgs.tif", x)))
        ]

        ## Add them
        if cfg["multispectral"]:
            doc.chunk.addPhotos(photo_files, layout=Metashape.MultiplaneLayout, group = grp)
        else:
            doc.chunk.addPhotos(photo_files, group = grp)
            
    ## Need to change the label on each camera so that it includes the containing folder(s)
    for camera in doc.chunk.cameras:
        path = camera.photo.path
        # remove the base imagery dir from this string
        rel_path = path.replace(cfg["photo_path"], "")
        # if it starts with a '/', remove it
        newlabel = re.sub("^/", "", rel_path)
        camera.label = newlabel
    
    if cfg["separate_calibration_per_path"] :
        # Assign a different (new) sensor (i.e. independent calibration) to each group of photos
        for grp in doc.chunk.camera_groups:

            # Get the template for the sensor from the first photo in the group
            for cam in doc.chunk.cameras:
                if cam.group == grp:
                    sensor = cam.sensor
                    break

            doc.chunk.addSensor(doc.chunk.cameras[0].sensor)
            sensor = doc.chunk.sensors[-1]
            
            for cam in doc.chunk.cameras:
                if cam.group == grp:
                    cam.sensor = sensor
                    
        # Remove the first (deafult) sensor, which should no longer be assigned to any photos
        doc.chunk.remove(doc.chunk.sensors[0])

    ## If specified, change the accuracy of the cameras to match the RTK flag (RTK fix if flag = 50, otherwise no fix
    if cfg["use_rtk"]:
        for cam in doc.chunk.cameras:
            rtkflag = cam.photo.meta["DJI/RtkFlag"]
            if rtkflag == "50":
                cam.reference.location_accuracy = Metashape.Vector(
                    [cfg["fix_accuracy"], cfg["fix_accuracy"], cfg["fix_accuracy"]]
                )
                cam.reference.accuracy = Metashape.Vector(
                    [cfg["fix_accuracy"], cfg["fix_accuracy"], cfg["fix_accuracy"]]
                )
            else:
                cam.reference.location_accuracy = Metashape.Vector(
                    [
                        cfg["nofix_accuracy"],
                        cfg["nofix_accuracy"],
                        cfg["nofix_accuracy"],
                    ]
                )
                cam.reference.accuracy = Metashape.Vector(
                    [
                        cfg["nofix_accuracy"],
                        cfg["nofix_accuracy"],
                        cfg["nofix_accuracy"],
                    ]
                )

    doc.save()

    return True


def calibrate_reflectance(doc, cfg):
    # TODO: Handle failure to find panels, or mulitple panel images by returning error to user.
    doc.chunk.locateReflectancePanels()
    doc.chunk.loadReflectancePanelCalibration(
        os.path.join(
            cfg["photo_path"],
            "calibration",
            cfg["calibrateReflectance"]["panel_filename"],
        )
    )
    # doc.chunk.calibrateReflectance(use_reflectance_panels=True,use_sun_sensor=True)
    doc.chunk.calibrateReflectance(
        use_reflectance_panels=cfg["calibrateReflectance"]["use_reflectance_panels"],
        use_sun_sensor=cfg["calibrateReflectance"]["use_sun_sensor"],
    )
    doc.save()

    return True


def add_gcps(doc, cfg):
    """
    Add GCPs (GCP coordinates and the locations of GCPs in individual photos.
    See the helper script (and the comments therein) for details on how to prepare the data needed by this function: R/prep_gcps.R
    """

    ## Tag specific pixels in specific images where GCPs are located
    path = os.path.join(cfg["photo_path"], "gcps", "prepared", "gcp_imagecoords_table.csv")
    file = open(path)
    content = file.read().splitlines()

    for line in content:
        marker_label, camera_label, x_proj, y_proj = line.split(",")
        if marker_label[0] == '"':  # if it's in quotes (from saving CSV in Excel), remove quotes
            marker_label = marker_label[1:-1]  # need to get it out of the two pairs of quotes
        if camera_label[0] == '"':  # if it's in quotes (from saving CSV in Excel), remove quotes
            camera_label = camera_label[1:-1]

        marker = get_marker(doc.chunk, marker_label)
        if not marker:
            marker = doc.chunk.addMarker()
            marker.label = marker_label

        camera = get_camera(doc.chunk, camera_label)
        if not camera:
            print(camera_label + " camera not found in project")
            continue

        marker.projections[camera] = Metashape.Marker.Projection(
            (float(x_proj), float(y_proj)), True
        )

    ## Assign real-world coordinates to each GCP
    path = os.path.join(cfg["photo_path"], "gcps", "prepared", "gcp_table.csv")

    file = open(path)
    content = file.read().splitlines()

    for line in content:
        marker_label, world_x, world_y, world_z = line.split(",")
        if marker_label[0] == '"':  # if it's in quotes (from saving CSV in Excel), remove quotes
            marker_label = marker_label[1:-1]  # need to get it out of the two pairs of quotes

        marker = get_marker(doc.chunk, marker_label)
        if not marker:
            marker = doc.chunk.addMarker()
            marker.label = marker_label

        marker.reference.location = (float(world_x), float(world_y), float(world_z))
        marker.reference.accuracy = (
            cfg["addGCPs"]["marker_location_accuracy"],
            cfg["addGCPs"]["marker_location_accuracy"],
            cfg["addGCPs"]["marker_location_accuracy"],
        )

    doc.chunk.marker_location_accuracy = (
        cfg["addGCPs"]["marker_location_accuracy"],
        cfg["addGCPs"]["marker_location_accuracy"],
        cfg["addGCPs"]["marker_location_accuracy"],
    )
    doc.chunk.marker_projection_accuracy = cfg["addGCPs"]["marker_projection_accuracy"]

    doc.save()

    return True


def export_cameras(doc, run_id, cfg):
    output_file = os.path.join(cfg["output_path"], run_id + "_cameras.xml")
    # Defaults to xml format, which is the only one we've used so far
    doc.chunk.exportCameras(path=output_file)


def align_photos(doc, log_file, run_id, cfg):
    """
    Match photos, align cameras, optimize cameras
    """

    #### Align photos

    # get a beginning time stamp
    timer1a = time.time()

    # Align cameras
    doc.chunk.matchPhotos(
        downscale=cfg["alignPhotos"]["downscale"],
        subdivide_task=cfg["subdivide_task"],
        keep_keypoints=cfg["alignPhotos"]["keep_keypoints"],
        generic_preselection=cfg["alignPhotos"]["generic_preselection"],
        reference_preselection=cfg["alignPhotos"]["reference_preselection"],
        reference_preselection_mode=cfg["alignPhotos"]["reference_preselection_mode"],
    )
    doc.chunk.alignCameras(
        adaptive_fitting=cfg["alignPhotos"]["adaptive_fitting"],
        subdivide_task=cfg["subdivide_task"],
        reset_alignment=cfg["alignPhotos"]["reset_alignment"],
    )
    doc.save()

    # get an ending time stamp
    timer1b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time1 = diff_time(timer1b, timer1a)

    # optionally export
    if cfg["alignPhotos"]["export"]:
        export_cameras(doc, run_id, cfg)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["Align Photos", time1]) + "\n")

    return True


def reset_region(doc):
    """
    Reset the region and make it much larger than the points; necessary because if points go outside the region, they get clipped when saving
    """

    doc.chunk.resetRegion()
    region_dims = doc.chunk.region.size
    region_dims[2] *= 3
    doc.chunk.region.size = region_dims

    return True


def optimize_cameras(doc, log_file, run_id, cfg):
    """
    Optimize cameras
    """

    # get a beginning time stamp
    timer1a = time.time()

    # Disable camera locations as reference if specified in YML
    if cfg["addGCPs"]["enabled"] and cfg["addGCPs"]["optimize_w_gcps_only"]:
        n_cameras = len(doc.chunk.cameras)
        for i in range(0, n_cameras):
            doc.chunk.cameras[i].reference.enabled = False

    # Currently only optimizes the default parameters, which is not all possible parameters
    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    # get an ending time stamp
    timer1b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time1 = diff_time(timer1b, timer1a)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["Optimize cameras", time1]) + "\n")

    doc.save()

    # optionally export, note this would override the export from align_cameras
    if cfg["optimizeCameras"]["export"]:
        export_cameras(doc, run_id, cfg)

    return True


def filter_points_usgs_part1(doc, log_file, cfg):

    # get a beginning time stamp
    timer1a = time.time()

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    rec_thresh_percent = cfg["filterPointsUSGS"]["rec_thresh_percent"]
    rec_thresh_absolute = cfg["filterPointsUSGS"]["rec_thresh_absolute"]
    proj_thresh_percent = cfg["filterPointsUSGS"]["proj_thresh_percent"]
    proj_thresh_absolute = cfg["filterPointsUSGS"]["proj_thresh_absolute"]
    reproj_thresh_percent = cfg["filterPointsUSGS"]["reproj_thresh_percent"]
    reproj_thresh_absolute = cfg["filterPointsUSGS"]["reproj_thresh_absolute"]

    fltr = Metashape.TiePoints.Filter()
    fltr.init(doc.chunk, Metashape.TiePoints.Filter.ReconstructionUncertainty)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1 - rec_thresh_percent / 100))]
    if thresh < rec_thresh_absolute:
        thresh = rec_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    fltr = Metashape.TiePoints.Filter()
    fltr.init(doc.chunk, Metashape.TiePoints.Filter.ProjectionAccuracy)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1 - proj_thresh_percent / 100))]
    if thresh < proj_thresh_absolute:
        thresh = proj_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    fltr = Metashape.TiePoints.Filter()
    fltr.init(doc.chunk, Metashape.TiePoints.Filter.ReprojectionError)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
    if thresh < reproj_thresh_absolute:
        thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    # get an ending time stamp
    timer1b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time1 = diff_time(timer1b, timer1a)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["USGS filter points part 1", time1]) + "\n")

    doc.save()


def filter_points_usgs_part2(doc, log_file, cfg):

    # get a beginning time stamp
    timer1a = time.time()

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    reproj_thresh_percent = cfg["filterPointsUSGS"]["reproj_thresh_percent"]
    reproj_thresh_absolute = cfg["filterPointsUSGS"]["reproj_thresh_absolute"]

    fltr = Metashape.TiePoints.Filter()
    fltr.init(doc.chunk, Metashape.TiePoints.Filter.ReprojectionError)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
    if thresh < reproj_thresh_absolute:
        thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    # get an ending time stamp
    timer1b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time1 = diff_time(timer1b, timer1a)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["USGS filter points part 2", time1]) + "\n")

    doc.save()


def classify_ground_points(doc, log_file, run_id, cfg):

    # get a beginning time stamp for the next step
    timer_a = time.time()

    doc.chunk.point_cloud.classifyGroundPoints(
        max_angle=cfg["classifyGroundPoints"]["max_angle"],
        max_distance=cfg["classifyGroundPoints"]["max_distance"],
        cell_size=cfg["classifyGroundPoints"]["cell_size"],
    )

    # get an ending time stamp for the previous step
    timer_b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time_tot = diff_time(timer_b, timer_a)

    doc.save()

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["Classify Ground Points", time_tot]) + "\n")


def build_depth_maps(doc, log_file, cfg):
    ### Build depth maps

    # get a beginning time stamp for the next step
    timer2a = time.time()

    # build depth maps only instead of also building the point cloud ##?? what does
    doc.chunk.buildDepthMaps(
        downscale=cfg["buildDepthMaps"]["downscale"],
        filter_mode=cfg["buildDepthMaps"]["filter_mode"],
        reuse_depth=cfg["buildDepthMaps"]["reuse_depth"],
        max_neighbors=cfg["buildDepthMaps"]["max_neighbors"],
        subdivide_task=cfg["subdivide_task"],
    )

    # get an ending time stamp for the previous step
    timer2b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time2 = diff_time(timer2b, timer2a)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["Build Depth Maps", time2]) + "\n")

    doc.save()


def build_point_cloud(doc, log_file, run_id, cfg):
    """
    Build point cloud
    """

    ### Build point cloud

    # get a beginning time stamp for the next step
    timer3a = time.time()

    # build point cloud
    doc.chunk.buildPointCloud(
        max_neighbors=cfg["buildPointCloud"]["max_neighbors"],
        keep_depth=cfg["buildPointCloud"]["keep_depth"],
        subdivide_task=cfg["subdivide_task"],
        point_colors=True,
    )

    # get an ending time stamp for the previous step
    timer3b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time3 = diff_time(timer3b, timer3a)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["Build Point Cloud", time3]) + "\n")

    doc.save()

    # classify ground points if specified
    if cfg["buildPointCloud"]["classify_ground_points"]:
        classify_ground_points(doc, log_file, run_id, cfg)

    ### Export points

    if cfg["buildPointCloud"]["export"]:

        output_file = os.path.join(cfg["output_path"], run_id + "_points.laz")

        if cfg["buildPointCloud"]["classes"] == "ALL":
            # call without classes argument (Metashape then defaults to all classes)
            doc.chunk.exportPointCloud(
                path=output_file,
                source_data=Metashape.PointCloudData,
                format=Metashape.PointCloudFormatLAS,
                crs=Metashape.CoordinateSystem(cfg["project_crs"]),
                subdivide_task=cfg["subdivide_task"],
            )
        else:
            # call with classes argument
            doc.chunk.exportPointCloud(
                path=output_file,
                source_data=Metashape.PointCloudData,
                format=Metashape.PointCloudFormatLAZ,
                crs=Metashape.CoordinateSystem(cfg["project_crs"]),
                clases=cfg["buildPointCloud"]["classes"],
                subdivide_task=cfg["subdivide_task"],
            )

    return True


def build_model(doc, log_file, run_id, cfg):
    """
    Build and export the model
    """

    start_time = time.time()
    # Build the mesh
    doc.chunk.buildModel(
        surface_type=Metashape.Arbitrary,
        interpolation=Metashape.EnabledInterpolation,
        face_count=cfg["buildModel"]["face_count"],
        face_count_custom=cfg["buildModel"][
            "face_count_custom"
        ],  # Only used if face_count is custom
        source_data=Metashape.DepthMapsData,
    )

    time_taken = diff_time(time.time(), start_time)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["Build Model", time_taken]) + "\n")

    # Save the model
    doc.save()

    if cfg["buildModel"]["export_georeferenced"]:
        output_file = os.path.join(
            cfg["output_path"],
            run_id + "_model_georeferenced." + cfg["buildModel"]["export_extension"],
        )
        doc.chunk.exportModel(path=output_file)

    if cfg["buildModel"]["export_local"]:
        # Wipe the CRS and transform so it aligns with the cameras
        # The approach was recommended here: https://www.agisoft.com/forum/index.php?topic=8210.0
        old_crs = doc.chunk.crs
        old_transform_matrix = doc.chunk.transform.matrix
        # Wipe the transform
        doc.chunk.crs = None
        doc.chunk.transform.matrix = None

        # Export the transform
        if cfg["buildModel"]["export_transform"]:
            output_file = os.path.join(
                cfg["output_path"],
                run_id + "_local_model_transform.csv",
            )

            with open(output_file, "w") as fileh:
                # This is a row-major representation
                transform_tuple = tuple(old_transform_matrix)
                # Write each row in the the transform
                for i in range(4):
                    fileh.write(", ".join(str(transform_tuple[i * 4 : (i + 1) * 4])))

        # Export the model
        output_file = os.path.join(
            cfg["output_path"],
            run_id + "_model_local." + cfg["buildModel"]["export_extension"],
        )
        doc.chunk.exportModel(path=output_file)

        # Reset CRS and transform
        doc.chunk.crs = old_crs
        doc.chunk.transform.matrix = old_transform_matrix

        doc.open(doc.path)

    return True


def build_dem_orthomosaic(doc, log_file, run_id, cfg):
    """
    Build end export DEM
    """

    # classify ground points if specified
    if cfg["buildDem"]["classify_ground_points"]:
        classify_ground_points(doc, log_file, run_id, cfg)

    if (cfg["buildDem"]["enabled"]):
        # prepping params for buildDem
        projection = Metashape.OrthoProjection()
        projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])

        # prepping params for export
        compression = Metashape.ImageCompression()
        compression.tiff_big = cfg["buildDem"]["tiff_big"]
        compression.tiff_tiled = cfg["buildDem"]["tiff_tiled"]
        compression.tiff_overviews = cfg["buildDem"]["tiff_overviews"]

        if ("DSM-ptcloud" in cfg["buildDem"]["surface"]):
            start_time = time.time()

            # call without point classes argument (Metashape then defaults to all classes)
            doc.chunk.buildDem(
                source_data=Metashape.PointCloudData,
                subdivide_task=cfg["subdivide_task"],
                projection=projection,
                resolution=cfg["buildDem"]["resolution"]
            )

            time_taken = diff_time(time.time(), start_time)

            # record results to file
            with open(log_file, "a") as file:
                file.write(sep.join(["Build DSM-ptcloud", time_taken]) + "\n")

            output_file = os.path.join(cfg["output_path"], run_id + "_dsm-ptcloud.tif")
            if cfg["buildDem"]["export"]:
                doc.chunk.exportRaster(
                    path=output_file,
                    projection=projection,
                    nodata_value=cfg["buildDem"]["nodata"],
                    source_data=Metashape.ElevationData,
                    image_compression=compression,
                )
                if cfg["buildOrthomosaic"]["enabled"] and "DSM-ptcloud" in cfg["buildOrthomosaic"]["surface"]:
                    build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending="dsm-ptcloud")
        if ("DTM-ptcloud" in cfg["buildDem"]["surface"]):

            start_time = time.time()

            # call with point classes argument to specify ground points only
            doc.chunk.buildDem(
                source_data=Metashape.PointCloudData,
                classes=Metashape.PointClass.Ground,
                subdivide_task=cfg["subdivide_task"],
                projection=projection,
                resolution=cfg["buildDem"]["resolution"]
            )

            time_taken = diff_time(time.time(), start_time)

            # record results to file
            with open(log_file, "a") as file:
                file.write(sep.join(["Build DTM-ptcloud", time_taken]) + "\n")

            output_file = os.path.join(cfg["output_path"], run_id + "_dtm-ptcloud.tif")
            if cfg["buildDem"]["export"]:
                doc.chunk.exportRaster(
                    path=output_file,
                    projection=projection,
                    nodata_value=cfg["buildDem"]["nodata"],
                    source_data=Metashape.ElevationData,
                    image_compression=compression,
                )
                if cfg["buildOrthomosaic"]["enabled"] and "DTM-ptcloud" in cfg["buildOrthomosaic"]["surface"]:
                    build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending="dtm-ptcloud")

        if ("DSM-mesh" in cfg["buildDem"]["surface"]):

            start_time = time.time()

            doc.chunk.buildDem(
                source_data=Metashape.ModelData,
                subdivide_task=cfg["subdivide_task"],
                projection=projection,
                resolution=cfg["buildDem"]["resolution"]
            )

            time_taken = diff_time(time.time(), start_time)

            # record results to file
            with open(log_file, "a") as file:
                file.write(sep.join(["Build DSM-mesh", time_taken]) + "\n")

            output_file = os.path.join(cfg["output_path"], run_id + "_dsm-mesh.tif")
            if cfg["buildDem"]["export"]:
                doc.chunk.exportRaster(
                    path=output_file,
                    projection=projection,
                    nodata_value=cfg["buildDem"]["nodata"],
                    source_data=Metashape.ElevationData,
                    image_compression=compression,
                )
                if cfg["buildOrthomosaic"]["enabled"] and "DSM-mesh" in cfg["buildOrthomosaic"]["surface"]:
                    build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending="dsm-mesh")

    # Building an orthomosaic from the mesh does not require a DEM, so this is done separately, independent of any DEM building
    if (cfg["buildOrthomosaic"]["enabled"] and "Mesh" in cfg["buildOrthomosaic"]["surface"]):
        build_export_orthomosaic(doc, log_file, run_id, cfg, from_mesh = True, file_ending="mesh")
    
    if(cfg["buildPointCloud"]["remove_after_export"]):
        doc.chunk.remove(doc.chunk.point_clouds)

    doc.save()

    return True


def build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending, from_mesh = False):
    """
    Helper function called by build_dem_orthomosaic. build_export_orthomosaic builds and exports an ortho based on the current elevation data.
    build_dem_orthomosaic sets the current elevation data and calls build_export_orthomosaic (one or more times depending on how many orthomosaics requested)
    
    Note that we have tried using the 'resolution' parameter of buildOrthomosaic, but it does not have any effect. An orthomosaic built onto a DSM always has a reslution of 1/4 the DSM, and one built onto the mesh has a resolution of ~the GSD.
    """

    # get a beginning time stamp for the next step
    timer6a = time.time()

    # prepping params for buildDem
    projection = Metashape.OrthoProjection()
    projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])

    if from_mesh:
        surface_data = Metashape.ModelData
    else:
        surface_data = Metashape.ElevationData

    doc.chunk.buildOrthomosaic(
        surface_data=surface_data,
        blending_mode=cfg["buildOrthomosaic"]["blending"],
        fill_holes=cfg["buildOrthomosaic"]["fill_holes"],
        refine_seamlines=cfg["buildOrthomosaic"]["refine_seamlines"],
        subdivide_task=cfg["subdivide_task"],
        projection=projection,
    )

    # get an ending time stamp for the previous step
    timer6b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time6 = diff_time(timer6b, timer6a)

    # record results to file
    with open(log_file, "a") as file:
        file.write(sep.join(["Build Orthomosaic", time6]) + "\n")

    doc.save()

    ## Export orthomosaic
    if cfg["buildOrthomosaic"]["export"]:
        output_file = os.path.join(cfg["output_path"], run_id + "_ortho_" + file_ending + ".tif")

        compression = Metashape.ImageCompression()
        compression.tiff_big = cfg["buildOrthomosaic"]["tiff_big"]
        compression.tiff_tiled = cfg["buildOrthomosaic"]["tiff_tiled"]
        compression.tiff_overviews = cfg["buildOrthomosaic"]["tiff_overviews"]

        projection = Metashape.OrthoProjection()
        projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])

        doc.chunk.exportRaster(
            path=output_file,
            projection=projection,
            nodata_value=cfg["buildOrthomosaic"]["nodata"],
            source_data=Metashape.OrthomosaicData,
            image_compression=compression,
        )
    
    if cfg["buildOrthomosaic"]["remove_after_export"]:
        doc.chunk.remove(doc.chunk.orthomosaics)

    return True


def export_report(doc, run_id, cfg):
    """
    Export report
    """

    output_file = os.path.join(cfg["output_path"], run_id + "_report.pdf")

    doc.chunk.exportReport(path=output_file)

    return True


def finish_run(log_file, config_file):
    """
    Finish run (i.e., write completed time to log)
    """

    # finish local results log and close it for the last time
    with open(log_file, "a") as file:
        file.write(sep.join(["Run Completed", stamp_time()]) + "\n")

    # open run configuration again. We can't just use the existing cfg file because its objects had already been converted to Metashape objects (they don't write well)
    with open(config_file) as file:
        config_full = yaml.safe_load(file)

    # write the run configuration to the log file
    with open(log_file, "a") as file:
        file.write("\n\n### CONFIGURATION ###\n")
        documents = yaml.dump(config_full, file, default_flow_style=False)
        file.write("### END CONFIGURATION ###\n")

    return True
