# Derek Young and Alex Mandel
# University of California, Davis
# 2019

#### Import libraries

# import the fuctionality we need to make time stamps to measure performance
import time
import datetime
import platform
import os
import glob

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
    
    if (cfg["photoset_id"] == "%lookup%") or cfg["location"] == "%lookup%":
        path_parts = cfg["photo_path"].split("/")
        photoset_name = path_parts[-1]
        photoset_parts = photoset_name.split("_")
    
    if cfg["photoset_id"] == "%lookup%":
        set_id = photoset_parts[0]
    else:
        set_id = cfg["photoset_id"]
        
    if cfg["location"] == "%lookup%":
        location = photoset_parts[1]
    else:
        location = cfg["location"]
    
    ## Project file example to make: "01c_ChipsA_YYYYMMDDtHHMM-jobid.psx"
    timestamp = stamp_time()
    # TODO: allow a nonexistent location string
    run_id = "_".join([timestamp,set_id,location])
    # TODO: If there is a JobID, append to time (separated with "-", not "_"). ##?? This will keep jobs initiated in the same minute distinct
    # TODO: Allow to specify a mnemonic for the end of the project name (from YAML?)
    
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
        chunk.marker_crs = Metashape.CoordinateSystem(cfg["gcp_crs"])

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
    a = glob.iglob(os.path.join(cfg["photo_path"],"**","*.[jJ][pP][gG]"))
    b = [path for path in a]
    photo_files = b
    
    ## Add them
    doc.chunk.addPhotos(photo_files)

    ## Need to change the label on each camera so that it includes the containing folder
    for camera in doc.chunk.cameras:
        path = camera.photo.path
        path_parts = path.split("/")[-2:]
        newlabel = "/".join(path_parts)
        camera.label = newlabel

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
        marker_label = marker_label[1:-1]  # need to get it out of the two pairs of quotes
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


