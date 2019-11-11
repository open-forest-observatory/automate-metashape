"""
Created on Mon Oct 21 13:45:15 2019

@author: Alex Mandel

"""# Simplified version of benchmark script
# Runs only one project; does not need pre-existing Metashape project files; 

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
# If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup
import Metashape


#### Helper functions and globals

# Set the log file name-value separator
# Chose ; as : is in timestamps
# TODO: Consider moving log to json formatting using a dict
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

#### Functions for each major step in Metashape

def project_setup(cfg):
    '''
    Create output and project paths, if they don't exist
    Define a project ID based on photoset name and timestamp
    Define a project filename and a log filename
    Create the project
    Start a log file
    '''
    
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
    
    ## Project file example to make: "01c_ChipsA_YYYYMMDD-jobid.psx"
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
    
    # Save doc (necessary for steps after point cloud because there needs to be a project file)
    doc.save(project_file)
    
    # Initialize a chunk, set its CRS as specified
    chunk = doc.addChunk()
    chunk.crs = Metashape.CoordinateSystem(cfg["project_crs"])
    
    
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
    Add photos to project
    
    '''

    ## Get paths to all the project photos
    a = glob.iglob(os.path.join(cfg["photo_path"],"**","*.[jJ][pP][gG]"))
    b = [path for path in a]
    photo_files = b
    
    ## Add them
    doc.chunk.addPhotos(photo_files)
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
    doc.chunk.matchPhotos(accuracy=cfg["alignPhotos"]["accuracy"])
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
    
    # Includes adaptive camera model fitting. I set it to optimize all parameters even though the defaults exclude a few.
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
    doc.chunk.buildDepthMaps(quality=cfg["buildDepthMaps"]["quality"], filter=cfg["buildDepthMaps"]["filter"], reuse_depth = cfg["buildDepthMaps"]["reuse_depth"], max_neighbors = cfg["buildDepthMaps"]["max_neighbors"])
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
    
    if cfg["buildDem"]["classes"] == "ALL":
        # call without classes argument (Metashape then defaults to all classes)
        doc.chunk.buildDem(source = cfg["buildDem"]["source"],
                           projection = Metashape.CoordinateSystem(cfg["project_crs"]))
    else:
        # call with classes argument
        doc.chunk.buildDem(source = cfg["buildDem"]["source"],
                           projection = Metashape.CoordinateSystem(cfg["project_crs"]),
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
    doc.chunk.buildOrthomosaic(surface=cfg["buildOrthomosaic"]["surface"],
                               blending=cfg["buildOrthomosaic"]["blending"],
                               fill_holes=cfg["buildOrthomosaic"]["fill_holes"],
                               refine_seamlines=cfg["buildOrthomosaic"]["refine_seamlines"],
                               projection=Metashape.CoordinateSystem(cfg["project_crs"]))
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
    
    doc.chunk.exportDem(path=output_file, tiff_big = cfg["exportDem"]["tiff_big"],
                    tiff_tiled = cfg["exportDem"]["tiff_tiled"],
                    projection = Metashape.CoordinateSystem(cfg["project_crs"]),
                    nodata=cfg["exportDem"]["nodata"],
                    tiff_overviews=cfg["exportDem"]["tiff_overviews"])

    return True



def export_orthomosaic(doc, log_file, run_id, cfg):
    '''
    Export Orthomosaic
    '''
    
    output_file = os.path.join(cfg["output_path"], run_id+'_ortho.tif')
    
    doc.chunk.exportOrthomosaic(path=output_file, tiff_big = cfg["exportDem"]["tiff_big"],
                    tiff_tiled = cfg["exportDem"]["tiff_tiled"],
                    projection = Metashape.CoordinateSystem(cfg["project_crs"]),
                    tiff_overviews=cfg["exportDem"]["tiff_overviews"])

    return True



def export_points(doc, log_file, run_id, cfg):
    '''
    Export points
    '''
        
    output_file = os.path.join(cfg["output_path"], run_id+'_points.las')
    
    if cfg["exportPoints"]["classes"] == "ALL":
        # call without classes argument (Metashape then defaults to all classes)
        doc.chunk.exportPoints(path = output_file,
                   source = cfg["exportPoints"]["source"],
                   precision = cfg["exportPoints"]["precision"],
                   format = Metashape.PointsFormatLAS,
                   projection = Metashape.CoordinateSystem(cfg["project_crs"]))
    else: 
        # call with classes argument
        doc.chunk.exportPoints(path = output_file,
                           source = cfg["exportPoints"]["source"],
                           precision = cfg["exportPoints"]["precision"],
                           format = Metashape.PointsFormatLAS,
                           projection = Metashape.CoordinateSystem(cfg["project_crs"]),
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
