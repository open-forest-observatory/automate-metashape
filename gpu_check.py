#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 09:14:50 2019

@author: Alex Mandel

A Quick test if Metashape detects a GPU, and if it's enabled automatically.
"""
import os
import Metashape
import datetime
import platform

folderpath = os.path.expanduser('~/metashape-pro/Puget-Benchmark')

file = open(folderpath+'/Benchmark_Results.txt','a')
# write a line with the Metashape version
file.write('Agisoft Metashape Professional Version: '+Metashape.app.version+'\n')
# write a line with the date and time
file.write('Benchmark Started at '+ datetime.datetime.now().strftime('%H:%M on %B %d, %Y\n'))
# write a line with CPU info - if possible, improve the way the CPU info is found / recorded
file.write('CPU: '+ platform.processor()+'\n')
# write two lines with GPU info: count and model names - this takes multiple steps to make it look clean in the end

gpustringraw = str(Metashape.app.enumGPUDevices())
gpucount = gpustringraw.count("name': '")
file.write('Number of GPUs Found: '+str(gpucount)+'\n')
gpustring = ''
currentgpu = 1
while gpucount >= currentgpu:
    if gpustring != '': gpustring = gpustring+', '
    gpustring = gpustring+gpustringraw.split("name': '")[currentgpu].split("',")[0]
    currentgpu = currentgpu+1
#gpustring = gpustringraw.split("name': '")[1].split("',")[0]
file.write('GPU Model(s): '+gpustring+'\n')

# Write down if the GPU is enabled or not, Bit Mask values
gpu_mask = Metashape.app.gpu_mask
file.write(' '.join(['GPU Mask: ', str(gpu_mask), '\n']))
#file.write('GPU(s): '+str(Metashape.app.enumGPUDevices())+'\n')
file.close()

print(gpustring)
print(gpu_mask)

# Test setting the gpu 
if ((gpucount > 0) and (gpu_mask == 0)):
    Metashape.app.gpu_mask = 1
    
gpu_mask = str(Metashape.app.gpu_mask)
print(gpu_mask)
