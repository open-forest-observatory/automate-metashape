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

# Initialize the workflow instance with the configuration file
meta = MetashapeWorkflow(config_file)

### Run the Metashape workflow
meta.run()
