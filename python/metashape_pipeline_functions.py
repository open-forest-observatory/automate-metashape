# Simplified version of benchmark script
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


#### some helper functions and globals

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
    
# Set the log file name-value separator
# Chose ; as : is in timestamps
# TODO: Consider moving log to json formatting using a dict
sep = "; "


def file_setup(photo_path, project_path, output_path):
    '''
    Create output and project paths, if they don't exist
    Define a project ID based on photoset name and timestamp
    Define a project filename and a log filename
    '''
    
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
        
    ### Set a filename template for project files and output files
    ## Get the first parts of the filename (the photoset ID and location string)
    path_parts = photo_path.split("/")
    photoset_name = path_parts[-1]
    photoset_parts = photoset_name.split("_")
    set_ID = photoset_parts[0]
    location = photoset_parts[1]
    ##?? OK to requre photo folders to be specified as multipart with specific order?
    
    ## Project file example to make: "01c_ChipsA_YYYYMMDD-jobid.psx"
    timestamp = stamp_time()
    project_id = "_".join([timestamp,set_ID,location])
    # TODO: If there is a JobID, append to time (separated with "-", not "_"). ##?? This will keep jobs initiated in the same minute distinct
    # TODO: Allow to specify a mnemonic for the end of the project name (from YAML?)
    
    project_file = os.path.join(project_path, '.'.join([project_id, 'psx']) )
    log_file = os.path.join(output_path, '.'.join(['log_'+project_id,'txt']) )
    ##?? OK to save these as globals?
        
    return True


def initialize_metashape_project(project_file):
    '''
    Create a doc and a chunk
    '''

    # create a handle to the Metashape object
    doc = Metashape.Document() #When running via Metashape, can use: doc = Metashape.app.document 
    
    # Save doc (necessary for steps after point cloud because there needs to be a project file)
    doc.save(project_file)
    
    # Initialize a chunk, set its CRS as specified
    chunk = doc.addChunk()
    chunk.crs = project_crs
    
    return True



def log_pc_specs():
    '''
    Log specs except for GPU
    '''

    # log Metashape version, CPU specs, time, and project location to results file
    # open the results file
    # TODO: records the Slurm values for actual cpus and ram allocated
    # https://slurm.schedmd.com/sbatch.html#lbAI
    file = open(log_file,'a')
    # write a line with the Metashape version
    file.write(sep.join(['Project', project_id])+'\n')
    file.write(sep.join(['Agisoft Metashape Professional Version', Metashape.app.version])+'\n')
    # write a line with the date and time
    file.write(sep.join(['Benchmark Started', stamp_time()]) +'\n')
    # write a line with CPU info - if possible, improve the way the CPU info is found / recorded
    file.write(sep.join(['Node', platform.node()])+'\n')
    file.write(sep.join(['CPU', platform.processor()]) +'\n')
    # write two lines with GPU info: count and model names - this takes multiple steps to make it look clean in the end

    return True

def enable_and_log_gpu():
    '''
    Enables GPU and logs GPU specs
    '''
    
    gpustringraw = str(Metashape.app.enumGPUDevices())
    gpucount = gpustringraw.count("name': '")
    file.write(sep.join(['Number of GPUs Found', str(gpucount)]) +'\n')
    gpustring = ''
    currentgpu = 1
    while gpucount >= currentgpu:
        if gpustring != '': gpustring = gpustring+', '
        gpustring = gpustring+gpustringraw.split("name': '")[currentgpu].split("',")[0]
        currentgpu = currentgpu+1
    #gpustring = gpustringraw.split("name': '")[1].split("',")[0]
    file.write(sep.join(['GPU Model', gpustring])+'\n')
    
    # Write down if the GPU is enabled or not, Bit Mask values
    gpu_mask = Metashape.app.gpu_mask
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
    
    file.close()
    
    return True



def add_photos(photo_path):
    '''
    Add photos to project
    
    '''

    ## Get paths to all the project photos
    a = glob.iglob(os.path.join(photo_path,"**","*.[jJ][pP][gG]"))
    b = [path for path in a]
    photo_files = b
    
    ## Add them
    chunk.addPhotos(photo_files)
    doc.save()
    
    return True


