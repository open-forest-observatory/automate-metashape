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
    '''
    Format the timestamps as needed
    '''
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M')
    return stamp

def diff_time(t2, t1):
    '''
    Give a end and start time, subtract, and round
    '''
    total = str(round(t2-t1, 1))
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

def project_setup(cfg):
    '''
    Create output and project paths, if they don't exist
    Define a project ID based on photoset name and timestamp
    Define a project filename and a log filename
    Create the project
    Start a log file
    '''

    # Make project directories (necessary even if loading an existing project because this workflow saves a new project based on the old one, leaving the old one intact
    if not os.path.exists(cfg["output_path"]):
        os.makedirs(cfg["output_path"])
    if not os.path.exists(cfg["project_path"]):
        os.makedirs(cfg["project_path"])

    ### Set a filename template for project files and output files
    ## Get the first parts of the filename (the photoset ID and location string)

    run_name = cfg["run_name"]

    ## Project file example to make: "projectID_YYYYMMDDtHHMM-jobID.psx"
    timestamp = stamp_time()
    run_id = "_".join([run_name,timestamp])
    # TODO: If there is a slurm JobID, append to time (separated with "-", not "_"). This will keep jobs initiated in the same minute distinct

    project_file = os.path.join(cfg["project_path"], '.'.join([run_id, 'psx']) )
    log_file = os.path.join(cfg["output_path"], '.'.join([run_id+"_log",'txt']) )


    '''
    Create a doc and a chunk
    '''

    # create a handle to the Metashape object
    doc = Metashape.Document() #When running via Metashape, can use: doc = Metashape.app.document

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


    '''
    Log specs except for GPU
    '''

    # log Metashape version, CPU specs, time, and project location to results file
    # open the results file
    # TODO: records the Slurm values for actual cpus and ram allocated
    # https://slurm.schedmd.com/sbatch.html#lbAI
    with open(log_file, 'a') as file:

        # write a line with the Metashape version
        file.write(sep.join(['Project', run_id])+'\n')
        file.write(sep.join(['Agisoft Metashape Professional Version', Metashape.app.version])+'\n')
        # write a line with the date and time
        file.write(sep.join(['Processing started', stamp_time()]) +'\n')
        # write a line with CPU info - if possible, improve the way the CPU info is found / recorded
        file.write(sep.join(['Node', platform.node()])+'\n')
        file.write(sep.join(['CPU', platform.processor()]) +'\n')
        # write two lines with GPU info: count and model names - this takes multiple steps to make it look clean in the end

    return doc, log_file, run_id



def enable_and_log_gpu(log_file):
    '''
    Enables GPU and logs GPU specs
    '''

    gpustringraw = str(Metashape.app.enumGPUDevices())
    gpucount = gpustringraw.count("name': '")
    gpustring = ''
    currentgpu = 1
    while gpucount >= currentgpu:
        if gpustring != '': gpustring = gpustring+', '
        gpustring = gpustring+gpustringraw.split("name': '")[currentgpu].split("',")[0]
        currentgpu = currentgpu+1
    #gpustring = gpustringraw.split("name': '")[1].split("',")[0]
    gpu_mask = Metashape.app.gpu_mask

    with open(log_file, 'a') as file:
        file.write(sep.join(['Number of GPUs Found', str(gpucount)]) +'\n')
        file.write(sep.join(['GPU Model', gpustring])+'\n')
        file.write(sep.join(['GPU Mask', str(gpu_mask)])+'\n')

        # If a GPU exists but is not enabled, enable the 1st one
        if (gpucount > 0) and (gpu_mask == 0):
            Metashape.app.gpu_mask = 1
            gpu_mask = Metashape.app.gpu_mask
            file.write(sep.join(['GPU Mask Enabled', str(gpu_mask)])+'\n')

        # This writes down all the GPU devices available
        #file.write('GPU(s): '+str(Metashape.app.enumGPUDevices())+'\n')

    # set Metashape to *not* use the CPU during GPU steps (appears to be standard wisdom)
    Metashape.app.cpu_enable = False

    return True


