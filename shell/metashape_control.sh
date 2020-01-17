#!/bin/bash
# Path to metashape 
# TODO: fix so this is more universal
#metashape='../metashape_pro'
hostname -f

# Set ENV variable to a specific font so reports work
export QT_QPA_FONTDIR='/usr/share/fonts/truetype/dejavu/'

#source auth.auth

CONFIG_FILE=${1} 

# Run the Benchmark
# First arg is the Metashape python pipeline script,
# Second arg is the config file
python ${1} ${2}


