python ~/Documents/projects/metashape/python/metashape_control.py ~/Documents/projects/metashape/config/example.yml
#python ${1} ${2}

# Slurm variant, no metashape resource yet
sbatch -p high --time=1:00:00 --job-name=MetaGPUf -c 12 --gres=gpu:1 --mem=32768 metashape_benchmark.sh ~/Documents/projects/metashape/python/metashape_control.py ~/Documents/projects/metashape/config/example.yml
