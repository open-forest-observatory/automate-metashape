"""
Created on Mon Oct 21 13:45:15 2019

@author: Alex Mandel
"""

import Metashape
import yaml
from metashape_workflow_functions import MetashapeWorkflow

# For debugging when running this script directly:
if __name__ == "__main__":

    yml_path = "config/example.yml"
    meta = MetashapeWorkflow(yml_path)
    # with open("config/example.yml",'r') as ymlfile:
    #    cfg = yaml.load(ymlfile)

    # catch = convert_objects(cfg)

    # Get a String value
    Photo_path = meta.cfg["Photo_path"]

    # Get a True/False
    GPU_use = meta.cfg["GPU"]["GPU_use"]

    # Get a Num
    GPU_num = meta.cfg["GPU"]["GPU_num"]

    # Convert a to a Metashape Object
    accuracy = eval(meta.cfg["matchPhotos"]["accuracy"])