def add_photos(doc, cfg):
    '''
    Add photos to project and change their labels to include their containing folder
    '''

    ## Get paths to all the project photos
    a = glob.iglob(os.path.join(cfg["photo_path"],"**","*.*"), recursive=True)   #(([jJ][pP][gG])|([tT][iI][fF]))
    b = [path for path in a]
    photo_files = [x for x in b if (re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)",x) and (not re.search("dem_usgs.tif",x)))]


    ## Add them
    if cfg["multispectral"]:
        doc.chunk.addPhotos(photo_files, layout = Metashape.MultiplaneLayout)
    else:
        doc.chunk.addPhotos(photo_files)


    ## Need to change the label on each camera so that it includes the containing folder(S)
    for camera in doc.chunk.cameras:
        path = camera.photo.path
        # remove the base imagery dir from this string
        rel_path = path.replace(cfg["photo_path"],"")
        # if it starts with a '/', remove it
        newlabel = re.sub("^/","",rel_path)
        camera.label = newlabel

    ## If specified, change the accuracy of the cameras to match the RTK flag (RTK fix if flag = 50, otherwise no fix
    if cfg["use_rtk"]:
        for cam in doc.chunk.cameras:
            rtkflag = cam.photo.meta['DJI/RtkFlag']
            if rtkflag == '50':
                cam.reference.location_accuracy = Metashape.Vector([cfg["fix_accuracy"],cfg["fix_accuracy"],cfg["fix_accuracy"]])
                cam.reference.accuracy = Metashape.Vector([cfg["fix_accuracy"],cfg["fix_accuracy"],cfg["fix_accuracy"]])
            else:
                cam.reference.location_accuracy = Metashape.Vector([cfg["nofix_accuracy"],cfg["nofix_accuracy"],cfg["nofix_accuracy"]])
                cam.reference.accuracy = Metashape.Vector([cfg["nofix_accuracy"],cfg["nofix_accuracy"],cfg["nofix_accuracy"]])


    doc.save()

    return True


def calibrate_reflectance(doc, cfg):
    # TODO: Handle failure to find panels, or mulitple panel images by returning error to user.
    doc.chunk.locateReflectancePanels()
    doc.chunk.loadReflectancePanelCalibration(os.path.join(cfg["photo_path"],"calibration",cfg["calibrateReflectance"]["panel_filename"]))
    # doc.chunk.calibrateReflectance(use_reflectance_panels=True,use_sun_sensor=True)
    doc.chunk.calibrateReflectance(use_reflectance_panels=cfg["calibrateReflectance"]["use_reflectance_panels"],
                                   use_sun_sensor=cfg["calibrateReflectance"]["use_sun_sensor"])
    doc.save()

    return True


def add_gcps(doc, cfg):
    '''
    Add GCPs (GCP coordinates and the locations of GCPs in individual photos.
    See the helper script (and the comments therein) for details on how to prepare the data needed by this function: R/prep_gcps.R
    '''

    ## Tag specific pixels in specific images where GCPs are located
    path = os.path.join(cfg["photo_path"], "gcps", "prepared", "gcp_imagecoords_table.csv")
    file = open(path)
    content = file.read().splitlines()

    for line in content:
        marker_label, camera_label, x_proj, y_proj = line.split(",")
        if marker_label[0] == '"': # if it's in quotes (from saving CSV in Excel), remove quotes
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

        marker.projections[camera] = Metashape.Marker.Projection((float(x_proj), float(y_proj)), True)


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
        marker.reference.accuracy = (cfg["addGCPs"]["marker_location_accuracy"], cfg["addGCPs"]["marker_location_accuracy"], cfg["addGCPs"]["marker_location_accuracy"])

    doc.chunk.marker_location_accuracy = (cfg["addGCPs"]["marker_location_accuracy"],cfg["addGCPs"]["marker_location_accuracy"],cfg["addGCPs"]["marker_location_accuracy"])
    doc.chunk.marker_projection_accuracy = cfg["addGCPs"]["marker_projection_accuracy"]

    doc.save()

    return True


def align_photos(doc, log_file, cfg):
    '''
    Match photos, align cameras, optimize cameras
    '''

    #### Align photos

    # get a beginning time stamp
    timer1a = time.time()

    # Align cameras
    doc.chunk.matchPhotos(downscale=cfg["alignPhotos"]["downscale"],
                          subdivide_task = cfg["subdivide_task"])
    doc.chunk.alignCameras(adaptive_fitting=cfg["alignPhotos"]["adaptive_fitting"],
                           subdivide_task = cfg["subdivide_task"])
    doc.save()

    # get an ending time stamp
    timer1b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time1 = diff_time(timer1b, timer1a)

    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Align Photos', time1])+'\n')

    return True


def reset_region(doc):
    '''
    Reset the region and make it much larger than the points; necessary because if points go outside the region, they get clipped when saving
    '''

    doc.chunk.resetRegion()
    region_dims = doc.chunk.region.size
    region_dims[2] *= 3
    doc.chunk.region.size = region_dims

    return True


def optimize_cameras(doc, cfg):
    '''
    Optimize cameras
    '''

    # Disable camera locations as reference if specified in YML
    if cfg["addGCPs"]["enabled"] and cfg["addGCPs"]["optimize_w_gcps_only"]:
        n_cameras = len(doc.chunk.cameras)
        for i in range(0, n_cameras):
            doc.chunk.cameras[i].reference.enabled = False

    # Currently only optimizes the default parameters, which is not all possible parameters
    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])
    doc.save()

    return True


