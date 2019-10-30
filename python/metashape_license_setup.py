#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 16 14:37:07 2019

@author: 
"""

import os
from pathlib import Path

license_path = "/opt/metashape-pro/metashape.lic"

cwd = "".join([os.getcwd(),"/metashape.lic"])
cwd_path = Path(cwd)

# check if license file already exists in wd, and if not, make a symlink to it
if (not cwd_path.exists()):
   os.symlink(src=license_path,dst=cwd)