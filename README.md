# Easy, reproducible Metashape workflows

A tool to make it easy to run reproducible, automated, documented Metashape photogrammetry workflows in batches on an individual computer (in serial) or as parallel jobs on a compute cluster. No coding knowledge required.

## Setup (native install)

### External users

**Python:** You need Python 3.7-3.11. We recommend the [Anaconda distribution](https://www.anaconda.com/distribution/) because it includes all the required libraries. When installing, if asked whether the installer should initialize Anaconda3, say "yes". Anaconda must be initialized upon install such that `python` can be called from the command line. A way to check is to simply enter `python` at your command prompt and see if the resulting header info includes Anaconda and Python 3. If it doesn't, you may still need to initialize your Conda install. **Alternative option:** If you want a minimal python installation (such as if you're installing on a computing cluster), you can install [miniconda](https://docs.conda.io/en/latest/miniconda.html) instead. After intalling miniconda, you will need to install additional packages required by our scripts (currently only `PyYAML`) using `pip install {package_name}`.

**Metashape:** You must install the Metashape Python 3 module (Metashape version 2.0). Download the [current .whl file](https://www.agisoft.com/downloads/installer/) and install it following [these instructions](https://agisoft.freshdesk.com/support/solutions/articles/31000148930-how-to-install-metashape-stand-alone-python-module) (using the name of the .whl file that you downloaded). NOTE: If you wish to use an older version of Metashape (v1.6-1.8), the primary scripts here (for v2.0) are not backwards-compatible, but scripts for older versions (with somewhat more limited configuration options) are archived in `prior-versions/`. For the Metashape v1.6-1.8-compatible scripts, you need Python 3.5-3.7.

**Metashape license:** You need a license (and associated license file) for Metashape. The easiest way to get the license file (assuming you own a license) is by installing the [Metashape Professional Edition GUI software](https://www.agisoft.com/downloads/installer/) (distinct from the Python module) and registering it following the prompts in the software (note you need to purchase a license first). UC Davis users, inquire over the geospatial listserv or the #spatial Slack channel for information on joining a floating license pool. Once you have a license file (whether a node-locked or floating license), you need to set the `agisoft_LICENSE` environment variable (search onilne for instructions for your OS; look for how to *permanently* set it) to the path to the folder containing the license file (`metashape.lic`). On many Linux systems, assuming the Metashape GUI is installed in `/opt/metashape-pro/`, you can set the environment variable with `export agisoft_LICENSE=/opt/metashape-pro/`, though if run directly in a bash terminal it will only be effective during that bash session.

### Internal users

For internal users working on a JS2 VM created using the OFO Dev CACAO template, run:

`conda activate meta`

to switch to a conda environment with a current Metashape python package preinstalled and configured.

## Setup (Docker container)

Docker, a type of software containerization, is an alternative way to run software where you don't need to install software in the traditional sense. Docker packages up the code and all its environment dependencies so the application runs reliably from one computer to another. Background information on docker and software containers can be found [here](https://foss.cyverse.org/07_reproducibility_II/).

To run a docker container on your local machine, you do need to install `docker`. You can install and run docker as a command line tool for [linux distributions](https://docs.docker.com/engine/install/) or as a graphical program (i.e, Docker Desktop) for [windows](https://docs.docker.com/desktop/setup/install/windows-install/), [macOS](https://docs.docker.com/desktop/setup/install/mac-install/), or [linux](https://docs.docker.com/desktop/setup/install/linux/). We recommend running docker commands at the terminal. If you are using Docker Desktop, you can still write commands at the terminal while Docker Desktop is open and running.

The `automate-metashape` docker image contains the python libraries needed to run the workflow, while you (the user) need to provide at minimum the **1.** aerial images; **2** a configuration file specifying your choices for processing; **3.** a license to use Metashape; and optionally **4.** [ground control points (GCPs)](https://github.com/open-forest-observatory/automate-metashape?tab=readme-ov-file#preparing-ground-control-points-gcps).   

### User inputs to the workflow

To provide the input data to Metashape, you need to specify a folder from your computer to be mirrored ("mounted") within the Docker container. The files needed to run Metashape (the folder of aerial images, the configuration file, and optionally the GCPs file) must all be in the folder that you mount. The files can be located in any arbitrary directory beneath this folder. For example, if the folder you mount is `~/drone_data` on your local computer, the images could be located at `~/drone_data/projects/project_10/images/` and the config file could be located at `~/drone_data/configs/project_10/config.yml` The folder from your local machine is mounted into the Docker container at the path /data/, so for the example above, the images would be found inside the docker container at the path /data/projects/project_10/images/.

#### Image directory

The images to be processed should all be in one folder (and optionally organized into subfolders beneath this folder) somewhere within the data folder you will be mounting. In the example above, the folder of images is at `~/drone_data/projects/project_10/images/`.

#### Workflow configuration file

An example configuration file is provided in this repository at `config/config-example.yml`. Please download this file to your local machine and rename it `config.yml`. By default, the container expects the config YAML file describing the Metashape workflow parameters to be located at `/data/config.yaml`, but this can be overridden by passing a different location as a final (optional) command line argument to the `docker run` command (see below). In a case where the local folder to be mounted is `~/drone_data/`, then for the config file to be mounted in the Docker container at `/data/config.yaml`, it must be located on the local computer at `~/drone_data/config.yaml`.

Within the `config.yml` you will need to edit some of the project level parameters to specify where to find input images and where to put output products within the container. Within this config file, all paths will be relative to the file structure of the docker container (beginning with `/data/`). In the config.yml, at a minimum the following entries should be updated:

* The value for photo_path should be updated to /data/{path_to_images_folder_within_mounted_folder}
* The value for output_path should be updated to /data/{path_to_desired_ouputs_folder_within_mounted_folder} (can be any location you want; will be created if it does not exist)
* The value for project_path should be updated similarly as for output_path.

### Metashape license
Users need to provide a license to use Metashape. Currently, this docker method only supports a floating license server using the format `<IP address>:<port number>`. Within a terminal, users can declare the floating license as an environmental variable using the command:

`export AGISOFT_FLS=<IP_address>:<port_number>`

Keep in mind that environmental variables will not persist across different terminal sessions. 

### Enable GPUs for accelerated processing

The use of graphical processing units (GPUs) can greatly increase the speed of photogrammetry processing. If your machine has GPU hardware, you will need extra software so docker can find and use your GPUs. Linux users simply need to install nvidia-container-toolkit via `sudo apt install nvidia-container-toolkit`. For Windows users please see [this documentation](https://docs.docker.com/desktop/features/gpu/). For macOS user, it may not be possible to use your local GPU (Apple Silicon) through Docker. 

### Run the docker container
From a terminal, run this command: 

`docker run -v </host/data/dir>:/data -e AGISOFT_FLS=$AGISOFT_FLS --gpus all ghcr.io/open-forest-observatory/automate-metashape`

Here is a breakdown of the command:

`docker run` is the command to run a docker image

`-v </host/data/dir>:/data` is mounting a volume from your local computer into the container. We are mounting your directory that has the imagery and config file (</host/data/dir>) into the container at the path "/data".

`-e AGISOFT_FLS=$AGISOFT_FLS` is declaring your floating license to use Metashape. We set the license info as an environmental variable earlier in these instructions (i.e., `export AGISOFT_FLS=<IP_address>:<port_number>`)

`--gpus all` If the container has access to your local GPUs, use this flag to enable it.

`ghcr.io/open-forest-observatory/automate-metashape` This is the docker image that has the software to run the `automate-metashape` script. It is located in the Github container registry. When you execute the `docker run...` command, it will download the container image to your local machine and start the script to process imagery using Metashape. 

#### Custom location of the Metashape configuration file

If your config.yaml is located anywhere other than `/data/config.yaml` (or the file is named differently), you can specify its location as one additional command line argument at the end of the `docker run` command. For example, if it is located at `/data/configs/project_10/config.yml` (meanining, in the example above, it is located on your local computer at `~/drone_data/configs/project_10/config.yml`), just append `/data/configs/project_10/config.yml` to the `docker run` command above. So the command above would look like:

`docker run -v </host/data/dir>:/data -e AGISOFT_FLS=$AGISOFT_FLS --gpus all ghcr.io/open-forest-observatory/automate-metashape /data/configs/project_10/config.yml`

### Outputs

As the processing runs, the completed imagery products will be saved into the folder you specified for the `output_path` parameter in the config.yaml. In the example above, if your config.yaml specifies the `output_path` as `/data/{path_to_desired_ouputs_folder_within_mounted_folder}`, the outputs will be saved on your local computer at `~/drone_data/{path_to_desired_ouputs_folder_within_mounted_folder}`.

### Permissions on Linux

If running Docker on Linux without `sudo` (as in this example), your user will need to be in the `docker` group. This can be achieved with `sudo usermod -a -G docker $USER` and then logging out and in, as explained [here](https://docs.docker.com/engine/install/linux-postinstall/).

Note that the owner of the output data will be the `root` user. To set the ownership to your user account, you can run `sudo chown <username>:<username> <file name>` or `sudo chown <username>:<username> -R <folder name>`.

## Usage

### Native install

**Reproducible workflow scripts:** Simply clone this repository to your machine!

The general command line call to run the worflow has three components:
1. Call to Python
2. Path to metashape workflow Python script (`metashape_workflow.py`)
3. Path to workflow configuration file (`*.yml`)

For example:

`python {repo_path}/python/metashape_workflow.py {config_path}/{config_file}.yml`

All processing parameters are specified in the .yml config file. There is an example config file in the repo at `config/example.yml`. Details on the config file are below.

### Docker install

See Docker section above.

### Organizing raw imagery (and associated files) for processing

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

The location of the raw imagery folder is specified in the configuration file passed to the metashape workflow script (see next section).

### Workflow configuration ###

All of the parameters defining the Metashape workflow are specified in the configuration file (a [YAML-format](https://docs.ansible.com/ansible/latest/reference_appendices/YAMLSyntax.html) file). This includes directories of input and output files, workflow steps to include, quality settings, and many other parameters.

An example configuration file is provided in this repo at `config/config-example.yml`. The file contains comments explaining the purpose of each customizable parameter. To prepare a customized workflow, copy the `config/config-example.yml` file to a new location, edit the parameter values to meet your specifications, save it, and then run the metashape workflow from the command line as described above, passing it the location of the customized configuration file. Do not remove or add parameters to the configuration file; adding will have no effect unless the Python code is changed along with the addition, and removing will produce errors.

The workflow configuration is saved in a procesing log at the end of a workflow run (see below).

#### Batch workflow configuration ####

If you wish to run multiple iterations of a processing workflow with small differences between each,
you can specify a "base" configuration YAML file that specifies the processing parameters that all
runs will have in common, and then using the `ofo-r` function
[make_derived_configs](https://github.com/open-forest-observatory/ofo-r/blob/main/R/photogrammetry-prep.R),
which takes a data frame of parameter replacements and creates a "derived" config file for each row
of the data frame, along with a shell script that will call the metashape workflow once for each of
the resulting config files, in serial.

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
