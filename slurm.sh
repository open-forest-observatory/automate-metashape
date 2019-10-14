#!/bin/sh
# -*- coding: utf-8 -*-
# These are example commands to slurm on the FARM cluster for running metashape jobs

#### Forest Data  ####

# Regular Node
sbatch -p high --time=2:00:00 --job-name=MetaFor -c 12 --mem=32768 --mail-type=ALL --mail-user=aimandel@ucdavis.edu metashape_benchmark.sh benchmark_simple.py /share/spatial02/users/latimer/performance-testing/thinned_set_subset

# GPU test to verify gpu usage
sbatch  -p bgpu --time=5:00 --job-name=MetaGPU1 --gres=gpu:1 -c 12 metashape_benchmark-cuda.sh gpu_check.py

# GPU Node
sbatch -p bgpu --time=1:00:00 --job-name=MetaGPUf -c 12 --gres=gpu:1 --mem=32768 --mail-type=ALL --mail-user=aimandel@ucdavis.edu metashape_benchmark.sh benchmark_simple.py /share/spatial02/users/latimer/performance-testing/thinned_set_subset

# AMD Nodes
sbatch -p high2 --time=2:00:00 --job-name=MetaAMD -c 12 --mem=65536 metashape_benchmark.sh benchmark_simple.py /share/spatial02/users/latimer/performance-testing/thinned_set_subset


#Re export the reports after a failure
sbatch -p low --time=1:00:00 --job-name=MetaF2 -c 1 --mail-type=ALL --mail-user=aimandel@ucdavis.edu metashape_benchmark.sh report.py /share/spatial02/users/latimer/performance-testing/thinned_set_subset/benchmark_2019-08-26T1506.psx 


#### Testing on Windows ####
& 'C:\Program Files\Agisoft\Metashape Pro\metashape.exe' -r C:\Users\vulpes\Documents\metashapebenchmark\benchmark_simple.py D:\Public\Pictures\Latimer_lab\thinned_set_subset >> nightfury-20190827.out
