# -*- coding: utf-8 -*-
# File for running a metashape workflow

# Derek Young and Alex Mandel
# University of California, Davis
# 2021

import argparse
import sys
from pathlib import Path

# ---- If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

## Define where to get the config file (only used if running interactively)
# manual_config_file = "config/config-base.yml"
manual_config_file = Path(
    Path(__file__).parent, "..", "config", "config-base.yml"
).resolve()
# ---- If not running interactively, the config file should be supplied as the command-line argument after the python script, e.g.: python metashape_workflow.py config.yml


# Load custom modules and config file: slightly different depending whether running interactively or via command line
try:  # running interactively (in linux) or command line (windows)
    from python.metashape_workflow_functions import MetashapeWorkflow
except:  # running from command line (in linux) or interactively (windows)
    from metashape_workflow_functions import MetashapeWorkflow


def parse_args():
    parser = argparse.ArgumentParser(
        description="The first required argument is the path to the config file. "
        + "All other arguments are optional overrides to the corresponding entry in that config"
    )
    parser.add_argument(
        "--config_file",
        default=manual_config_file,
        help="A path to a yaml config file.",
    )
    parser.add_argument(
        "--photo-path",
        nargs="+",
        help="One or more absolute paths to load photos from, separated by spaces.",
    )
    parser.add_argument(
        "--photo-path-secondary",
        help="A path to a folder of images to add after alignment. "
        + "For more information, see the description in the example config file.",
    )
    parser.add_argument(
        "--project-path",
        help="Path to save Metashape project file (.psx). Will be created if does not exist",
    )
    parser.add_argument(
        "--output-path",
        help="Path for exports (e.g., points, DSM, orthomosaic) and processing log. "
        + "Will be created if does not exist.",
    )
    parser.add_argument(
        "--run-name",
        help="The identifier for the run. Will be used in naming output files.",
    )
    parser.add_argument(
        "--project-crs",
        help="CRS EPSG code that project outputs should be in "
        + "(projection should be in meter units and intended for the project area). "
        + "It should be specified in the following format: 'EPSG::<EPSG code>'.",
    )

    args = parser.parse_args()
    return args


args = parse_args()

# Initialize the workflow instance with the configuration file and the dictionary representation of
# CLI overrides
meta = MetashapeWorkflow(config_file=args.config_file, override_dict=args.__dict__)

### Run the Metashape workflow
meta.run()
