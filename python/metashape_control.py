# -*- coding: utf-8 -*-
# File for running a metashape pipeline

# Derek Young and Alex Mandel
# University of California, Davis
# 2019

import sys

### Add the Metashape functionality
# If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

## Define where to get the config file (only used if running interactively)
manual_config_file = "config/example.yml"


## Load custom modules: slightly different depending whether running interactively or via command line
if hasattr(sys,"ps1"): # running interactively
  from python import metashape_pipeline_functions as meta
  from python import read_yaml  
else: # running from command line
    import metashape_pipeline_functions as meta
    import read_yaml
    
## Load config file: slightly different depending whether running interactively or via command line
if hasattr(sys,"ps1"): # running interactively
    config_file = manual_config_file
else: # running from command line
    config_file = sys.argv[1]
    

## Parse the config file
cfg = read_yaml.read_yaml(config_file)

### Run the Metashape workflow
doc, log, run_id = meta.project_setup(cfg)

meta.enable_and_log_gpu(log)

meta.add_photos(doc, cfg)

meta.align_photos(doc, log, cfg)

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
