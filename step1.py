import json
import sys
import os


def detemineDatasetsToRun():
        json.dump(os.listdir('/data') + os.listdir('/results'), sys.stdout)
        json.dump(os.environ['AGISOFT_FLS'], sys.stdout)

detemineDatasetsToRun()