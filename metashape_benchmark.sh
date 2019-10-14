#!/bin/bash
# Path to metashape 
# TODO: fix so this is more universal
#metashape='../metashape_pro'
hostname -f

# Set ENV variable to a specific font so reports work
export QT_QPA_FONTDIR='/usr/share/fonts/truetype/dejavu/'

source auth.auth

IMAGEPATH=${2} 

# Activate the license
../metashape.sh --activate $KEY

# Run the Benchmark
# On Windows remove the -platform option
# Pass the Metashape Python as the 1st arg
# Pass the Path to the project data as the 2nd arg
../metashape.sh -platform offscreen -r ${1} ${2}


# Deactivate the license, if the script fails you need to login to the node and do this manually
../metashape.sh --deactivate
