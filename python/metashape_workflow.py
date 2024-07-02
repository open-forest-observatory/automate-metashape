# -*- coding: utf-8 -*-
# File for running a metashape workflow

# Derek Young and Alex Mandel
# University of California, Davis
# 2021

import sys

# ---- If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

## Define where to get the config file (only used if running interactively)
manual_config_file = "config/example_dev.yml"
# ---- If not running interactively, the config file should be supplied as the command-line argument after the python script, e.g.: python metashape_workflow.py config.yml


# Load custom modules and config file: slightly different depending whether running interactively or via command line
try:  # running interactively (in linux) or command line (windows)
    from python.metashape_workflow_functions import MetashapeWorkflow
except:  # running from command line (in linux) or interactively (windows)
    from metashape_workflow_functions import MetashapeWorkflow

if sys.stdin.isatty():
    config_file = sys.argv[1]
else:
    config_file = manual_config_file

meta = MetashapeWorkflow(config_file)

### Run the Metashape workflow

meta.project_setup()

meta.enable_and_log_gpu()

if (meta.cfg["photo_path"] != "") and (
    meta.cfg["addPhotos"]["enabled"]
):  # only add photos if there is a photo directory listed
    meta.add_photos()

if meta.cfg["calibrateReflectance"]["enabled"]:
    meta.calibrate_reflectance()

if meta.cfg["alignPhotos"]["enabled"]:
    meta.align_photos()
    meta.reset_region()

if meta.cfg["filterPointsUSGS"]["enabled"]:
    meta.filter_points_usgs_part1()
    meta.reset_region()

if meta.cfg["addGCPs"]["enabled"]:
    meta.add_gcps()
    meta.reset_region()

if meta.cfg["optimizeCameras"]["enabled"]:
    meta.optimize_cameras()
    meta.reset_region()

if meta.cfg["filterPointsUSGS"]["enabled"]:
    meta.filter_points_usgs_part2()
    meta.reset_region()

if meta.cfg["buildDepthMaps"]["enabled"]:
    meta.build_depth_maps()

if meta.cfg["buildPointCloud"]["enabled"]:
    meta.build_point_cloud()

if meta.cfg["buildModel"]["enabled"]:
    meta.build_model()

# For this step, the check for whether it is enabled in the config happens inside the function, because there are two steps (DEM and ortho), each of which can be enabled independently
meta.build_dem_orthomosaic()

if meta.cfg["photo_path_secondary"] != "":
    meta.add_align_secondary_photos()

meta.export_report()

meta.finish_run()