def filter_points_usgs_part1(doc, cfg):

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    rec_thresh_percent = cfg["filterPointsUSGS"]["rec_thresh_percent"]
    rec_thresh_absolute = cfg["filterPointsUSGS"]["rec_thresh_absolute"]
    proj_thresh_percent = cfg["filterPointsUSGS"]["proj_thresh_percent"]
    proj_thresh_absolute = cfg["filterPointsUSGS"]["proj_thresh_absolute"]
    reproj_thresh_percent = cfg["filterPointsUSGS"]["reproj_thresh_percent"]
    reproj_thresh_absolute = cfg["filterPointsUSGS"]["reproj_thresh_absolute"]

    fltr = Metashape.PointCloud.Filter()
    fltr.init(doc.chunk, Metashape.PointCloud.Filter.ReconstructionUncertainty)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1 - rec_thresh_percent / 100))]
    if thresh < rec_thresh_absolute:
        thresh = rec_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    fltr = Metashape.PointCloud.Filter()
    fltr.init(doc.chunk, Metashape.PointCloud.Filter.ProjectionAccuracy)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1- proj_thresh_percent / 100))]
    if thresh < proj_thresh_absolute:
        thresh = proj_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    fltr = Metashape.PointCloud.Filter()
    fltr.init(doc.chunk, Metashape.PointCloud.Filter.ReprojectionError)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
    if thresh < reproj_thresh_absolute:
        thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    doc.save()


def filter_points_usgs_part2(doc, cfg):

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    reproj_thresh_percent = cfg["filterPointsUSGS"]["reproj_thresh_percent"]
    reproj_thresh_absolute = cfg["filterPointsUSGS"]["reproj_thresh_absolute"]

    fltr = Metashape.PointCloud.Filter()
    fltr.init(doc.chunk, Metashape.PointCloud.Filter.ReprojectionError)
    values = fltr.values.copy()
    values.sort()
    thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
    if thresh < reproj_thresh_absolute:
        thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
    fltr.removePoints(thresh)

    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])

    doc.save()


def build_dense_cloud(doc, log_file, run_id, cfg):
    '''
    Build depth maps and dense cloud
    '''

    ### Build depth maps

    # get a beginning time stamp for the next step
    timer2a = time.time()

    # build depth maps only instead of also building the dense cloud ##?? what does
    doc.chunk.buildDepthMaps(downscale=cfg["buildDenseCloud"]["downscale"],
                             filter_mode=cfg["buildDenseCloud"]["filter_mode"],
                             reuse_depth=cfg["buildDenseCloud"]["reuse_depth"],
                             max_neighbors=cfg["buildDenseCloud"]["max_neighbors"],
                             subdivide_task=cfg["subdivide_task"])
    doc.save()

    # get an ending time stamp for the previous step
    timer2b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time2 = diff_time(timer2b, timer2a)

    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Depth Maps', time2]) + '\n')

    ### Build dense cloud

    # get a beginning time stamp for the next step
    timer3a = time.time()

    # build dense cloud
    doc.chunk.buildDenseCloud(max_neighbors=cfg["buildDenseCloud"]["max_neighbors"],
                              keep_depth = cfg["buildDenseCloud"]["keep_depth"],
                              subdivide_task = cfg["subdivide_task"],
                              point_colors = True)
    doc.save()

    # get an ending time stamp for the previous step
    timer3b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time3 = diff_time(timer3b, timer3a)

    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Dense Cloud', time3])+'\n')

    ### Classify ground points


    if cfg["buildDenseCloud"]["classify"]:

        # get a beginning time stamp for the next step
        timer_a = time.time()

        doc.chunk.dense_cloud.classifyGroundPoints(max_angle=cfg["buildDenseCloud"]["max_angle"],
                                                   max_distance=cfg["buildDenseCloud"]["max_distance"],
                                                   cell_size=cfg["buildDenseCloud"]["cell_size"])
        doc.save()

        # get an ending time stamp for the previous step
        timer_b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time_tot = diff_time(timer_b, timer_a)

        # record results to file
        with open(log_file, 'a') as file:
            file.write(sep.join(['Classify Ground Points', time_tot]) + '\n')



    ### Export points

    if cfg["buildDenseCloud"]["export"]:

        output_file = os.path.join(cfg["output_path"], run_id + '_points.las')

        if cfg["buildDenseCloud"]["classes"] == "ALL":
            # call without classes argument (Metashape then defaults to all classes)
            doc.chunk.exportPoints(path=output_file,
                                   source_data=Metashape.DenseCloudData,
                                   format=Metashape.PointsFormatLAS,
                                   crs=Metashape.CoordinateSystem(cfg["project_crs"]),
                                   subdivide_task=cfg["subdivide_task"])
        else:
            # call with classes argument
            doc.chunk.exportPoints(path=output_file,
                                   source_data=Metashape.DenseCloudData,
                                   format=Metashape.PointsFormatLAS,
                                   crs=Metashape.CoordinateSystem(cfg["project_crs"]),
                                   clases=cfg["buildDenseCloud"]["classes"],
                                   subdivide_task=cfg["subdivide_task"])

    return True




