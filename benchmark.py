#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jul  8 10:33:12 2019

@author: Alex Mandel

Script to run Benchmark Metashape project with timing
"""

import Metashape
import time
from os import path

# Activate the license, not sure this works right
#if (Metashape.app.activated == False):
#    Metashape.License("")
    
# TODO: Deactivate the license even if the script fails

project = "/home/vulpes/Downloads/metashape-pro/Puget-Benchmark/School Map/School Map Align Photos.psx"
folderpath = path.dirname(project)
projectname = path.basename(project)

doc = Metashape.app.document

# add logging of the project name, type, and image count
file = open(folderpath+'/Benchmark Results.txt','a')
file.write('Project: '+projectname+'\n')
# need to figure out how to count just the images (not project files or subfolders)
# file.write('Image Count: XXX Photos\n')
file.close()

# ALIGN PHOTOS
# open the first version of the project we want to test, in its unprocessed state
doc.open(project, False , True )
chunk = doc.chunk

# get a beginning time stamp
timer1a = time.time()

# match photos
chunk.matchPhotos(accuracy=Metashape.HighAccuracy, generic_preselection=True, reference_preselection=False)

# align cameras
chunk.alignCameras()

# get an ending time stamp
timer1b = time.time()

# calculate difference between end and start time to 1 decimal place
time1 = round(timer1b - timer1a,1)

# record results to file
file = open(folderpath+'/Benchmark Results.txt','a')
file.write('Align Photos: '+str(time1)+'\n')
file.close()
