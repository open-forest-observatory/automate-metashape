"""
Created on Mon Oct 21 13:45:15 2019

@author: Alex Mandel
"""

import yaml
import Metashape


def convert_objects(a_dict):
    '''
    Based on
    https://stackoverflow.com/a/25896596/237354
    '''
    for k, v in a_dict.items():
        if not isinstance(v, dict):
            if isinstance(v, str):
                # TODO look for Metashape.
                if v and 'Metashape' in v and not ('path' in k) and not ('project' in k):    # allow "path" and "project" keys from YAML to include "Metashape" (e.g., Metashape in the filename)
                    a_dict[k] = eval(v)
            elif isinstance(v, list):
                # TODO skip if no item have metashape
                a_dict[k] =  [eval(item) for item in v if("Metashape" in item)]
        else:
            convert_objects(v)

def read_yaml(yml_path):
    with open(yml_path,'r') as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

    # TODO: wrap in a Try to catch errors
    convert_objects(cfg)

    return cfg

if __name__ == "__main__":

    yml_path = "config/example.yml"
    cfg = read_yaml(yml_path)
    #with open("config/example.yml",'r') as ymlfile:
    #    cfg = yaml.load(ymlfile)

    #catch = convert_objects(cfg)

    # Get a String value
    Photo_path = cfg['Photo_path']

    # Get a True/False
    GPU_use = cfg['GPU']['GPU_use']

    # Get a Num
    GPU_num = cfg['GPU']['GPU_num']

    # Convert a to a Metashape Object
    accuracy = eval(cfg["matchPhotos"]["accuracy"])
