# -*- coding: utf-8 -*-
# File for running a metashape workflow

import argparse
import contextlib
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
        "--project-name",
        help="The identifier for the project. Will be used in naming the project file and output files.",
    )
    parser.add_argument(
        "--project-crs",
        help="CRS EPSG code that project outputs should be in "
        + "(projection should be in meter units and intended for the project area). "
        + "It should be specified in the following format: 'EPSG::<EPSG code>'.",
    )
    parser.add_argument(
        "--step",
        help="Run a single processing step. Valid steps: setup, match_photos, "
        + "align_cameras, build_depth_maps, build_point_cloud, build_mesh, "
        + "build_dem_orthomosaic, match_photos_secondary, align_cameras_secondary, finalize. "
        + "If not specified, runs the full workflow.",
    )

    args = parser.parse_args()
    return args


if __name__ == "__main__":
    args = parse_args()

    # Get the non-None overrides provided on the command line
    override_dict = {k: v for k, v in args.__dict__.items() if v is not None}

    # Initialize the workflow instance with the configuration file and the dictionary representation of
    # CLI overrides
    meta = MetashapeWorkflow(config_file=args.config_file, override_dict=override_dict)

    ### Run the Metashape workflow
    # The argo workflow requires that all stdout is json formatted. Since this isn't the case for the
    # metashape logs, we redirect to standard error. We also catch any exceptions raised during
    # processing so that we can still report the completed output paths as JSON to stdout. We keep
    # track of whether an error occurred with a boolean flag so that we can set the process exit code
    # appropriately.
    metashape_error_occurred = False
    with contextlib.redirect_stdout(sys.stderr):
        # Actually run the processing step
        try:
            if args.step:
                meta.run_step(args.step)
            else:
                meta.run()
        except Exception as e:
            metashape_error_occurred = True
            # TODO make this error message more descriptive
            print(
                "Metashape errored while processing, the completed paths will still be reported. "
                + "The error was: \n"
                + e.__str__()
            )

    # Log where the data files were written as json dict
    print(meta.get_written_paths(as_json=True))

    # Exit with non-zero exit code if a metashape error occurred
    if metashape_error_occurred:
        sys.exit(1)