def align_photos(accuracy, adaptive_fitting):
    '''
    Match photos, align cameras, optimize cameras
    '''
    
    #### Align photos
    
    # get a beginning time stamp
    timer1a = time.time()
    
    # Align cameras
    chunk.matchPhotos(accuracy=accuracy)
    chunk.alignCameras(adaptive_fitting=adaptive_fitting)
    doc.save()
    
    # get an ending time stamp
    timer1b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time1 = diff_time(timer1b, timer1a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Align Photos', time1])+'\n')
        
    return True



def optimize_cameras(adaptive_fitting):
    '''
    Optimize cameras
    '''
    
    # Includes adaptive camera model fitting. I set it to optimize all parameters even though the defaults exclude a few.
    chunk.optimizeCameras(adaptive_fitting=adaptive_fitting)

    return True



def build_depth_maps(quality, filter, reuse_depth, max_neighbors):
    '''
    Build depth maps
    '''

    # get a beginning time stamp for the next step
    timer2a = time.time()
    
    # build depth maps only instead of also building the dense cloud ##?? what does 
    chunk.buildDepthMaps(quality=quality, filter=filter, reuse_depth = reuse_depth, max_neighbors = max_neighbors)
    doc.save()
    
    # get an ending time stamp for the previous step
    timer2b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time2 = diff_time(timer2b, timer2a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Depth Maps', time2])+'\n')
        
    return True




def build_dense_cloud(max_neighbors):
    '''
    Build dense cloud
    '''

    # get a beginning time stamp for the next step
    timer3a = time.time()
    
    # build dense cloud
    chunk.buildDenseCloud(max_neighbors=max_neighbors)
    doc.save()
    
    # get an ending time stamp for the previous step
    timer3b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time3 = diff_time(timer3b, timer3a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Dense Cloud', time3])+'\n')
        
    return True



def classify_ground_points(max_angle, max_distance, cell_size, source):
    '''
    Classify ground points
    '''
    
    chunk.dense_cloud.classifyGroundPoints(max_angle=max_angle, max_distance=max_distance, cell_size=cell_size, source=source)
    doc.save()
    
    return True


def build_dem(source, projection, classes):
    '''
    Build DEM
    '''
    
    # get a beginning time stamp for the next step
    timer5a = time.time()
    
    # build DEM
    chunk.buildDem(projection = projection, classes=classes)
    
    # get an ending time stamp for the previous step
    timer5b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time5 = diff_time(timer5b, timer5a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build DEM', time5])+'\n')
        
    return True

    

def build_orthomosaic(surface, blending, fill_holes, refine_seamlines, projection):
    '''
    Build orthomosaic
    '''
    
    # get a beginning time stamp for the next step
    timer6a = time.time()
    
    # build orthomosaic
    chunk.buildOrthomosaic(surface=surface, blending=blending, fill_holes=fill_holes, refine_seamlines=refine_seamlines, projection=projection)
    doc.save()
    
    # get an ending time stamp for the previous step
    timer6b = time.time()
    
    # calculate difference between end and start time to 1 decimal place
    time6 = diff_time(timer6b, timer6a)
    
    # record results to file
    with open(log_file, 'a') as file:
        file.write(sep.join(['Build Orthomosaic', time6])+'\n')
        
    return True

    

def export_dem(path, tiff_big, tiff_tiled, image_format, projection, nodata, tiff_overviews):
    '''
    Export DEM
    '''
    
    output_file = os.path.join(path, project_id+'_dem.tif')
    
    chunk.exportDem(path=output_file, tiff_big = tiff_big, tiff_tiled = tiff_tiled, projection = projection, nodata=nodata, tiff_overviews=tiff_overviews)

    return True

def export_orthomosaic(path, tiff_big, tiff_tiled, image_format, projection, nodata, tiff_overviews):
    '''
    Export Orthomosaic
    '''
    
    output_file = os.path.join(path, project_id+'_ortho.tif')
    
    chunk.exportOrthomosaic(path=output_file, tiff_big = tiff_big, tiff_tiled = tiff_tiled, projection = projection, tiff_overviews=tiff_overviews)

    return True


def export_points(path, source, precision, format, projection, classes):
    '''
    Export points
    '''
    
    output_file = os.path.join(path, project_id+'_points.las')
    
    chunk.exportPoints(path = output_file, source = source, precision = precision, format = format, projection = projection, clases = classes)

    return True

def export_report(path):
    '''
    Export report
    '''
    
    output_file = os.path.join(path, project_id+'_report.pdf')

    chunk.exportReport(path = output_file)
    
    return True



def finish_run():
    '''
    Finish run (i.e., write completed time to log)
    '''
    
    # finish local results log and close it for the last time
    with open(log_file, 'a') as file:
        file.write(sep.join(['Run Completed', stamp_time()])+'\n')
        
    return True
