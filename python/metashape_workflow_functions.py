# Derek Young and Alex Mandel
# University of California, Davis
# 2021

#### Import libraries
import datetime
import glob
import os
import platform
import re

# Import the fuctionality we need to make time stamps to measure performance
import time

### Import the Metashape functionality
import Metashape
import yaml


#### Helper functions
def convert_objects(a_dict):
    """
    Convert strings that refer to metashape objects (e.g. "Metashape.MoasicBlending") into metashape objects

    Based on
    https://stackoverflow.com/a/25896596/237354
    """
    for k, v in a_dict.items():
        if not isinstance(v, dict):
            if isinstance(v, str):
                # TODO look for Metashape.
                if (
                    v
                    and "Metashape" in v
                    and not ("path" in k)
                    and not ("project" in k)
                    and not ("name" in k)
                ):  # allow "path" and "project" and "name" keys (e.g. "photoset_path" and "run_name") from YAML to include "Metashape" (e.g., Metashape in the filename)
                    a_dict[k] = eval(v)
            elif isinstance(v, list):
                # skip if no item in list have metashape, else convert string to metashape object
                if any("Metashape" in item for item in v):
                    a_dict[k] = [eval(item) for item in v if ("Metashape" in item)]
        else:
            convert_objects(v)


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


# Set the log file name-value separator
# Chose ; as : is in timestamps
# TODO: Consider moving log to json/yaml formatting using a dict