def calibrate_reflectance(doc, cfg):
    
    # TODO: Handle failure to find panels, or mulitple panel images by returning error to user.
    doc.chunk.locateReflectancePanels()
    # TODO: Might need full path to calibration csv
    #doc.chunk.loadReflectancePanelCalibration("calibration/RP04-1923118-OB.csv")
    doc.chunk.loadReflectancePanelCalibration(cfg["calibrateReflectance"]["panel_path"])
    #doc.chunk.calibrateReflectance(use_reflectance_panels=True,use_sun_sensor=True)
    doc.chunk.calibrateReflectance(use_reflectance_panels=["calibrateReflectance"]["use_reflectance_panels"],
                                   use_sun_sensor=["calibrateReflectance"]["use_sun_sensor"])
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
    doc.chunk.matchPhotos(downscale=cfg["alignPhotos"]["downscale"])
    doc.chunk.alignCameras(adaptive_fitting=cfg["alignPhotos"]["adaptive_fitting"])
    doc.save()
    
    # get an ending time stamp
    timer1b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time1 = diff_time(timer1b, timer1a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Align Photos', time1])+'\n')
        
    return True



def optimize_cameras(doc, cfg):
    '''
    Optimize cameras
    '''

    # Disable camera locations as reference if specified in YML
    if cfg["addGCPs"]["enabled"] and cfg["addGCPs"]["optimize_w_gcps_only"]:
        n_cameras = len(doc.chunk.cameras)
        for i in range(1, n_cameras):
            doc.chunk.cameras[i].reference.enabled = False

    # Currently only optimizes the default parameters, which is not all possible parameters
    doc.chunk.optimizeCameras(adaptive_fitting=cfg["optimizeCameras"]["adaptive_fitting"])
    doc.save()

    return True



def build_depth_maps(doc, log_file, cfg):
    '''
    Build depth maps
    '''

    # get a beginning time stamp for the next step
    timer2a = time.time()
    
    # build depth maps only instead of also building the dense cloud ##?? what does 
    doc.chunk.buildDepthMaps(downscale=cfg["buildDepthMaps"]["downscale"], filter_mode=cfg["buildDepthMaps"]["filter_mode"], reuse_depth = cfg["buildDepthMaps"]["reuse_depth"], max_neighbors = cfg["buildDepthMaps"]["max_neighbors"])
    doc.save()
    
    # get an ending time stamp for the previous step
    timer2b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time2 = diff_time(timer2b, timer2a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Depth Maps', time2])+'\n')
        
    return True




def build_dense_cloud(doc, log_file, cfg):
    '''
    Build dense cloud
    '''

    # get a beginning time stamp for the next step
    timer3a = time.time()
    
    # build dense cloud
    doc.chunk.buildDenseCloud(max_neighbors=cfg["buildDenseCloud"]["max_neighbors"],
                          keep_depth = cfg["buildDenseCloud"]["keep_depth"])
    doc.save()
    
    # get an ending time stamp for the previous step
    timer3b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time3 = diff_time(timer3b, timer3a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Dense Cloud', time3])+'\n')
        
    return True



def classify_ground_points(doc, log_file, cfg):
    '''
    Classify ground points
    '''
    
    # get a beginning time stamp for the next step
    timer_a = time.time()
    
    
    
    doc.chunk.dense_cloud.classifyGroundPoints(max_angle=cfg["classifyGroundPoints"]["max_angle"],
                                           max_distance=cfg["classifyGroundPoints"]["max_distance"],
                                           cell_size=cfg["classifyGroundPoints"]["cell_size"])
    doc.save()
    
    # get an ending time stamp for the previous step
    timer_b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time_tot = diff_time(timer_b, timer_a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Classify Ground Points', time_tot])+'\n')
        
    
    return True


def build_dem(doc, log_file, cfg):
    '''
    Build DEM
    '''
    
    # get a beginning time stamp for the next step
    timer5a = time.time()

    projection = Metashape.OrthoProjection
    projection.crs = Metashape.CoordinateSystem(cfg["project_crs"])
    
    if cfg["buildDem"]["classes"] == "ALL":
        # call without classes argument (Metashape then defaults to all classes)
        doc.chunk.buildDem(source_data = cfg["buildDem"]["source"]) # removed projection argument
    else:
        # call with classes argument
        doc.chunk.buildDem(source_data = cfg["buildDem"]["source"],
                           #projection = projection,
                           classes = cfg["buildDem"]["classes"])
    
    # get an ending time stamp for the previous step
    timer5b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time5 = diff_time(timer5b, timer5a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build DEM', time5])+'\n')
        
    return True

    

def build_orthomosaic(doc, log_file, cfg):
    '''
    Build orthomosaic
    '''
    
    # get a beginning time stamp for the next step
    timer6a = time.time()
    
    # build orthomosaic
    doc.chunk.buildOrthomosaic(surface_data=cfg["buildOrthomosaic"]["surface"],
                               blending_mode=cfg["buildOrthomosaic"]["blending"],
                               fill_holes=cfg["buildOrthomosaic"]["fill_holes"],
                               refine_seamlines=cfg["buildOrthomosaic"]["refine_seamlines"])  ## removed: projection=Metashape.CoordinateSystem(cfg["project_crs"])
    doc.save()
    
    # get an ending time stamp for the previous step
    timer6b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time6 = diff_time(timer6b, timer6a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Orthomosaic', time6])+'\n')
        
    return True

    

def export_dem(doc, log_file, run_id, cfg):
    '''
    Export DEM
    '''
    
    output_file = os.path.join(cfg["output_path"], run_id+'_dem.tif')

    Metashape.ImageCompression.tiff_big = cfg["exportDem"]["tiff_big"]
    Metashape.ImageCompression.tiff_tiled = cfg["exportDem"]["tiff_tiled"]
    Metashape.ImageCompression.tiff_overviews = cfg["exportDem"]["tiff_overviews"]
    
    doc.chunk.exportRaster(path=output_file,
                    #projection = Metashape.CoordinateSystem(cfg["project_crs"]),
                    nodata_value=cfg["exportDem"]["nodata"],
                    source_data = Metashape.ElevationData)

    return True



def export_orthomosaic(doc, log_file, run_id, cfg):
    '''
    Export Orthomosaic
    '''
    
    output_file = os.path.join(cfg["output_path"], run_id+'_ortho.tif')

    Metashape.ImageCompression.tiff_big = cfg["exportOrthomosaic"]["tiff_big"]
    Metashape.ImageCompression.tiff_tiled = cfg["exportOrthomosaic"]["tiff_tiled"]
    Metashape.ImageCompression.tiff_overviews = cfg["exportOrthomosaic"]["tiff_overviews"]

    doc.chunk.exportRaster(path=output_file,
                           # projection = Metashape.CoordinateSystem(cfg["project_crs"]),
                           nodata_value=cfg["exportOrthomosaic"]["nodata"],
                           source_data=Metashape.OrthomosaicData)

    return True



def export_points(doc, log_file, run_id, cfg):
    '''
    Export points
    '''
        
    output_file = os.path.join(cfg["output_path"], run_id+'_points.las')
    
    if cfg["exportPoints"]["classes"] == "ALL":
        # call without classes argument (Metashape then defaults to all classes)
        doc.chunk.exportPoints(path = output_file,
                   source_data = cfg["exportPoints"]["source"],
                   #precision = cfg["exportPoints"]["precision"], ### removed in 1.6.0
                   format = Metashape.PointsFormatLAS,
                   crs = Metashape.CoordinateSystem(cfg["project_crs"]))
    else: 
        # call with classes argument
        doc.chunk.exportPoints(path = output_file,
                           source_data = cfg["exportPoints"]["source"],
                           #precision = cfg["exportPoints"]["precision"],  ### removed in 1.6.0
                           format = Metashape.PointsFormatLAS,
                           crs = Metashape.CoordinateSystem(cfg["project_crs"]),
                           clases = cfg["exportPoints"]["classes"])

    return True





def export_report(doc, run_id, cfg):
    '''
    Export report
    '''
    
    output_file = os.path.join(cfg["output_path"], run_id+'_report.pdf')

    doc.chunk.exportReport(path = output_file)
    
    return True



def finish_run(log_file):
    '''
    Finish run (i.e., write completed time to log)
    '''
    
    # finish local results log and close it for the last time
    with open(log_file, 'a') as file:
        file.write(sep.join(['Run Completed', stamp_time()])+'\n')
        
    return True
