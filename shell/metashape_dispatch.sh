python ~/Documents/projects/metashape/python/metashape_control.py ~/Documents/projects/metashape/config/example.yml
#python ${1} ${2}

# Slurm variant, no metashape resource yet
sbatch -p high --time=1:00:00 --job-name=MetaGPUf -c 12 --gres=gpu:1 --mem=32768 metashape_benchmark.sh ~/Documents/projects/metashape/python/metashape_control.py ~/Documents/projects/metashape/config/example.yml

# Current Slurm variant
sbatch -p med --time=1:00:00 --job-name=MetashapeTest01 -c 16 --mem=32768 --mail-type=ALL --mail-user=djyoung@ucdavis.edu metashape_control.sh ~/projects/metashape/python/metashape_control.py ~/projects/metashape/config/example.yml

# actual
sbatch -p bigmemh --time=24:00:00 --job-name=MetaT01 -c 64 --mem=256G --mail-type=ALL --mail-user=djyoung@ucdavis.edu shell/metashape_control.sh python/metashape_pipeline.py config/example.yml
