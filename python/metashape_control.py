# -*- coding: utf-8 -*-
# File for running a metashape pipeline

# Derek Young and Alex Mandel
# University of California, Davis
# 2019

from python import metashape_pipeline_functions
from python import read_yaml

### import the Metashape functionality
# If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup
import Metashape

cfg = read_yaml.read_yaml("config/example.yml")


#### Specify directories
#specifically, drone photo directory, metashape products directory, metashape project directory. 
#the processing log will go into the products directory

## If running interactively, specify directories here:
photo_path = '/storage/forestuav/imagery/missions/01c_ChipsA_120m_thinned22_subset'
output_path = '/storage/forestuav/metashape_outputs/analysis1'
project_path = '/storage/forestuav/metashape_projects/analysis1'

## TODO: Read paths from YAML config file

file_setup(photo_path = photo_path, project_path = project_path, output_path = output_path)

initialize_metashape_project(project_file = project_file) ##?? Is it strange to pass this argument which was created as a global by the previous function?

log_pc_specs()

enable_and_log_gpu()

add_photos(photo_path = photo_path)

align_photos(accuracy = Metashape.MediumAccuracy, adaptive_fitting = True)