def build_dem(doc, log_file, run_id, cfg):
    '''
    Build end export DEM
    '''

    # get a beginning time stamp for the next step
    timer5a = time.time()

    #prepping params for buildDem
    projection = Metashape.OrthoProjection()
    projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])

    #prepping params for export
    compression = Metashape.ImageCompression()
    compression.tiff_big = cfg["buildDem"]["tiff_big"]
    compression.tiff_tiled = cfg["buildDem"]["tiff_tiled"]
    compression.tiff_overviews = cfg["buildDem"]["tiff_overviews"]

    if (cfg["buildDem"]["type"] == "DSM") | (cfg["buildDem"]["type"] == "both"):
        # call without classes argument (Metashape then defaults to all classes)
        doc.chunk.buildDem(source_data = Metashape.DenseCloudData,
                           subdivide_task = cfg["subdivide_task"],
                           projection = projection)
        output_file = os.path.join(cfg["output_path"], run_id + '_dsm.tif')
        if cfg["buildDem"]["export"]:
            doc.chunk.exportRaster(path=output_file,
                                   projection=projection,
                                   nodata_value=cfg["buildDem"]["nodata"],
                                   source_data=Metashape.ElevationData,
                                   image_compression=compression)
    if (cfg["buildDem"]["type"] == "DTM") | (cfg["buildDem"]["type"] == "both"):
        # call with classes argument
        doc.chunk.buildDem(source_data = Metashape.DenseCloudData,
                           classes = Metashape.PointClass.Ground,
                           subdivide_task = cfg["subdivide_task"],
                           projection = projection)
        output_file = os.path.join(cfg["output_path"], run_id + '_dtm.tif')
        if cfg["buildDem"]["export"]:
            doc.chunk.exportRaster(path=output_file,
                                   projection=projection,
                                   nodata_value=cfg["buildDem"]["nodata"],
                                   source_data=Metashape.ElevationData,
                                   image_compression=compression)
    if (cfg["buildDem"]["type"] != "DTM") & (cfg["buildDem"]["type"] == "both") & (cfg["buildDem"]["type"] == "DSM"):
        raise ValueError("DEM type must be either 'DSM' or 'DTM' or 'both'")

    doc.save()

    # get an ending time stamp for the previous step
    timer5b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time5 = diff_time(timer5b, timer5a)

    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build DEM', time5])+'\n')

    return True

# This is just a helper function called by build_orthomosaic
def export_orthomosaic(doc, log_file, run_id, cfg):
    '''
    Export orthomosaic
    '''



    return True


