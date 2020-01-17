# -*- coding: utf-8 -*-
# File for running a metashape workflow

# Derek Young and Alex Mandel
# University of California, Davis
# 2019

import sys

# ---- If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

## Define where to get the config file (only used if running interactively)
manual_config_file = "config/example_altum2.yml"
# ---- If not running interactively, the config file should be supplied as the command-line argument after the python script, e.g.: python metashape_control.py config.yml


## Load custom modules and config file: slightly different depending whether running interactively or via command line
try:  # running interactively
    from python import metashape_pipeline_functions as meta
    from python import read_yaml
    config_file = manual_config_file
except:  # running from command line
    import metashape_pipeline_functions as meta
    import read_yaml
    config_file = sys.argv[1]

## Parse the config file
cfg = read_yaml.read_yaml(config_file)

### Run the Metashape workflow

doc, log, run_id = meta.project_setup(cfg)

meta.enable_and_log_gpu(log)

if cfg["load_project"] == "":  # only add photos if this is a brand new project, not based off an existing project
    meta.add_photos(doc, cfg)

if cfg["calibrateReflectance"]["enabled"]:
    meta.calibrate_reflectance(doc, cfg)

if cfg["addGCPs"]["enabled"]:
    meta.add_gcps(doc, cfg)

if cfg["alignPhotos"]["enabled"]:
    meta.align_photos(doc, log, cfg)

if cfg["optimizeCameras"]["enabled"]:
    meta.optimize_cameras(doc, cfg)

if cfg["buildDenseCloud"]["enabled"]:
    meta.build_dense_cloud(doc, log, cfg)

if cfg["classifyGroundPoints"]["enabled"]:
    meta.classify_ground_points(doc, log, cfg)

if cfg["buildDem"]["enabled"]:
    meta.build_dem(doc, log, cfg)

if cfg["importDem"]["enabled"]:
    meta.import_dem(doc, log, cfg)

if cfg["buildOrthomosaic"]["enabled"]:
    meta.build_orthomosaic(doc, log, cfg)

if cfg["exportDem"]["enabled"]:
    meta.export_dem(doc, log, run_id, cfg)

if cfg["exportOrthomosaic"]["enabled"]:
    meta.export_orthomosaic(doc, log, run_id, cfg)

if cfg["exportPoints"]["enabled"]:
    meta.export_points(doc, log, run_id, cfg)

meta.export_report(doc, run_id, cfg)

meta.finish_run(log)
