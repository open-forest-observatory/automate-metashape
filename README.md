# Easy, reproducible Metashape workflows

A simple command line tool to automate end-to-end photogrammetry workflows using [Agisoft Metashape](https://www.agisoft.com/).  Metashape is proprietary structure-from-motion photogrammetry software that creates 3D point clouds, digital elevation models, mesh models, and orthomosaics from overlapping aerial imagery. Our no-code automation increases the speed of image product creation and makes your workflows fully reproducible and documented. Run parameters are controlled through a single, intuitive configuration file. We offer a [native installation workflow](#native-installation-workflow) as well as a [docker workflow](#docker-workflow). You need to provide **1.** a Metashape license, **2.** your aerial images, and optionally **3.** [ground control points](#preparing-ground-control-points-gcps).


<br/>
<br/>


## Native Installation Workflow

### Download and Install Software
**Python:** You need Python 3.7-3.11. We recommend the [Anaconda
distribution](https://www.anaconda.com/distribution/) because it includes all the required
libraries. When installing, if asked whether the installer should initialize Anaconda3, say "yes".
Anaconda must be initialized upon install such that `python` can be called from the command line. A
way to check is to simply enter `python` at your command prompt and see if the resulting header info
includes Anaconda and Python 3. If it doesn't, you may still need to initialize your Conda install.
If you want logging of GPU utilization during workflow runs, you will need to install one additional
package into your environment that is not inlcluded in Anaconda by running `pip install nvidia-ml-py`.
**Alternative option:** If you want a minimal python installation (such as if you're installing on a
computing cluster), you can install [miniconda](https://docs.conda.io/en/latest/miniconda.html)
instead. After intalling miniconda, you will need to install additional packages required by our
scripts using `pip install PyYAML psutil nvidia-ml-py`. The final package, `nvidia-ml-py`, is only
required if you want to enable logging of GPU utilization during workflow runs.

**Reproducible workflow scripts (python):** Simply clone this repository to your machine! `git clone https://github.com/open-forest-observatory/automate-metashape.git`

**Metashape:** You must install the Metashape Python 3 module (Metashape version 2.0). Download the [current .whl file](https://www.agisoft.com/downloads/installer/) and install it following [these instructions](https://agisoft.freshdesk.com/support/solutions/articles/31000148930-how-to-install-metashape-stand-alone-python-module) (using the name of the .whl file that you downloaded). NOTE: If you wish to use an older version of Metashape (v1.6-1.8), the primary scripts here (for v2.0) are not backwards-compatible, but scripts for older versions (with somewhat more limited configuration options) are archived in `prior-versions/`. For the Metashape v1.6-1.8-compatible scripts, you need Python 3.5-3.7.

**Metashape license:** You need a license (and associated license file) for Metashape. The easiest way to get the license file (assuming you own a license) is by installing the [Metashape Professional Edition GUI software](https://www.agisoft.com/downloads/installer/) (distinct from the Python module) and registering it following the prompts in the software (note you need to purchase a license first). UC Davis users, inquire over the geospatial listserv or the #spatial Slack channel for information on joining a floating license pool. Once you have a license file (whether a node-locked or floating license), you need to set the `agisoft_LICENSE` environment variable (search onilne for instructions for your OS; look for how to *permanently* set it) to the path to the folder containing the license file (`metashape.lic`). On many Linux systems, assuming the Metashape GUI is installed in `/opt/metashape-pro/`, you can set the environment variable with `export agisoft_LICENSE=/opt/metashape-pro/`, though if run directly in a bash terminal it will only be effective during that bash session.

<br/>

** Internal OFO developers only: Python and the Metashape python module are pre-installed and ready for use on 'ofo-dev' instances launched from Exosphere and as well as 'Open-Forest-Observatory' template launched from CACAO. The software is installed in a conda environment. `conda activate meta`

<br/>

### Organizing raw imagery (and associated files) for processing

Images should be organized such that there is one root level that contains all the photos from the flight mission to be processed (these photos may optionally be organized within sub-folders), and no other missions. If your workflow is to include the **optional** inputs of _spectral calibration_, [ground control points (GCPs)](#preparing-ground-control-points-gcps), and/or a _USGS DEM_, this root-level folder *must* also contain a corresponding folder for each. For example:

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

<br/>

### Workflow configuration

All of the parameters defining the Metashape workflow are specified in the configuration file (a [YAML-format](https://docs.ansible.com/ansible/latest/reference_appendices/YAMLSyntax.html) file). This includes directories of input and output files, workflow steps to include, quality settings, and many other parameters.

An example configuration file is provided in this repo at [`config/config-example.yml`](/config/config-example.yml). Edit the parameter values to meet your specifications. The file contains comments explaining the purpose of each customizable parameter.  You can directly edit the `config-example.yml` or save a new copy somewhere on the your local computer. You will specify the path of this config.yml in the [python run command](#running-the-workflow).

Note: Please do not remove or add parameters to the configuration file; adding will have no effect unless the Python code is changed along with the addition, and removing will produce errors.

<br/>

### Running the Workflow

The general command line call to run the workflow has two required components:
1. Call to Python
2. Path to metashape workflow Python script (`metashape_workflow.py`)

For example:

`python {repo_path}/python/metashape_workflow.py`

<br/>

With this minimalist run command, the script assumes your config.yml file is located in the repo at `{repo_path}/config/config-example.yml`

<br/>

If your config file is located in a different directory, use the optional flag `--config-file`

For example:

`python {repo_path}/python/metashape_workflow.py --config-file {config_path}/{config_file}.yml`


<br/>

**Additional run command flags**. Using these flags will override parameters specified in the config.yml file. 

`--photo-path`    Path to the directory that contains the aerial images (usually jpegs) to be processed

`--photo-path-secondary`   Path to the directory that contains aerial images which are aligned only after all other processing is done. Not commonly used. 

`--project-path` Path where the metashape project file (.psx) will be written

`--output-path` Path where all imagery products (orthomosaic, point cloud, DEMs, mesh model, reports) will be written 

`--project-name`    The identifier for the project. Will be used in naming the project file and output files

`--project-crs` Coordinate reference system EPSG code for outputs. Eg. _EPSG:26910_

`--step`    Run a single processing step instead of the full workflow. This enables step-by-step execution where each step loads the project from the previous step. Valid steps are:
- `setup` - Initialize project and add photos
- `match_photos` - Find tie points between photos
- `align_cameras` - Estimate camera positions and perform post-alignment operations
- `build_depth_maps` - Generate depth maps from aligned photos
- `build_point_cloud` - Build dense 3D point cloud from depth maps
- `build_mesh` - Build 3D mesh model from depth maps
- `build_dem_orthomosaic` - Generate DEMs and/or orthomosaics
- `match_photos_secondary` - Match secondary photos (if configured in config file)
- `align_cameras_secondary` - Align secondary cameras (if configured in config file)
- `finalize` - Clean up and generate processing reports

Example step-based workflow execution:

```bash
python metashape_workflow.py --config-file config.yml --step setup
python metashape_workflow.py --config-file config.yml --step match_photos
python metashape_workflow.py --config-file config.yml --step align_cameras
python metashape_workflow.py --config-file config.yml --step build_depth_maps
python metashape_workflow.py --config-file config.yml --step build_point_cloud
python metashape_workflow.py --config-file config.yml --step build_dem_orthomosaic
python metashape_workflow.py --config-file config.yml --step finalize
```

**Note:** Each step automatically loads the project file created/updated by previous steps, so all steps must use the same `--project-path` and `--project-name` values. The `setup` step creates the project; all subsequent steps load it.

<br/>

#### License Retry Wrapper

When using a floating license server, license availability can be intermittent—especially in shared environments where multiple users or workflows compete for licenses. Metashape acquires a license at import time, and if no license is available, the workflow will fail when attempting to save the project (after potentially hours of processing).

The `license_retry_wrapper.py` script solves this by:
1. Monitoring the first few lines of Metashape output for license errors
2. If a license error is detected, immediately terminating the process (before wasting compute time)
3. Waiting a configurable interval and retrying

**Usage:**

Instead of calling `metashape_workflow.py` directly, call the wrapper:

```bash
python {repo_path}/python/license_retry_wrapper.py --config-file config.yml
```

All command-line arguments are passed through to `metashape_workflow.py`.

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `LICENSE_MAX_RETRIES` | `0` | Maximum retry attempts. `0` = no retries (fail immediately), `-1` = unlimited, `>0` = that many retries |
| `LICENSE_RETRY_INTERVAL` | `300` | Seconds to wait between retry attempts |
| `LICENSE_CHECK_LINES` | `20` | Number of output lines to monitor for license errors |

**Example with custom settings:**

```bash
export LICENSE_RETRY_INTERVAL=600
export LICENSE_MAX_RETRIES=10
python {repo_path}/python/license_retry_wrapper.py --config-file config.yml
```

**Signal Handling:**

The wrapper forwards SIGTERM and SIGINT signals to the child Metashape process, ensuring graceful shutdown in containerized/orchestrated environments (e.g., Kubernetes pod termination).

#### Output Monitoring and Heartbeat

The license retry wrapper includes an output monitor that reduces console log volume during long-running Metashape steps while preserving full debuggability. This is especially useful in orchestrated environments (e.g., Argo/Kubernetes) where verbose Metashape output can overwhelm log storage.

**Features:**
- **Progress callbacks**: Metashape API calls report structured `[automate-metashape-progress] operation: X%` messages at configurable percentage intervals
- **Heartbeat**: Periodic liveness messages showing timestamp, line count, elapsed time, and most recent Metashape output line
- **Full log file**: Every line of Metashape output is written to a log file on disk (as a sibling to `--output-path`), even when console output is sparse
- **Error context buffer**: On failure, the last N lines of output are dumped to console for immediate debugging
- **Full output mode**: Set `LOG_HEARTBEAT_INTERVAL=0` to print all lines to console (original behavior) while still getting progress callbacks, full log file, and error buffer

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `PROGRESS_INTERVAL_PCT` | `1` | Print progress every N percent (e.g., `10` prints at 10%, 20%, 30%...) |
| `LOG_HEARTBEAT_INTERVAL` | `60` | Seconds between heartbeat status lines. `0` = full output mode (print all lines, no filtering) |
| `LOG_BUFFER_SIZE` | `100` | Number of lines kept in circular buffer for error context dump on failure |
| `LOG_OUTPUT_DIR` | _(unset)_ | Optional override for full log file directory. If not set, log is placed as a sibling to `--output-path` |

**Example with sparse output (default):**

```bash
export LOG_HEARTBEAT_INTERVAL=60
export PROGRESS_INTERVAL_PCT=10
python {repo_path}/python/license_retry_wrapper.py --config-file config.yml --step build_depth_maps --output-path /data/output
```

Console output will be ~20-30 lines per step instead of thousands, with progress milestones and periodic heartbeats. The full log is saved to `/data/metashape-build_depth_maps.log`.

**Example with full output (original behavior):**

```bash
export LOG_HEARTBEAT_INTERVAL=0
python {repo_path}/python/license_retry_wrapper.py --config-file config.yml
```

<br/>

#### Argo workflow configuration (OFO Kubernetes cluster)

When running via the [OFO Argo workflow orchestration system](https://github.com/open-forest-observatory/ofo-argo), additional configuration options control GPU resource allocation:

- **`gpu_enabled`** (for `match_photos`, `build_mesh`): If `true`, the step runs on a GPU node; if `false`, it runs on a CPU node. Defaults to `true`. This has no effect on local execution where Metashape auto-detects available hardware.

- **`gpu_resource`** (for `match_photos`, `build_depth_maps`, `build_mesh`): Specifies which GPU resource to request. Options:
  - `"nvidia.com/gpu"` - Full GPU (default)
  - `"nvidia.com/mig-1g.5gb"` - MIG partition: 1/7 compute, 5GB VRAM
  - `"nvidia.com/mig-2g.10gb"` - MIG partition: 2/7 compute, 10GB VRAM
  - `"nvidia.com/mig-3g.20gb"` - MIG partition: 3/7 compute, 20GB VRAM

  MIG (Multi-Instance GPU) partitions allow multiple workflow steps to share a single physical GPU, reducing costs for workloads with low GPU utilization. Requires a MIG-enabled nodegroup on the cluster.

- **`gpu_count`** (for `match_photos`, `build_depth_maps`, `build_mesh`): Number of GPU resources to request. Defaults to `1`. Use with MIG partitions to request multiple slices (e.g., `gpu_count: 2` with `mig-1g.5gb` to get 2/7 compute power).

These options have no effect when running locally or via Docker—they are only used by the Argo workflow system.

<br/>


#### Running workflow batches 

Running workflows in batch (i.e., multiple workflows in series) on a single computer is as simple as creating configuration file for each workflow run and calling the Python workflow script once for each. The calls can be combined into a shell script. Here is a quick workflow of how to do this:

1. Create an empty shell script `touch metashape.sh`
2. Populate the script with run commands on different lines. Note: the only thing that changes is the name of the config file.


```
python ~/repos/automate-metashape/python/metashape_workflow.py --config-file ~/projects/forest_structure/metashape_configs/config001.yml
python ~/repos/automate-metashape/python/metashape_workflow.py --config-file ~/projects/forest_structure/metashape_configs/config002.yml
python ~/repos/automate-metashape/python/metashape_workflow.py --config-file ~/projects/forest_structure/metashape_configs/config003.yml
```
3. Give the shell script file executable permissions ` chmod +x metashape.sh`
4. Make sure you are located in the directory that contains the shell script. Run the shell script `./metashape.sh`


<br/>

### Workflow outputs

The outputs of the workflow are the following:
- **Photogrammetry outputs** (e.g., dense point cloud, orthomosaic, digital surface model, and Metashape processing report)
- **A Metashape project file** (for additional future processing or for inspecting the data via the Metashape GUI)
- **A processing log** (which records the processing time for each step and the full set of configuration parameters, for reproducibility)

The outputs for a given workflow run are named using the following convention: `{project_name}_abc.xyz`. For example: `set14-highQuality_ortho.tif`. The project name and output directories are specified in the configuration file.

<br/>
<br/>
<br/>

---

<br/>

## Docker Workflow

Docker, a type of software containerization, is an alternative way to run software where you don't need to install software in the traditional sense. Docker packages up the code and all its environment dependencies so the application runs reliably from one computer to another. Background information on docker and software containers can be found [here](https://foss.cyverse.org/07_reproducibility_II/).

To run a docker container on your local machine, you do need to install `docker`. You can install and run docker as a command line tool for [linux distributions](https://docs.docker.com/engine/install/) or as a graphical program (i.e, Docker Desktop) for [windows](https://docs.docker.com/desktop/setup/install/windows-install/), [macOS](https://docs.docker.com/desktop/setup/install/mac-install/), or [linux](https://docs.docker.com/desktop/setup/install/linux/). We recommend running docker commands at the terminal. If you are using Docker Desktop, you can still write commands at the terminal while Docker Desktop is open and running.

The `automate-metashape` docker image contains the python libraries needed to run the workflow, while you (the user) need to provide at minimum the **1.** aerial images; **2** a configuration file specifying your choices for processing; **3.** a license to use Metashape; and optionally **4.** [ground control points (GCPs)](#preparing-ground-control-points-gcps).   

<br/>

### User inputs to docker workflow

To provide the input data to Metashape, you need to specify a folder from your computer to be mirrored ("mounted") within the Docker container. The files needed to run Metashape (the folder of aerial images, the configuration file, and optionally the GCPs file) must all be in the folder that you mount. The files can be located in any arbitrary directory beneath this folder. For example, if the folder you mount is `~/drone_data` on your local computer, the images could be located at `~/drone_data/images/` and the config file could be located at `~/drone_data/config.yml` The folder from your local machine is mounted into the Docker container at the path `/data/`, so for the example above, the images would be found inside the docker container at the path `/data/images/`.

<br/>

#### Image directory

The images to be processed should all be in one parent folder (and optionally organized into subfolders beneath this folder) somewhere within the data folder you will be mounting. If including GCPs, spectral calibratation, and/or the USGS DEM, follow the organization shown [here](#organizing-raw-imagery-and-associated-files-for-processing).

<br/>

#### Workflow configuration file

An example configuration file is provided in this repository at [`config/config-example.yml`](/config/config-example.yml). Please download this file to your local machine and rename it `config.yml`. By default the container expects the config YAML file describing the Metashape workflow parameters to be located at `/data/config.yaml`. So in a case where the local folder to be mounted is `~/drone_data/`, then for the config file to be mounted in the Docker container at `/data/config.yaml`, it must be located on the local computer at `~/drone_data/config.yaml`. However, the config file location can be overridden by passing a different location following an optional command line argument `--config-file` of the `docker run` command. For more information click [here](#custom-location-of-the-metashape-configuration-file).

Within the `config.yml` you will need to edit some of the project level parameters to specify where to find input images and where to put output products within the container. Within this config file, all paths will be relative to the file structure of the docker container (beginning with `/data/`). In the config.yaml, at a minimum the following entries should be updated:

* The value for 'photo_path' should be updated to `/data/{path_to_images_folder_within_mounted_folder}`
* The value for 'output_path' should be updated to `/data/{path_to_desired_ouputs_folder_within_mounted_folder}` (can be any location you want; will be created if it does not exist)
* The value for 'project_path' should be updated similarly as for 'output_path'.

<br/>

### Metashape license
Users need to provide a license to use Metashape. Currently, this docker method only supports a floating license server using the format `<IP address>:<port number>`. Within a terminal, users can declare the floating license as an environment variable using the command:

`export AGISOFT_FLS=<IP_address>:<port_number>`

Keep in mind that environment variables will not persist across different terminal sessions. 

<br/>

### Enable GPUs for accelerated processing

The use of graphical processing units (GPUs) can greatly increase the speed of photogrammetry processing. If your machine has GPU hardware, you will need extra software so docker can find and use your GPUs. Linux users simply need to install nvidia-container-toolkit via `sudo apt install nvidia-container-toolkit`. For Windows users please see [this documentation](https://docs.docker.com/desktop/features/gpu/). For macOS user, it may not be possible to use your local GPU (Apple Silicon) through Docker. 

<br/>

### Run the docker container
From a terminal, run this command: 

`docker run -v </host/data/dir>:/data -e AGISOFT_FLS=$AGISOFT_FLS --gpus all ghcr.io/open-forest-observatory/automate-metashape`

Here is a breakdown of the command:

`docker run` is the command to run a docker image

`-v </host/data/dir>:/data` is mounting a volume from your local computer into the container. We are mounting your directory that has the imagery and config file (</host/data/dir>) into the container at the path "/data".

`-e AGISOFT_FLS=$AGISOFT_FLS` is declaring your floating license to use Metashape. We set the license info as an environmental variable earlier in these instructions (i.e., `export AGISOFT_FLS=<IP_address>:<port_number>`)

`--gpus all` If the container has access to your local GPUs, use this flag to enable it.

`ghcr.io/open-forest-observatory/automate-metashape` This is the docker image that has the software to run the `automate-metashape` script. It is located in the Github container registry. When you execute the `docker run...` command, it will download the container image to your local machine and start the script to process imagery using Metashape. 

<br/>

#### Custom location of the Metashape configuration file

If your config.yaml is located anywhere other than `/data/config.yaml` (or the file is named differently), you can specify its location following one additional command line argument `--config-file` at the end of the `docker run` command. For example, if it is located in the container at `/data/configs/project_10/config.yml` (meanining, in the example above, it is located on your local computer at `~/drone_data/configs/project_10/config.yml`), just append `--config-file /data/configs/project_10/config.yml` to the `docker run` command above. So the command above would look like:

`docker run -v </host/data/dir>:/data -e AGISOFT_FLS=$AGISOFT_FLS --gpus all ghcr.io/open-forest-observatory/automate-metashape --config-file /data/configs/project_10/config.yml`

<br/>

#### License Retry Wrapper (Docker)

When using a floating license server in environments where license availability may be intermittent, you can use the license retry wrapper to automatically retry if no license is available.

To use the wrapper instead of running `metashape_workflow.py` directly, override the container's entrypoint:

```bash
docker run -v </host/data/dir>:/data \
  -e AGISOFT_FLS=$AGISOFT_FLS \
  -e LICENSE_RETRY_INTERVAL=300 \
  -e LICENSE_MAX_RETRIES=-1 \
  --gpus all \
  --entrypoint python3 \
  ghcr.io/open-forest-observatory/automate-metashape \
  /app/python/license_retry_wrapper.py --config-file /data/config.yml
```

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `LICENSE_MAX_RETRIES` | `0` | Maximum retry attempts. `0` = no retries (fail immediately), `-1` = unlimited, `>0` = that many retries |
| `LICENSE_RETRY_INTERVAL` | `300` | Seconds to wait between retry attempts |
| `LICENSE_CHECK_LINES` | `20` | Number of output lines to monitor for license errors |
| `PROGRESS_INTERVAL_PCT` | `1` | Print progress every N percent (e.g., `10` prints at 10%, 20%, 30%...) |
| `LOG_HEARTBEAT_INTERVAL` | `60` | Seconds between heartbeat status lines. `0` = full output mode (print all lines) |
| `LOG_BUFFER_SIZE` | `100` | Number of lines kept in circular buffer for error context dump on failure |
| `LOG_OUTPUT_DIR` | _(unset)_ | Optional override for full log file directory |

The wrapper monitors Metashape's startup output for license errors. If detected, it terminates the process immediately (before wasting compute time on processing that would fail at save), waits the specified interval, and retries. This is particularly useful in orchestrated environments like Kubernetes/Argo where multiple workflows may compete for floating licenses.

The wrapper also includes an output monitor with progress callbacks, periodic heartbeat messages, error context buffering, and full log file output. See the [Output Monitoring and Heartbeat](#output-monitoring-and-heartbeat) section above for details.

<br/>

### Outputs

As the processing runs, the completed imagery products will be saved into the folder you specified for the `output_path` parameter in the config.yaml. In the example above, if your config.yaml specifies the `output_path` as `/data/{path_to_desired_ouputs_folder_within_mounted_folder}`, the outputs will be saved on your local computer at `~/drone_data/{path_to_desired_ouputs_folder_within_mounted_folder}`.

<br/>

### Permissions on Linux

If running Docker on Linux without `sudo` (as in this example), your user will need to be in the `docker` group. This can be achieved with `sudo usermod -a -G docker $USER` and then logging out and in, as explained [here](https://docs.docker.com/engine/install/linux-postinstall/).

Note that the owner of the output data will be the `root` user. To set the ownership to your user account, you can run `sudo chown <username>:<username> <file name>` or `sudo chown <username>:<username> -R <folder name>`.


<br/>
<br/>

--- 

<br/>

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

<br/>