def build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending):
    '''
    Helper function called by build_orthomosaics. build_export_orthomosaic builds and exports an ortho based on the current elevation data.
    build_orthomosaics sets the current elevation data and calls build_export_orthomosaic (one or more times depending on how many orthomosaics requested)
    '''

    # get a beginning time stamp for the next step
    timer6a = time.time()

    #prepping params for buildDem
    projection = Metashape.OrthoProjection()
    projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])

    doc.chunk.buildOrthomosaic(surface_data=Metashape.ElevationData,
                               blending_mode=cfg["buildOrthomosaic"]["blending"],
                               fill_holes=cfg["buildOrthomosaic"]["fill_holes"],
                               refine_seamlines=cfg["buildOrthomosaic"]["refine_seamlines"],
                               subdivide_task=cfg["subdivide_task"],
                               projection=projection)

    doc.save()

    ## Export orthomosaic
    if cfg["buildOrthomosaic"]["export"]:
        output_file = os.path.join(cfg["output_path"], run_id + '_ortho_' + file_ending + '.tif')

        compression = Metashape.ImageCompression()
        compression.tiff_big = cfg["buildOrthomosaic"]["tiff_big"]
        compression.tiff_tiled = cfg["buildOrthomosaic"]["tiff_tiled"]
        compression.tiff_overviews = cfg["buildOrthomosaic"]["tiff_overviews"]

        projection = Metashape.OrthoProjection()
        projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])

        doc.chunk.exportRaster(path=output_file,
                               projection=projection,
                               nodata_value=cfg["buildOrthomosaic"]["nodata"],
                               source_data=Metashape.OrthomosaicData,
                               image_compression=compression)

    # get an ending time stamp for the previous step
    timer6b = time.time()

    # calculate difference between end and start time to 1 decimal place
    time6 = diff_time(timer6b, timer6a)

    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Orthomosaic', time6]) + '\n')

    return True


def build_orthomosaics(doc, log_file, run_id, cfg):
    '''
    Build orthomosaic. This function just calculates the needed elevation data(s) and then calls build_export_orthomosaic to do the actual building and exporting. It does this multiple times if orthos based on multiple surfaces were requsted
    '''

    # prep projection for export step below (in case export is enabled)
    projection = Metashape.OrthoProjection()
    projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])

    # get a beginning time stamp for the next step
    timer6a = time.time()

    # what should the orthomosaic filename end in? e.g., DSM, DTM, USGS to indicate the surface it was built on
    file_ending = cfg["buildOrthomosaic"]["surface"]

    # Import USGS DEM as surface for orthomosaic if specified
    if cfg["buildOrthomosaic"]["surface"] == "USGS":
        path = os.path.join(cfg["photo_path"],cfg["buildOrthomosaic"]["usgs_dem_path"])
        crs = Metashape.CoordinateSystem(cfg["buildOrthomosaic"]["usgs_dem_crs"])
        doc.chunk.importRaster(path=path,
                               crs=crs,
                               raster_type=Metashape.ElevationData)
        build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending = "USGS")
    # Otherwise use Metashape point cloud to build elevation model
    # DTM: use ground points only
    if (cfg["buildOrthomosaic"]["surface"] == "DTM") | (cfg["buildOrthomosaic"]["surface"] == "DTMandDSM"):
        doc.chunk.buildDem(source_data = Metashape.DenseCloudData,
                           classes=Metashape.PointClass.Ground,
                           subdivide_task=cfg["subdivide_task"],
                           projection=projection)
        build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending = "dtm")
    # DSM: use all point classes
    if (cfg["buildOrthomosaic"]["surface"] == "DSM") | (cfg["buildOrthomosaic"]["surface"] == "DTMandDSM"):
        doc.chunk.buildDem(source_data = Metashape.DenseCloudData,
                           subdivide_task=cfg["subdivide_task"],
                           projection=projection)
        build_export_orthomosaic(doc, log_file, run_id, cfg, file_ending = "dsm")

    return True


def export_report(doc, run_id, cfg):
    '''
    Export report
    '''

    output_file = os.path.join(cfg["output_path"], run_id+'_report.pdf')

    doc.chunk.exportReport(path = output_file)

    return True


def finish_run(log_file,config_file):
    '''
    Finish run (i.e., write completed time to log)
    '''

    # finish local results log and close it for the last time
    with open(log_file, 'a') as file:
        file.write(sep.join(['Run Completed', stamp_time()])+'\n')

    # open run configuration again. We can't just use the existing cfg file because its objects had already been converted to Metashape objects (they don't write well)
    with open(config_file) as file:
        config_full = yaml.load(file)

    # write the run configuration to the log file
    with open(log_file, 'a') as file:
        file.write("\n\n### CONFIGURATION ###\n")
        documents = yaml.dump(config_full,file, default_flow_style=False)
        file.write("### END CONFIGURATION ###\n")


    return True
