#!/bin/bash
hostname -f

module load python3

# 1st arg is the python script
# 2nd arg is the yaml config file 

python3 ${1} ${2}