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
import sys

# import the Metashape functionality (should this come before the line above? seems to work as-is)
import Metashape


#### some helper functions and globals

def stamp_time():
    ''' 
    Format the timestamps as needed
    '''
    stamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')
    return stamp

def diff_time(t2, t1):
    '''
    Give a end and start time, subtract, and round
    '''
    total = str(round(t2-t1, 1))
    return total
    
# Set the log file name value separator
# Chose ; as : is in timestamps
# TODO: Consider moving log to json formatting using a dict
sep = "; "

#### Specify directories

# 1st arg is the path to the project data
if (len(sys.argv) >= 2):
    folderpath = os.path.expanduser(sys.argv[1])
else:
    folderpath = os.path.expanduser('/share/spatial02/latimer/forest_benchmark')

photos_path = os.path.join(folderpath,'raw_images')
photo_files = [file.path for file in os.scandir(photos_path) if file.path.endswith('.jpg')]

# TODO: results should go to a subfolder for a particular benchmark
unique_id = ''.join(['benchmark_', stamp_time().replace(":","")])
# Project Name should be unique so benchmark can be run several times
project_file = os.path.join(folderpath, '.'.join([unique_id, 'psx']) )
log_file = os.path.join(folderpath, '.'.join([unique_id,'txt']) )
output = os.path.join(folderpath, unique_id)
os.mkdir(output)


#### Specify CRS

# Using a UTM Zone for output, current bug in CA Albers
# TODO: Select UTM zone based on EXIF data in the photos.
project_crs = Metashape.CoordinateSystem("EPSG::32610")


#### Create doc, chunk

# create a handle to the Metashape object
doc = Metashape.app.document

# Save doc (necessary for steps after point cloud because there needs to be a project file)
doc.save(project_file)

# Grab the chunk that initialized in the current document, set its CRS to WGS84 / UTM 10N
chunk = doc.addChunk()
chunk.crs = project_crs



#### Log PC specs

# log Metashape version, CPU specs, time, and project location to results file
# open the results file
# TODO: records the Slurm values for actual cpus and ram allocated
# https://slurm.schedmd.com/sbatch.html#lbAI
file = open(log_file,'a')
# write a line with the Metashape version
file.write(sep.join(['Project', os.path.basename(folderpath)])+'\n')
file.write(sep.join(['Agisoft Metashape Professional Version', Metashape.app.version])+'\n')
# write a line with the date and time
file.write(sep.join(['Benchmark Started', stamp_time()]) +'\n')
# write a line with CPU info - if possible, improve the way the CPU info is found / recorded
file.write(sep.join(['Node', platform.node()])+'\n')
file.write(sep.join(['CPU', platform.processor()]) +'\n')
# write two lines with GPU info: count and model names - this takes multiple steps to make it look clean in the end
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



#### Add photos

chunk.addPhotos(photo_files)
doc.save()



#### Align photos

# get a beginning time stamp
timer1a = time.time()

# Align cameras
chunk.matchPhotos(accuracy=Metashape.HighAccuracy, preselection=Metashape.GenericPreselection)
chunk.alignCameras(adaptive_fitting=True)
doc.save()

# get an ending time stamp
timer1b = time.time()

# calculate difference between end and start time to 1 decimal place
time1 = diff_time(timer1b, timer1a)

# record results to file
with open(log_file, 'a') as file:
    file.write(sep.join(['Align Photos', time1])+'\n')




#### Optimize cameras
# Includes adaptive camera model fitting. I set it to optimize all parameters even though the defaults exclude a few.
chunk.optimizeCameras(fit_f=True, fit_cx=True, fit_cy=True, fit_b1=True, fit_b2=True, fit_k1=True, fit_k2=True, fit_k3=True, fit_k4=True, fit_p1=True, fit_p2=True, fit_p3=True, fit_p4=True, adaptive_fitting=True)



#### Build depth maps

# get a beginning time stamp for the next step
timer2a = time.time()

# build depth maps only instead of also building the dense cloud ##?? what does 
chunk.buildDepthMaps(quality=Metashape.MediumQuality, filter=Metashape.MildFiltering)
doc.save()

# get an ending time stamp for the previous step
timer2b = time.time()

# calculate difference between end and start time to 1 decimal place
time2 = diff_time(timer2b, timer2a)

# record results to file
with open(log_file, 'a') as file:
    file.write(sep.join(['Build Depth Maps', time2])+'\n')






#### Build dense cloud

# get a beginning time stamp for the next step
timer3a = time.time()

# build dense cloud
chunk.buildDenseCloud(max_neighbors=60)
doc.save()

# get an ending time stamp for the previous step
timer3b = time.time()

# calculate difference between end and start time to 1 decimal place
time3 = diff_time(timer3b, timer3a)

# record results to file
with open(log_file, 'a') as file:
    file.write(sep.join(['Build Dense Cloud', time3])+'\n')




#### Classify ground points
chunk.dense_cloud.classifyGroundPoints()
doc.save()



#### Build DEM (a DTM)

# get a beginning time stamp for the next step
timer5a = time.time()

# build DEM
chunk.buildDem(projection = project_crs, classes=[Metashape.PointClass.Ground])

# get an ending time stamp for the previous step
timer5b = time.time()

# calculate difference between end and start time to 1 decimal place
time5 = diff_time(timer5b, timer5a)

# record results to file
with open(log_file, 'a') as file:
    file.write(sep.join(['Build DEM', time5])+'\n')

    


#### Build Orthomosaic

# get a beginning time stamp for the next step
timer6a = time.time()

# build orthomosaic
chunk.buildOrthomosaic(projection = project_crs, refine_seamlines = True)
doc.save()

# get an ending time stamp for the previous step
timer6b = time.time()

# calculate difference between end and start time to 1 decimal place
time6 = diff_time(timer6b, timer6a)

# record results to file
with open(log_file, 'a') as file:
    file.write(sep.join(['Build Orthomosaic', time6])+'\n')

    


#### Export dem, ortho, las, report
timer7a = time.time()
chunk.exportDem(os.path.join(output, 'DTM.tif'), tiff_big = True, tiff_tiled = False, projection = project_crs)
timer7b = time.time()
chunk.exportOrthomosaic(os.path.join(output, 'ortho.tif'), tiff_big = True, tiff_tiled = False, projection = project_crs)
timer7c = time.time()
chunk.exportPoints(os.path.join(output, 'points.las'), format = Metashape.PointsFormatLAS, projection = project_crs)
timer7d = time.time()
chunk.exportReport(os.path.join(output, 'report.pdf'))
timer7e = time.time()

with open(log_file, 'a') as file:
    file.write(sep.join(['DEM Export', diff_time(timer7b, timer7a)])+'\n')
    file.write(sep.join(['Ortho Export', diff_time(timer7c, timer7b)])+'\n')
    file.write(sep.join(['Las Export', diff_time(timer7d, timer7c)])+'\n')
    file.write(sep.join(['Report', diff_time(timer7e, timer7d)])+'\n')

#### Finish benchmark

# finish local results log and close it for the last time
with open(log_file, 'a') as file:
    file.write(sep.join(['Benchmark Completed', stamp_time()])+'\n')
