# -*- coding: utf-8 -*-
# File for running a metashape workflow

# Derek Young and Alex Mandel
# University of California, Davis
# 2019

import sys

# ---- If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

## Define where to get the config file (only used if running interactively)
manual_config_file = "config/example.yml"
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

meta.add_photos(doc, cfg)

meta.add_gcps(doc, cfg)

meta.align_photos(doc, log, cfg)

# meta.calibrate_reflectance(doc, cfg)

meta.optimize_cameras(doc, cfg)

meta.build_depth_maps(doc, log, cfg)

meta.build_dense_cloud(doc, log, cfg)

meta.classify_ground_points(doc, log, cfg)

meta.build_dem(doc, log, cfg)

meta.build_orthomosaic(doc, log, cfg)

meta.export_dem(doc, log, run_id, cfg)

meta.export_orthomosaic(doc, log, run_id, cfg)

meta.export_points(doc, log, run_id, cfg)

meta.export_report(doc, run_id, cfg)

meta.finish_run(log)