class MetashapeWorkflow:

    sep = "; "

    def __init__(self, config_file):
        """
        Initializes an instance of the MetashapeWorkflow class based on the config file given
        """
        self.config_file = config_file
        self.doc = None
        self.log_file = None
        self.run_id = None
        self.cfg = None
        self.read_yaml()

    def read_yaml(self):
        with open(self.config_file, "r") as ymlfile:
            self.cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

        # TODO: wrap in a Try to catch errors
        convert_objects(self.cfg)

    #### Functions for each major step in Metashape

    def run(self):
        """
        Execute metashape workflow steps based on config file
        """
        self.project_setup()

        self.enable_and_log_gpu()

        if (self.cfg["photo_path"] != "") and (
            self.cfg["addPhotos"]["enabled"]
        ):  # only add photos if there is a photo directory listed
            self.add_photos()

        if self.cfg["calibrateReflectance"]["enabled"]:
            self.calibrate_reflectance()

        if self.cfg["alignPhotos"]["enabled"]:
            self.align_photos()
            self.reset_region()

        if self.cfg["filterPointsUSGS"]["enabled"]:
            self.filter_points_usgs_part1()
            self.reset_region()

        if self.cfg["addGCPs"]["enabled"]:
            self.add_gcps()
            self.reset_region()

        if self.cfg["optimizeCameras"]["enabled"]:
            self.optimize_cameras()
            self.reset_region()

        if self.cfg["filterPointsUSGS"]["enabled"]:
            self.filter_points_usgs_part2()
            self.reset_region()

        if self.cfg["buildDepthMaps"]["enabled"]:
            self.build_depth_maps()

        if self.cfg["buildPointCloud"]["enabled"]:
            self.build_point_cloud()

        if self.cfg["buildModel"]["enabled"]:
            self.build_model()

        # For this step, the check for whether it is enabled in the config happens inside the function, because there are two steps (DEM and ortho), each of which can be enabled independently
        self.build_dem_orthomosaic()

        if self.cfg["photo_path_secondary"] != "":
            self.add_align_secondary_photos()

        self.export_report()

        self.finish_run()

    def project_setup(self):
        """
        Create output and project paths, if they don't exist
        Define a project ID based on specified project name and timestamp
        Define a project filename and a log filename
        Create the project
        Start a log file
        """

        # Make project directories (necessary even if loading an existing project because this workflow saves a new project based on the old one, leaving the old one intact
        if not os.path.exists(self.cfg["output_path"]):
            os.makedirs(self.cfg["output_path"])
        if not os.path.exists(self.cfg["project_path"]):
            os.makedirs(self.cfg["project_path"])

        ### Set a filename template for project files and output files based on the 'run_name' key of the config YML
        ## BUT if the value for run_name is "from_config_filename", then use the config filename for the run name.

        run_name = self.cfg["run_name"]

        if run_name == "from_config_filename" or run_name == "":
            file_basename = os.path.basename(
                self.config_file
            )  # extracts file base name from path
            run_name, _ = os.path.splitext(file_basename)  # removes extension

        ## Project file example to make: "projectID_YYYYMMDDtHHMM-jobID.psx"
        timestamp = stamp_time()
        self.run_id = "_".join([run_name, timestamp])
        # TODO: If there is a slurm JobID, append to time (separated with "-", not "_"). This will keep jobs initiated in the same minute distinct

        project_file = os.path.join(
            self.cfg["project_path"], ".".join([self.run_id, "psx"])
        )
        self.log_file = os.path.join(
            self.cfg["output_path"], ".".join([self.run_id + "_log", "txt"])
        )

        """
        Create a doc and a chunk
        """

        # create a handle to the Metashape object
        self.doc = (
            Metashape.Document()
        )  # When running via Metashape, can use: doc = Metashape.app.document

        # If specified, open existing project
        if self.cfg["load_project"] != "":
            self.doc.open(self.cfg["load_project"])
        else:
            # Initialize a chunk, set its CRS as specified
            chunk = self.doc.addChunk()
            chunk.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])
            chunk.marker_crs = Metashape.CoordinateSystem(
                self.cfg["addGCPs"]["gcp_crs"]
            )

        # Save doc doc as new project (even if we opened an existing project, save as a separate one so the existing project remains accessible in its original state)
        self.doc.save(project_file)

        """
        Log specs except for GPU
        """

        # log Metashape version, CPU specs, time, and project location to results file
        # open the results file
        # TODO: records the Slurm values for actual cpus and ram allocated
        # https://slurm.schedmd.com/sbatch.html#lbAI
        with open(self.log_file, "a") as file:

            # write a line with the Metashape version
            file.write(MetashapeWorkflow.sep.join(["Project", self.run_id]) + "\n")
            file.write(
                MetashapeWorkflow.sep.join(
                    ["Agisoft Metashape Professional Version", Metashape.app.version]
                )
                + "\n"
            )
            # write a line with the date and time
            file.write(
                MetashapeWorkflow.sep.join(["Processing started", stamp_time()]) + "\n"
            )
            # write a line with CPU info - if possible, improve the way the CPU info is found / recorded
            file.write(MetashapeWorkflow.sep.join(["Node", platform.node()]) + "\n")
            file.write(MetashapeWorkflow.sep.join(["CPU", platform.processor()]) + "\n")
            # write two lines with GPU info: count and model names - this takes multiple steps to make it look clean in the end

    def enable_and_log_gpu(self):
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
            gpustring = (
                gpustring + gpustringraw.split("name': '")[currentgpu].split("',")[0]
            )
            currentgpu = currentgpu + 1
        # gpustring = gpustringraw.split("name': '")[1].split("',")[0]
        gpu_mask = Metashape.app.gpu_mask

        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflow.sep.join(["Number of GPUs Found", str(gpucount)])
                + "\n"
            )
            file.write(MetashapeWorkflow.sep.join(["GPU Model", gpustring]) + "\n")
            file.write(MetashapeWorkflow.sep.join(["GPU Mask", str(gpu_mask)]) + "\n")

            # If a GPU exists but is not enabled, enable the 1st one
            if (gpucount > 0) and (gpu_mask == 0):
                Metashape.app.gpu_mask = 1
                gpu_mask = Metashape.app.gpu_mask
                file.write(
                    MetashapeWorkflow.sep.join(["GPU Mask Enabled", str(gpu_mask)])
                    + "\n"
                )

            # This writes down all the GPU devices available
            # file.write('GPU(s): '+str(Metashape.app.enumGPUDevices())+'\n')

        # set Metashape to *not* use the CPU during GPU steps (appears to be standard wisdom)
        Metashape.app.cpu_enable = False

        # Disable CUDA if specified
        if not self.cfg["use_cuda"]:
            Metashape.app.settings.setValue("main/gpu_enable_cuda", "0")

        # Set GPU multiplier to value specified (2 is default)
        Metashape.app.settings.setValue(
            "main/depth_max_gpu_multiplier", self.cfg["gpu_multiplier"]
        )

        return True

    def add_photos(self, secondary=False):
        """
        Add photos to project and change their labels to include their containing folder. Secondary: if
        True, this is a secondary set of photos to be aligned only, after all photogrammetry products
        have been produced from the primary set of photos.
        """

        if secondary:
            photo_paths = self.cfg["photo_path_secondary"]
        else:
            photo_paths = self.cfg["photo_path"]

        # If it's a single string (i.e. one directory), make it a list of one string so we can iterate
        # over it the same as if it were a list of strings
        if isinstance(photo_paths, str):
            photo_paths = [photo_paths]

        for photo_path in photo_paths:

            grp = self.doc.chunk.addCameraGroup()

            ## Get paths to all the project photos
            a = glob.iglob(
                os.path.join(photo_path, "**", "*.*"), recursive=True
            )  # (([jJ][pP][gG])|([tT][iI][fF]))
            b = [path for path in a]
            photo_files = [
                x
                for x in b
                if (
                    re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)", x)
                    and (not re.search("dem_usgs.tif", x))
                )
            ]

            ## Add them
            if self.cfg["addPhotos"]["multispectral"]:
                self.doc.chunk.addPhotos(
                    photo_files, layout=Metashape.MultiplaneLayout, group=grp
                )
            else:
                self.doc.chunk.addPhotos(photo_files, group=grp)

        ## Need to change the label on each camera so that it includes the containing folder(s)
        for camera in self.doc.chunk.cameras:
            path = camera.photo.path
            camera.label = path

        if self.cfg["addPhotos"]["separate_calibration_per_path"]:
            # Assign a different (new) sensor (i.e. independent calibration) to each group of photos
            for grp in self.doc.chunk.camera_groups:

                # Get the template for the sensor from the first photo in the group
                for cam in self.doc.chunk.cameras:
                    if cam.group == grp:
                        sensor = cam.sensor
                        break

                self.doc.chunk.addSensor(self.doc.chunk.cameras[0].sensor)
                sensor = self.doc.chunk.sensors[-1]

                for cam in self.doc.chunk.cameras:
                    if cam.group == grp:
                        cam.sensor = sensor

            # Remove the first (deafult) sensor, which should no longer be assigned to any photos
            self.doc.chunk.remove(self.doc.chunk.sensors[0])

        ## If specified, change the accuracy of the cameras to match the RTK flag (RTK fix if flag = 50, otherwise no fix
        if self.cfg["addPhotos"]["use_rtk"]:
            for cam in self.doc.chunk.cameras:
                rtkflag = cam.photo.meta["DJI/RtkFlag"]
                if rtkflag == "50":
                    cam.reference.location_accuracy = Metashape.Vector(
                        [
                            self.cfg["addPhotos"]["fix_accuracy"],
                            self.cfg["addPhotos"]["fix_accuracy"],
                            self.cfg["addPhotos"]["fix_accuracy"],
                        ]
                    )
                    cam.reference.accuracy = Metashape.Vector(
                        [
                            self.cfg["addPhotos"]["fix_accuracy"],
                            self.cfg["addPhotos"]["fix_accuracy"],
                            self.cfg["addPhotos"]["fix_accuracy"],
                        ]
                    )
                else:
                    cam.reference.location_accuracy = Metashape.Vector(
                        [
                            self.cfg["addPhotos"]["nofix_accuracy"],
                            self.cfg["addPhotos"]["nofix_accuracy"],
                            self.cfg["addPhotos"]["nofix_accuracy"],
                        ]
                    )
                    cam.reference.accuracy = Metashape.Vector(
                        [
                            self.cfg["addPhotos"]["nofix_accuracy"],
                            self.cfg["addPhotos"]["nofix_accuracy"],
                            self.cfg["addPhotos"]["nofix_accuracy"],
                        ]
                    )

        self.doc.save()

        return True

    def calibrate_reflectance(self):
        # TODO: Handle failure to find panels, or mulitple panel images by returning error to user.
        self.doc.chunk.locateReflectancePanels()
        self.doc.chunk.loadReflectancePanelCalibration(
            os.path.join(
                self.cfg["photo_path"],
                "calibration",
                self.cfg["calibrateReflectance"]["panel_filename"],
            )
        )
        # self.doc.chunk.calibrateReflectance(use_reflectance_panels=True,use_sun_sensor=True)
        self.doc.chunk.calibrateReflectance(
            use_reflectance_panels=self.cfg["calibrateReflectance"][
                "use_reflectance_panels"
            ],
            use_sun_sensor=self.cfg["calibrateReflectance"]["use_sun_sensor"],
        )
        self.doc.save()

        return True

    def add_gcps(self):
        """
        Add GCPs (GCP coordinates and the locations of GCPs in individual photos.
        See the helper script (and the comments therein) for details on how to prepare the data needed by this function: R/prep_gcps.R
        """

        # Determine the location of the GCPs file, which is also the base path to prepend to the GCP
        # camera label (relative to what's specified in the GCPs file, which is a relative path), to
        # make it into an absolute path to match the label of the camera in the Metashape. Note the
        # difference between the two camera labels: one is the camera label specified in the GCPs file
        # (relative path), and one is the camera label in the Metashape (absolute). Currently, this
        # assumes that all of the GCPs apply to the first provided folder of cameras (i.e., the only
        # folder provided, or the first folder provided if multiple are provided) -- and that this is
        # the folder containing the GCP definition file. TODO: Tolerate GCPs split across multiple
        # folders of input images:
        # https://github.com/open-forest-observatory/automate-metashape-2/issues/49.

        photo_paths = self.cfg["photo_path"]

        # If it's a single string (i.e. one directory), make it a list of one string so we can take the
        # first element using the same operation we would use on a list of strings
        if isinstance(photo_paths, str):
            photo_paths = [photo_paths]

        # Take the first folder and assume it's the one with the GCPs file
        photo_path = photo_paths[0]

        ## Tag specific pixels in specific images where GCPs are located
        path = os.path.join(photo_path, "gcps", "prepared", "gcp_imagecoords_table.csv")
        file = open(path)
        content = file.read().splitlines()

        for line in content:
            marker_label, camera_label, x_proj, y_proj = line.split(",")
            if (
                marker_label[0] == '"'
            ):  # if it's in quotes (from saving CSV in Excel), remove quotes
                marker_label = marker_label[
                    1:-1
                ]  # need to get it out of the two pairs of quotes
            if (
                camera_label[0] == '"'
            ):  # if it's in quotes (from saving CSV in Excel), remove quotes
                camera_label = camera_label[1:-1]

            marker = get_marker(self.doc.chunk, marker_label)
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = marker_label

            # Prepend the image path to the GCP's camera label to make it an absolute path
            camera_label = os.path.join(photo_path, camera_label)

            camera = get_camera(self.doc.chunk, camera_label)
            if not camera:
                print(camera_label + " camera not found in project")
                continue

            marker.projections[camera] = Metashape.Marker.Projection(
                (float(x_proj), float(y_proj)), True
            )

        ## Assign real-world coordinates to each GCP
        path = os.path.join(photo_path, "gcps", "prepared", "gcp_table.csv")

        file = open(path)
        content = file.read().splitlines()

        for line in content:
            marker_label, world_x, world_y, world_z = line.split(",")
            if (
                marker_label[0] == '"'
            ):  # if it's in quotes (from saving CSV in Excel), remove quotes
                marker_label = marker_label[
                    1:-1
                ]  # need to get it out of the two pairs of quotes

            marker = get_marker(self.doc.chunk, marker_label)
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = marker_label

            marker.reference.location = (float(world_x), float(world_y), float(world_z))
            marker.reference.accuracy = (
                self.cfg["addGCPs"]["marker_location_accuracy"],
                self.cfg["addGCPs"]["marker_location_accuracy"],
                self.cfg["addGCPs"]["marker_location_accuracy"],
            )

        self.doc.chunk.marker_location_accuracy = (
            self.cfg["addGCPs"]["marker_location_accuracy"],
            self.cfg["addGCPs"]["marker_location_accuracy"],
            self.cfg["addGCPs"]["marker_location_accuracy"],
        )
        self.doc.chunk.marker_projection_accuracy = self.cfg["addGCPs"][
            "marker_projection_accuracy"
        ]

        self.doc.save()

        return True

    def export_cameras(self):
        output_file = os.path.join(
            self.cfg["output_path"], self.run_id + "_cameras.xml"
        )
        # Defaults to xml format, which is the only one we've used so far
        self.doc.chunk.exportCameras(path=output_file)

    def align_photos(self):
        """
        Match photos, align cameras, optimize cameras
        """

        #### Align photos

        # get a beginning time stamp
        timer1a = time.time()

        # Align cameras
        self.doc.chunk.matchPhotos(
            downscale=self.cfg["alignPhotos"]["downscale"],
            subdivide_task=self.cfg["subdivide_task"],
            keep_keypoints=self.cfg["alignPhotos"]["keep_keypoints"],
            generic_preselection=self.cfg["alignPhotos"]["generic_preselection"],
            reference_preselection=self.cfg["alignPhotos"]["reference_preselection"],
            reference_preselection_mode=self.cfg["alignPhotos"][
                "reference_preselection_mode"
            ],
        )
        self.doc.chunk.alignCameras(
            adaptive_fitting=self.cfg["alignPhotos"]["adaptive_fitting"],
            subdivide_task=self.cfg["subdivide_task"],
            reset_alignment=self.cfg["alignPhotos"]["reset_alignment"],
        )
        self.doc.save()

        # get an ending time stamp
        timer1b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time1 = diff_time(timer1b, timer1a)

        # optionally export
        if self.cfg["alignPhotos"]["export"]:
            self.export_cameras()

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflow.sep.join(["Align Photos", time1]) + "\n")

        return True

    def reset_region(self):
        """
        Reset the region and make it much larger than the points; necessary because if points go outside the region, they get clipped when saving
        """

        self.doc.chunk.resetRegion()
        region_dims = self.doc.chunk.region.size
        region_dims[2] *= 3
        self.doc.chunk.region.size = region_dims

        return True

    def optimize_cameras(self):
        """
        Optimize cameras
        """

        # get a beginning time stamp
        timer1a = time.time()

        # Disable camera locations as reference if specified in YML
        if (
            self.cfg["addGCPs"]["enabled"]
            and self.cfg["addGCPs"]["optimize_w_gcps_only"]
        ):
            n_cameras = len(self.doc.chunk.cameras)
            for i in range(0, n_cameras):
                self.doc.chunk.cameras[i].reference.enabled = False

        # Currently only optimizes the default parameters, which is not all possible parameters
        self.doc.chunk.optimizeCameras(
            adaptive_fitting=self.cfg["optimizeCameras"]["adaptive_fitting"]
        )

        # get an ending time stamp
        timer1b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time1 = diff_time(timer1b, timer1a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflow.sep.join(["Optimize cameras", time1]) + "\n")

        self.doc.save()

        # optionally export, note this would override the export from align_cameras
        if self.cfg["optimizeCameras"]["export"]:
            self.export_cameras()

        return True

    def filter_points_usgs_part1(self):

        # get a beginning time stamp
        timer1a = time.time()

        self.doc.chunk.optimizeCameras(
            adaptive_fitting=self.cfg["optimizeCameras"]["adaptive_fitting"]
        )

        rec_thresh_percent = self.cfg["filterPointsUSGS"]["rec_thresh_percent"]
        rec_thresh_absolute = self.cfg["filterPointsUSGS"]["rec_thresh_absolute"]
        proj_thresh_percent = self.cfg["filterPointsUSGS"]["proj_thresh_percent"]
        proj_thresh_absolute = self.cfg["filterPointsUSGS"]["proj_thresh_absolute"]
        reproj_thresh_percent = self.cfg["filterPointsUSGS"]["reproj_thresh_percent"]
        reproj_thresh_absolute = self.cfg["filterPointsUSGS"]["reproj_thresh_absolute"]

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ReconstructionUncertainty)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - rec_thresh_percent / 100))]
        if thresh < rec_thresh_absolute:
            thresh = rec_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        self.doc.chunk.optimizeCameras(
            adaptive_fitting=self.cfg["optimizeCameras"]["adaptive_fitting"]
        )

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ProjectionAccuracy)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - proj_thresh_percent / 100))]
        if thresh < proj_thresh_absolute:
            thresh = proj_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        self.doc.chunk.optimizeCameras(
            adaptive_fitting=self.cfg["optimizeCameras"]["adaptive_fitting"]
        )

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ReprojectionError)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
        if thresh < reproj_thresh_absolute:
            thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        self.doc.chunk.optimizeCameras(
            adaptive_fitting=self.cfg["optimizeCameras"]["adaptive_fitting"]
        )

        # get an ending time stamp
        timer1b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time1 = diff_time(timer1b, timer1a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflow.sep.join(["USGS filter points part 1", time1]) + "\n"
            )

        self.doc.save()

    def filter_points_usgs_part2(self):

        # get a beginning time stamp
        timer1a = time.time()

        self.doc.chunk.optimizeCameras(
            adaptive_fitting=self.cfg["optimizeCameras"]["adaptive_fitting"]
        )

        reproj_thresh_percent = self.cfg["filterPointsUSGS"]["reproj_thresh_percent"]
        reproj_thresh_absolute = self.cfg["filterPointsUSGS"]["reproj_thresh_absolute"]

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ReprojectionError)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
        if thresh < reproj_thresh_absolute:
            thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        self.doc.chunk.optimizeCameras(
            adaptive_fitting=self.cfg["optimizeCameras"]["adaptive_fitting"]
        )

        # get an ending time stamp
        timer1b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time1 = diff_time(timer1b, timer1a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflow.sep.join(["USGS filter points part 2", time1]) + "\n"
            )

        self.doc.save()

    def classify_ground_points(self):

        # get a beginning time stamp for the next step
        timer_a = time.time()

        self.doc.chunk.point_cloud.classifyGroundPoints(
            max_angle=self.cfg["classifyGroundPoints"]["max_angle"],
            max_distance=self.cfg["classifyGroundPoints"]["max_distance"],
            cell_size=self.cfg["classifyGroundPoints"]["cell_size"],
        )

        # get an ending time stamp for the previous step
        timer_b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time_tot = diff_time(timer_b, timer_a)

        self.doc.save()

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflow.sep.join(["Classify Ground Points", time_tot]) + "\n"
            )

    def build_depth_maps(self):
        ### Build depth maps

        # get a beginning time stamp for the next step
        timer2a = time.time()

        # build depth maps only instead of also building the point cloud ##?? what does
        self.doc.chunk.buildDepthMaps(
            downscale=self.cfg["buildDepthMaps"]["downscale"],
            filter_mode=self.cfg["buildDepthMaps"]["filter_mode"],
            reuse_depth=self.cfg["buildDepthMaps"]["reuse_depth"],
            max_neighbors=self.cfg["buildDepthMaps"]["max_neighbors"],
            subdivide_task=self.cfg["subdivide_task"],
        )

        # get an ending time stamp for the previous step
        timer2b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time2 = diff_time(timer2b, timer2a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflow.sep.join(["Build Depth Maps", time2]) + "\n")

        self.doc.save()

    def build_point_cloud(self):
        """
        Build point cloud
        """

        ### Build point cloud

        # get a beginning time stamp for the next step
        timer3a = time.time()

        # build point cloud
        self.doc.chunk.buildPointCloud(
            max_neighbors=self.cfg["buildPointCloud"]["max_neighbors"],
            keep_depth=self.cfg["buildPointCloud"]["keep_depth"],
            subdivide_task=self.cfg["subdivide_task"],
            point_colors=True,
        )

        # get an ending time stamp for the previous step
        timer3b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time3 = diff_time(timer3b, timer3a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflow.sep.join(["Build Point Cloud", time3]) + "\n")

        self.doc.save()

        # classify ground points if specified
        if self.cfg["buildPointCloud"]["classify_ground_points"]:
            self.classify_ground_points()

        ### Export points

        if self.cfg["buildPointCloud"]["export"]:

            output_file = os.path.join(
                self.cfg["output_path"], self.run_id + "_points.laz"
            )

            if self.cfg["buildPointCloud"]["classes"] == "ALL":
                # call without classes argument (Metashape then defaults to all classes)
                self.doc.chunk.exportPointCloud(
                    path=output_file,
                    source_data=Metashape.PointCloudData,
                    format=Metashape.PointCloudFormatLAS,
                    crs=Metashape.CoordinateSystem(self.cfg["project_crs"]),
                    subdivide_task=self.cfg["subdivide_task"],
                )
            else:
                # call with classes argument
                self.doc.chunk.exportPointCloud(
                    path=output_file,
                    source_data=Metashape.PointCloudData,
                    format=Metashape.PointCloudFormatLAZ,
                    crs=Metashape.CoordinateSystem(self.cfg["project_crs"]),
                    clases=self.cfg["buildPointCloud"]["classes"],
                    subdivide_task=self.cfg["subdivide_task"],
                )

        return True

    def build_model(self):
        """
        Build and export the model
        """

        start_time = time.time()
        # Build the mesh
        self.doc.chunk.buildModel(
            surface_type=Metashape.Arbitrary,
            interpolation=Metashape.EnabledInterpolation,
            face_count=self.cfg["buildModel"]["face_count"],
            face_count_custom=self.cfg["buildModel"][
                "face_count_custom"
            ],  # Only used if face_count is custom
            source_data=Metashape.DepthMapsData,
        )

        time_taken = diff_time(time.time(), start_time)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflow.sep.join(["Build Model", time_taken]) + "\n")

        # Save the model
        self.doc.save()

        if self.cfg["buildModel"]["export_georeferenced"]:
            output_file = os.path.join(
                self.cfg["output_path"],
                self.run_id
                + "_model_georeferenced."
                + self.cfg["buildModel"]["export_extension"],
            )
            self.doc.chunk.exportModel(path=output_file)

        if self.cfg["buildModel"]["export_local"]:
            # Wipe the CRS and transform so it aligns with the cameras
            # The approach was recommended here: https://www.agisoft.com/forum/index.php?topic=8210.0
            old_crs = self.doc.chunk.crs
            old_transform_matrix = self.doc.chunk.transform.matrix
            # Wipe the transform
            self.doc.chunk.crs = None
            self.doc.chunk.transform.matrix = None

            # Export the transform
            if self.cfg["buildModel"]["export_transform"]:
                output_file = os.path.join(
                    self.cfg["output_path"],
                    self.run_id + "_local_model_transform.csv",
                )

                with open(output_file, "w") as fileh:
                    # This is a row-major representation
                    transform_tuple = tuple(old_transform_matrix)
                    # Write each row in the the transform
                    for i in range(4):
                        fileh.write(
                            ", ".join(str(transform_tuple[i * 4 : (i + 1) * 4]))
                        )

            # Export the model
            output_file = os.path.join(
                self.cfg["output_path"],
                self.run_id
                + "_model_local."
                + self.cfg["buildModel"]["export_extension"],
            )
            self.doc.chunk.exportModel(path=output_file)

            # Reset CRS and transform
            self.doc.chunk.crs = old_crs
            self.doc.chunk.transform.matrix = old_transform_matrix

            self.doc.open(self.doc.path)

        return True

    def build_dem_orthomosaic(self):
        """
        Build end export DEM
        """

        # classify ground points if specified
        if self.cfg["buildDem"]["classify_ground_points"]:
            self.classify_ground_points()

        if self.cfg["buildDem"]["enabled"]:
            # prepping params for buildDem
            projection = Metashape.OrthoProjection()
            projection.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])

            # prepping params for export
            compression = Metashape.ImageCompression()
            compression.tiff_big = self.cfg["buildDem"]["tiff_big"]
            compression.tiff_tiled = self.cfg["buildDem"]["tiff_tiled"]
            compression.tiff_overviews = self.cfg["buildDem"]["tiff_overviews"]

            if "DSM-ptcloud" in self.cfg["buildDem"]["surface"]:
                start_time = time.time()

                # call without point classes argument (Metashape then defaults to all classes)
                self.doc.chunk.buildDem(
                    source_data=Metashape.PointCloudData,
                    subdivide_task=self.cfg["subdivide_task"],
                    projection=projection,
                    resolution=self.cfg["buildDem"]["resolution"],
                )

                time_taken = diff_time(time.time(), start_time)

                self.doc.chunk.elevation.label = "DSM-ptcloud"

                # record results to file
                with open(self.log_file, "a") as file:
                    file.write(
                        MetashapeWorkflow.sep.join(["Build DSM-ptcloud", time_taken])
                        + "\n"
                    )

                output_file = os.path.join(
                    self.cfg["output_path"], self.run_id + "_dsm-ptcloud.tif"
                )
                if self.cfg["buildDem"]["export"]:
                    self.doc.chunk.exportRaster(
                        path=output_file,
                        projection=projection,
                        nodata_value=self.cfg["buildDem"]["nodata"],
                        source_data=Metashape.ElevationData,
                        image_compression=compression,
                    )
                    
            if "DTM-ptcloud" in self.cfg["buildDem"]["surface"]:

                start_time = time.time()

                # call with point classes argument to specify ground points only
                self.doc.chunk.buildDem(
                    source_data=Metashape.PointCloudData,
                    classes=Metashape.PointClass.Ground,
                    subdivide_task=self.cfg["subdivide_task"],
                    projection=projection,
                    resolution=self.cfg["buildDem"]["resolution"],
                )

                time_taken = diff_time(time.time(), start_time)

                self.doc.chunk.elevation.label = "DTM-ptcloud"

                # record results to file
                with open(self.log_file, "a") as file:
                    file.write(
                        MetashapeWorkflow.sep.join(["Build DTM-ptcloud", time_taken])
                        + "\n"
                    )

                output_file = os.path.join(
                    self.cfg["output_path"], self.run_id + "_dtm-ptcloud.tif"
                )
                if self.cfg["buildDem"]["export"]:
                    self.doc.chunk.exportRaster(
                        path=output_file,
                        projection=projection,
                        nodata_value=self.cfg["buildDem"]["nodata"],
                        source_data=Metashape.ElevationData,
                        image_compression=compression,
                    )

            if "DSM-mesh" in self.cfg["buildDem"]["surface"]:

                start_time = time.time()

                self.doc.chunk.buildDem(
                    source_data=Metashape.ModelData,
                    subdivide_task=self.cfg["subdivide_task"],
                    projection=projection,
                    resolution=self.cfg["buildDem"]["resolution"],
                )

                time_taken = diff_time(time.time(), start_time)

                self.doc.chunk.elevation.label = "DSM-mesh"

                # record results to file
                with open(self.log_file, "a") as file:
                    file.write(
                        MetashapeWorkflow.sep.join(["Build DSM-mesh", time_taken])
                        + "\n"
                    )

                output_file = os.path.join(
                    self.cfg["output_path"], self.run_id + "_dsm-mesh.tif"
                )
                if self.cfg["buildDem"]["export"]:
                    self.doc.chunk.exportRaster(
                        path=output_file,
                        projection=projection,
                        nodata_value=self.cfg["buildDem"]["nodata"],
                        source_data=Metashape.ElevationData,
                        image_compression=compression,
                    )

        if self.cfg["buildOrthomosaic"]["enabled"]:
            for surface in self.cfg["buildOrthomosaic"]["surface"]:
                if surface == "Mesh":
                    self.build_export_orthomosaic(from_mesh=True, file_ending="mesh")
                else:
                    dem_found = False
                    for elevation in self.doc.chunk.elevations:
                        if elevation.label == surface:
                            # Activate the appropriate DEM
                            self.doc.chunk.elevation = elevation
                            dem_found = True
                            break

                    if not dem_found:
                        raise ValueError(f"Error: DEM for {surface} is not available.")
                    
                    self.build_export_orthomosaic(file_ending=surface.lower())

        if self.cfg["buildPointCloud"]["remove_after_export"]:
            self.doc.chunk.remove(self.doc.chunk.point_clouds)

        self.doc.save()

        return True

    def build_export_orthomosaic(self, file_ending, from_mesh=False):
        """
        Helper function called by build_dem_orthomosaic. build_export_orthomosaic builds and exports an ortho based on the current elevation data.
        build_dem_orthomosaic sets the current elevation data and calls build_export_orthomosaic (one or more times depending on how many orthomosaics requested)

        Note that we have tried using the 'resolution' parameter of buildOrthomosaic, but it does not have any effect. An orthomosaic built onto a DSM always has a reslution of 1/4 the DSM, and one built onto the mesh has a resolution of ~the GSD.
        """

        # get a beginning time stamp for the next step
        timer6a = time.time()

        # prepping params for buildDem
        projection = Metashape.OrthoProjection()
        projection.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])

        if from_mesh:
            surface_data = Metashape.ModelData
        else:
            surface_data = Metashape.ElevationData

        self.doc.chunk.buildOrthomosaic(
            surface_data=surface_data,
            blending_mode=self.cfg["buildOrthomosaic"]["blending"],
            fill_holes=self.cfg["buildOrthomosaic"]["fill_holes"],
            refine_seamlines=self.cfg["buildOrthomosaic"]["refine_seamlines"],
            subdivide_task=self.cfg["subdivide_task"],
            projection=projection,
        )

        # get an ending time stamp for the previous step
        timer6b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time6 = diff_time(timer6b, timer6a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflow.sep.join(["Build Orthomosaic", time6]) + "\n")

        self.doc.save()

        ## Export orthomosaic
        if self.cfg["buildOrthomosaic"]["export"]:
            output_file = os.path.join(
                self.cfg["output_path"], self.run_id + "_ortho_" + file_ending + ".tif"
            )

            compression = Metashape.ImageCompression()
            compression.tiff_big = self.cfg["buildOrthomosaic"]["tiff_big"]
            compression.tiff_tiled = self.cfg["buildOrthomosaic"]["tiff_tiled"]
            compression.tiff_overviews = self.cfg["buildOrthomosaic"]["tiff_overviews"]

            projection = Metashape.OrthoProjection()
            projection.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])

            self.doc.chunk.exportRaster(
                path=output_file,
                projection=projection,
                nodata_value=self.cfg["buildOrthomosaic"]["nodata"],
                source_data=Metashape.OrthomosaicData,
                image_compression=compression,
            )

        if self.cfg["buildOrthomosaic"]["remove_after_export"]:
            self.doc.chunk.remove(self.doc.chunk.orthomosaics)

        return True

    def add_align_secondary_photos(self):
        """
        Add and align a second set of photos, to be aligned only. The main use case for this currently
        is to be able to build all photogrammetry products from the primary set of photos (e.g., a nadir
        mission), but to also estimate the positions of a secondary set of photos (e.g., oblique photos)
        to use for multiview object detection/classification.
        """

        if self.cfg["alignPhotos"]["reset_alignment"] == True:
            raise ValueError(
                "For aligning secondary photos, reset_alignment must be False."
            )
        if self.cfg["alignPhotos"]["keep_keypoints"] == False:
            raise ValueError(
                "For aligning secondary photos, keep_keypoints must be True."
            )

        # get a beginning time stamp for the next step
        timer2a = time.time()

        # Add the secondary photos
        self.add_photos(secondary=True)

        # get an ending time stamp for the previous step
        timer2b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time2 = diff_time(timer2b, timer2a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflow.sep.join(["Add secondary photos", time2]) + "\n"
            )

        # Save the transform matrix
        matrix_saved = self.doc.chunk.transform.matrix

        # Align the secondary photos (really, align all photos, but only the secondary photos will be
        # affected because Metashape only matches and aligns photos that were not already
        # matched/aligned, assuming keep_keypoints and reset_alignment were set as required).
        self.align_photos()

        # Restore the saved transform matrix
        self.doc.chunk.transform.matrix = matrix_saved

        self.doc.save()

    def export_report(self):
        """
        Export report
        """

        output_file = os.path.join(self.cfg["output_path"], self.run_id + "_report.pdf")

        self.doc.chunk.exportReport(path=output_file)

        return True

    def finish_run(self):
        """
        Finish run (i.e., write completed time to log)
        """

        # finish local results log and close it for the last time
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflow.sep.join(["Run Completed", stamp_time()]) + "\n"
            )

        # open run configuration again. We can't just use the existing self.cfg file because its objects had already been converted to Metashape objects (they don't write well)
        with open(self.config_file) as file:
            config_full = yaml.safe_load(file)

        # write the run configuration to the log file
        with open(self.log_file, "a") as file:
            file.write("\n\n### CONFIGURATION ###\n")
            documents = yaml.dump(config_full, file, default_flow_style=False)
            file.write("### END CONFIGURATION ###\n")

        return True
