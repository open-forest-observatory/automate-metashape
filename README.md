# Easy, reproducible Metashape workflows

A tool to make it easy to run reproducible, automated, documented Metashape photogrammetry workflows in batch on individual computers or as parallel jobs on a compute cluster. No coding knowledge required.

## Setup

**Python:** You need Python (3.5, 3.6, or 3.7). We recommend the [Anaconda distribution](https://www.anaconda.com/distribution/) because it includes all the required libraries. When installing, if asked whether the installer should initialize Anaconda3, say "yes". Anaconda must be initialized upon install such that `python` can be called from the command line. A way to check is to simply enter `python` at your command prompt and see if the resulting header info includes Anaconda and Python 3. If it doesn't, you may still need to initialize your Conda install. **Alternative option:** If you want a minimal python installation (such as if you're installing on a computing cluster), you can install [miniconda](https://docs.conda.io/en/latest/miniconda.html) instead. After intalling miniconda, you will need to install additional packages required by our scripts (currently only `PyYAML`) using `pip install {package_name}`.

**Metashape:** You must install the Metashape Python 3 module (Metashape version 1.6). Download the [current .whl file](https://www.agisoft.com/downloads/installer/) and install it following [these instructions](https://agisoft.freshdesk.com/support/solutions/articles/31000148930-how-to-install-metashape-stand-alone-python-module) (using the name of the .whl file that you downloaded).

**Metashape license:** You need a license (and associated license file) for Metashape. The easiest way to get the license file (assuming you own a license) is by installing the [Metashape Professional Edition GUI software](https://www.agisoft.com/downloads/installer/) (distinct from the Python module) and registering it following the prompts in the software (note you need to purchase a license first). UC Davis users, inquire over the geospatial listserv or the #geosptial Slack channel for information on joining a floating license pool. Once you have a license file (whether a node-locked or floating license), you need to set the `agisoft_LICENSE` environment variable (search onilne for instructions for your OS; look for how to *permanently* set it) to the path to the folder containing the license file (`metashape.lic`).

**Reproducible workflow scripts:** Simply clone this repository to your machine!

## Usage

The general command line call to run the worflow has three components:
1. Call to Python
2. Path to metashape workflow Python script (`metashape_workflow.py`)
3. Path to workflow configuration file (`*.yml`)

For example:

`python {repo_path}/python/metashape_workflow.py {config_path}/{config_file}.yml`

All processing parameters are specified in the .yml config file. There is an example config file in the repo at `config/example.yml`. Details on the config file are below.

### Oragnizing raw imagery (and associated files) for processing

Images should be organized such that there is one root level that contains all the photos from the flight mission to be processed (these photos may optionally be organized within sub-folders), and no other missions. If the workflow is to include spectral calibration, ground control points (GCPs), and/or a USGS DEM, this root-level folder *must* also contain a corresponding folder for each. For example:

```
mission001_photos
├───100MEDIA
|       DJI_0001.JPG
|       DJI_0002.JPG
|       ...
├───101MEDIA
|       DJI_0001.JPG
|       DJI_0002.JPG
|       ...
├───102MEDIA
|       DJI_0001.JPG
|       DJI_0002.JPG
|       ...
├───gcps
|       ...
├───dem_usgs
|       dem_usgs.tif
└───calibration
        RP04-1923118-OB.csv
```

The namings for the ancillary data folders (`gcps`, `dem_usgs`, and `calibration`) must exactly match these if they are to be a part of the workflow.

A **sample RGB photo dataset** (which includes GCPs and a USGS DEM) may be [downloaded here](https://ucdavis.box.com/s/hv8m8fibe164pjj0mssdx1mj8qb996k8) (1.5 GB). Note this dataset has sparse photos (low overlap), so photogrammetry results are unimpressive.

<mark>TO DO: Add sample multispectral dataset. Could potentially use cherry dataset if we figure out why it's not working well.</mark>

The location of the raw imagery folder is specified in the configuration file passed to the metashape workflow script (see next section).

### Workflow configuration ###

All of the parameters defining the Metashape workflow are specified in the configuration file (a [YAML-format](https://docs.ansible.com/ansible/latest/reference_appendices/YAMLSyntax.html) file). This includes directories of input and output files, workflow steps to include, quality settings, and many other parameters.

An example configuration file is provided in this repo at `config/example.yml`. The file contains comments explaining the purpose of each customizable parameter. To prepare a customized workflow, copy the `config/example.yml` file to a new location, edit the parameter values to meet your specifications, save it, and then run the metashape workflow from the command line as described above, passing it the location of the customized configuration file. Do not remove or add parameters to the configuration file; adding will have no effect unless the Python code is changed along with the addition, and removing will produce errors.

The workflow configuration is saved in a procesing log at the end of a workflow run (see below).

#### Batch workflow configuration ####

If you wish to run multiple iterations of a processing workflow with small differences between each, you can specify a "base" configuration YAML file that specifies the processing parameters that all runs will have in common, plus a "derived" configuration file that specifies how each individual run's parameters should differ from the base parameters. For an example, see `config/base.yml` and `config/derived.yml`. For each run, the derived YAML only needs to include the parameters that differ from the base parameters. Each separate run in the derived YAML should be given a name and surrounded by `####` on each end (see example `derived.yml`). Then, use the R script `R/prep_configs.R` to generate a full YAML config file for each run. As arguments to the call to this R script, supply (1) the path to the directory containing the base and derived YAML config files, and (2) the path to the `metashape_workflow.py` script. The `prep_configs.R` script will create a full YAML file for each run, as well as a shell file that calls the Metashape workflow scripts once for each configuration (each run). All you have to do to execute all these runs in series is to call this automatically generated shell script.

### Workflow outputs

The outputs of the workflow are the following:
- **Photogrammetry outputs** (e.g., dense point cloud, orthomosaic, digital surface model, and Metashape processing report)
- **A Metashape project file** (for additional future processing or for inspecting the data via the Metashape GUI)
- **A processing log** (which records the processing time for each step and the full set of configuration parameters, for reproducibility)

The outputs for a given workflow run are named using the following convention: `{run_name}_{date_and_time}_abc.xyz`. For example: `set14-highQuality_20200118T1022_ortho.tif`. The run name and output directories are specified in the configuration file.

### Running workflow batches in serial on a single computer

Running workflows in batch (i.e., multiple workflows in series) on a single computer is as simple as creating configuration file for each workflow run and calling the Python workflow script once for each. The calls can be combined into a shell script. The shell script might look like the following (note the only thing that changes is the name of the config file):

```
python ~/repos/metashape/python/metashape_workflow.py ~/projects/forest_structure/metashape_configs/config001.yml
python ~/repos/metashape/python/metashape_workflow.py ~/projects/forest_structure/metashape_configs/config002.yml
python ~/repos/metashape/python/metashape_workflow.py ~/projects/forest_structure/metashape_configs/config003.yml
```

Then it's just a matter of running the shell script.


### Running workflow batches in parallel on a compute cluster

Running Metashape workflow batches in parallel on a cluster is as simple as submitting multiple jobs to the cluster. Submitting a job simply involves instructing the cluster to run the `metashape_workflow.py` script with the specified configuration file.

#### Example for the `farm` cluster (UC Davis College of Agricultural and Environmental Sciences)

- [Basic farm overview and account creation information](https://wiki.cse.ucdavis.edu/support/systems/farm)
- [Basic instructions for running jobs on farm](https://bitbucket.org/hijmans-lab/computing/wiki/getting-started-farm)
- [Additional resources for getting set up and running jobs on farm](https://github.com/RILAB/lab-docs/wiki/Using-Farm)

You will need to install the Metashape python module into your user account on farm following the [Setup](https://github.com/ucdavis/metashape/blob/master/README.md#setup) instructions above (including the isntructions related to the Metashape license). This is easiest if you first install Miniconda and install Metashape (along with PyYAML) there.

Next you need to create a shell script that will set up the appropriate environment variables and then call python to execute the metashape_workflow.py file with a provided config file (save as `farm_python.sh`):
```
#!/bin/bash -l
source ~/.bashrc

# Write the hostname to the processing log
hostname -f

# Set ENV variable to a specific font so reports work
export QT_QPA_FONTDIR='/usr/share/fonts/truetype/dejavu/'

# Run the workflow
# First arg is the Metashape python workflow script,
# Second arg is the config file
python ${1} ${2}
```

Finally, to submit a Metashape job, you would run something like the following line:
```
sbatch -p bigmemh --time=24:00:00 --job-name=MetaDemo -c 64 --mem=128G shell/farm_python.sh python/metashape_workflow.py config/example.yml
```

The meanings of the sbatch parameters are explained in the linked resources above. Once you have submitted one job using the sbatch command, you can submit another so that they run in parallel (assuming your user group has sufficient resource allocation on farm). You can also put multiple sbatch commands into a shell script so that you only have to run the shell script.

#### Options for accessing farm computing resources

Efficient execution of Metashape requires a good GPU. Having *many* CPUs can help, but still does not come near to the efficiency of a GPU. For photogrammetry to make sense on farm, PIs would need to invest in GPU nodes. Here are rough estimates of a hypothetical Metashape project's execution time based on extensive benchmarking:

| Machine/node type | Required computing time | Cost ballpark |
|---|---|---|
| Dell Alienware gaming PC with Nvidia RTX 2080 Ti and 16 CPUs | 1 day | $3,000 |
| Free original farm nodes (24 CPUs) | 30 days | Free |
| New farm bigmem nodes (96 CPUs) | 5 days | $22,700 |
| Potential future farm GPU node (8 x RTX 2080 Ti) | 2 days (using only 1 of the 8 GPUs) | $25,000 (if split 8 ways, $3,125 per user) |

A new farm GPU node would provide computing power that is competitive with the Alienware gaming PC for *individual projects,* but it would provide the opportunity to run multiple projects in parallel. Assuming that not all PIs/users were using the node at the same time (a reasonable assumption), those who needed extra processing power temporarily would be allowed to use other users' GPU allocations. This is the beauty of a shared computing cluster. In this circumstance, running 8 projects that would each take 1 day on the Alienware gaming PC (for a total of 8 days) would take only 2 days on the computing cluster.


## Preparing ground-control points (GCPs)

Because the workflow implemented here is completely GUI-free, it is necessary to prepare GCPs in advance. The process of preparing GCPs involves recording (a) the geospatial location of the GCPs on the earth and (b) the location of the GCPs within the photos in which they appear.

Metashape requires this information in a very specific format, so this repository includes an R script to assist in producing the necessary files based on more human-readable input. The helper script is `R/prep_gcps.R`.

**GCP processing input files.** Example GCP input files are included in the [example RGB photo dataset](https://ucdavis.box.com/s/hv8m8fibe164pjj0mssdx1mj8qb996k8) under `gcps/raw/`. The files are the following:
- **gcps.gpkg**: A geopackage (shapefile-like GIS format) containing the locations of each GCP on the earth. Must include an integer column called `gcp_id` that gives each GCP a unique integer ID number.
- **gcp_imagecoords.csv**: A CSV table identifying the locations of the GCPs within raw drone images. Each GCP should be located in at least 5 images (ideally more). The tabls must contain the following columns:
  - `gcp`: the integer ID number of the GCP (to match the ID number in `gcps.gpkg`)
  - `folder`: the *integer* number of the subfolder in which the raw drone image is located. For example, if the image is in `100MEDIA`, the value that should be recorded is `100`.
  - `image`: the *ingeter* number of the image in which the GCP is to be identified. For example, if the image is named `DJI_0077.JPG`, the value that should be recorded is `77`.
  - `x` and `y`: the coordinates of the pixel in the image where the GCP is located. `x` and `y` are in units of pixels right and down (respectively) from the upper-left corner.

These two files must be in `gcps/raw/` at the top level of the flight mission directory (where the subfolders of images also reside). Identification of the image pixel coordinates where the GCPs are located is easy using the info tool in QGIS.

**Running the script.** You must have R and the following packages installed: sf, raster, dplyr, stringr, magick, ggplot2. The R `bin` directory must be in your system path, or you'll need to use the full path to R. You run the script from the command line by calling `Rscript --vanilla` with the helper script and passing the location of the top-level mission imagery folder (which contains the `gcp` folder) as an argument. For example, on Windows:

```
Rscript --vanilla {path_to_repo}/R/prep_gcps.R {path_to_imagery_storage}/sample_rgb_photoset
```

**Outputs.** The script will create a `prepared` directory within the `gcps` folder containing the two files used by Metashape: `gcp_table.csv`, which contains the geospatial coordinates of the GCPs on the earth, and `gcp_imagecoords_table.csv`, which contains the pixel coordinates of the GCPs within each image. It also outputs a PDF called `gcp_qaqc.pdf`, which shows the specified location of each GCP in each image in order to quality-control the location data. If left in this folder structure (`gcps/prepared`), the Metashape workflow script will be able to find and incorporate the GCP data if GCPs are enabled in the configuration file.
