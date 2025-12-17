#### Import libraries
import collections
import datetime
import glob
import json
import os
import platform
import re

# Import the fuctionality we need to make time stamps to measure performance
import time
from pathlib import Path

### Import the Metashape functionality
import Metashape
import yaml
from benchmark_monitor import BenchmarkMonitor


#### Helper functions
def recursive_update(d, u):
    """ "
    Recursively update dictionary `d` with any keys from `u`. New keys contained in `u` but not in `d`
    will be created.

    Taken from: https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    """
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = recursive_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def make_derived_yaml(input_path: str, output_path: str, override_options: dict):
    """Create a new config file by reading one file and updating specific values

    Args:
        input_path (str):
            The path to the yaml config file to load from
        output_path (str):
            The path to the yaml config file to write out. Containing folder will be created if needed.
        override_options (dict):
            A potentially-nested dictionary
    """
    # Read the input config
    with open(input_path, "r") as ymlfile:
        base_cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

    # Update the values in the base config
    updated_config = recursive_update(base_cfg, override_options)

    # Create the output folder if needed
    Path(output_path).parent.mkdir(exist_ok=True, parents=True)

    # Write out the updated config
    with open(output_path, "w") as ymlfile:
        # Preserve the initial order of keys for readability
        yaml.dump(updated_config, ymlfile, sort_keys=False)


def convert_objects(a_dict):
    """
    Convert strings that refer to metashape objects (e.g. "Metashape.MoasicBlending") into metashape objects

    Based on
    https://stackoverflow.com/a/25896596/237354
    """
    for k, v in a_dict.items():
        if not isinstance(v, dict):
            if isinstance(v, str):
                # TODO look for Metashape.
                if (
                    v
                    and "Metashape" in v
                    and not ("path" in k)
                    and not ("project" in k)
                    and not ("name" in k)
                ):  # allow "path" and "project" and "name" keys (e.g. "photoset_path" and "project_name") from YAML to include "Metashape" (e.g., Metashape in the filename)
                    a_dict[k] = eval(v)
            elif isinstance(v, list):
                # skip if no item in list have metashape, else convert string to metashape object
                if any("Metashape" in item for item in v):
                    a_dict[k] = [eval(item) for item in v if ("Metashape" in item)]
        else:
            convert_objects(v)


def stamp_time():
    """
    Format the timestamps as needed
    """
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M")
    return stamp


def detect_config_format(cfg):
    """
    Detect whether a config uses old or new format.

    Old format: Global settings at top level (photo_path, project_path, etc.)
    New format: Global settings under 'project:' section

    Args:
        cfg (dict): Configuration dictionary

    Returns:
        str: 'old' or 'new'
    """
    # Check for old format indicators: top-level global settings
    old_format_keys = ['photo_path', 'project_path', 'output_path', 'run_name', 'project_name']
    has_old_format = any(key in cfg for key in old_format_keys)

    # Check for new format indicator: 'project' section with nested settings
    has_new_format = 'project' in cfg and isinstance(cfg['project'], dict)

    if has_new_format:
        return 'new'
    elif has_old_format:
        return 'old'
    else:
        # Default to new format if unclear
        return 'new'


def migrate_config_to_new_format(old_cfg):
    """
    Migrate a config from old format to new format.

    Old format changes:
    - Global settings at top level → moved to 'project:' section
    - alignPhotos → split into match_photos and align_cameras
    - addPhotos → add_photos
    - calibrateReflectance → calibrate_reflectance
    - addGCPs → add_gcps
    - filterPointsUSGS → filter_points_usgs
    - optimizeCameras → optimize_cameras
    - exportCameras → export_cameras
    - buildDepthMaps → build_depth_maps
    - buildPointCloud → build_point_cloud
    - classifyGroundPoints → classify_ground_points (stays as is, just for reference)
    - buildMesh → build_mesh
    - buildDem → build_dem
    - buildOrthomosaic → build_orthomosaic

    Args:
        old_cfg (dict): Configuration in old format

    Returns:
        dict: Configuration in new format
    """
    new_cfg = {}

    # Create project section with global settings
    new_cfg['project'] = {
        'load_project': old_cfg.get('load_project', ''),
        'photo_path': old_cfg.get('photo_path', ''),
        'photo_path_secondary': old_cfg.get('photo_path_secondary', ''),
        'project_path': old_cfg.get('project_path', ''),
        'output_path': old_cfg.get('output_path', ''),
        'project_crs': old_cfg.get('project_crs', 'EPSG::26910'),
        'project_name': old_cfg.get('run_name', old_cfg.get('project_name', '')),  # Support both old run_name and new project_name
        'subdivide_task': old_cfg.get('subdivide_task', True),
    }

    # Migrate add_photos (rename from addPhotos)
    if 'addPhotos' in old_cfg:
        new_cfg['add_photos'] = old_cfg['addPhotos'].copy()

    # Migrate calibrate_reflectance (rename from calibrateReflectance)
    if 'calibrateReflectance' in old_cfg:
        new_cfg['calibrate_reflectance'] = old_cfg['calibrateReflectance'].copy()

    # Split alignPhotos into match_photos and align_cameras
    if 'alignPhotos' in old_cfg:
        align_photos = old_cfg['alignPhotos']

        # match_photos section
        new_cfg['match_photos'] = {
            'enabled': align_photos.get('enabled', True),
            'downscale': align_photos.get('downscale', 2),
            'generic_preselection': align_photos.get('generic_preselection', True),
            'reference_preselection': align_photos.get('reference_preselection', True),
            'reference_preselection_mode': align_photos.get('reference_preselection_mode', 'Metashape.ReferencePreselectionSource'),
            'keep_keypoints': align_photos.get('keep_keypoints', True),
        }

        # align_cameras section
        new_cfg['align_cameras'] = {
            'enabled': align_photos.get('enabled', True),
            'adaptive_fitting': align_photos.get('adaptive_fitting', True),
            'reset_alignment': align_photos.get('reset_alignment', False),
        }

    # Migrate add_gcps (rename from addGCPs)
    if 'addGCPs' in old_cfg:
        new_cfg['add_gcps'] = old_cfg['addGCPs'].copy()

    # Migrate filter_points_usgs (rename from filterPointsUSGS)
    if 'filterPointsUSGS' in old_cfg:
        new_cfg['filter_points_usgs'] = old_cfg['filterPointsUSGS'].copy()

    # Migrate optimize_cameras (rename from optimizeCameras)
    if 'optimizeCameras' in old_cfg:
        new_cfg['optimize_cameras'] = old_cfg['optimizeCameras'].copy()

    # Migrate export_cameras (rename from exportCameras)
    if 'exportCameras' in old_cfg:
        new_cfg['export_cameras'] = old_cfg['exportCameras'].copy()

    # Migrate build_depth_maps (rename from buildDepthMaps)
    if 'buildDepthMaps' in old_cfg:
        new_cfg['build_depth_maps'] = old_cfg['buildDepthMaps'].copy()

    # Migrate build_point_cloud (rename from buildPointCloud)
    if 'buildPointCloud' in old_cfg:
        new_cfg['build_point_cloud'] = old_cfg['buildPointCloud'].copy()

    # Migrate classify_ground_points (rename from classifyGroundPoints)
    if 'classifyGroundPoints' in old_cfg:
        new_cfg['classify_ground_points'] = old_cfg['classifyGroundPoints'].copy()

    # Migrate build_mesh (rename from buildMesh)
    if 'buildMesh' in old_cfg:
        new_cfg['build_mesh'] = old_cfg['buildMesh'].copy()

    # Migrate build_dem (rename from buildDem)
    if 'buildDem' in old_cfg:
        new_cfg['build_dem'] = old_cfg['buildDem'].copy()

    # Migrate build_orthomosaic (rename from buildOrthomosaic)
    if 'buildOrthomosaic' in old_cfg:
        new_cfg['build_orthomosaic'] = old_cfg['buildOrthomosaic'].copy()

    return new_cfg


def diff_time(t2, t1):
    """
    Give a end and start time, subtract, and round
    """
    total = str(round(t2 - t1, 1))
    return total


# Used by add_gcps function
def get_marker(chunk, label):
    for marker in chunk.markers:
        if marker.label == label:
            return marker
    return None


# Used by add_gcps function
def get_camera(chunk, label):
    for camera in chunk.cameras:
        if camera.label.lower() == label.lower():
            return camera
    return None


# TODO: Consider moving log to json/yaml formatting using a dict


class MetashapeWorkflow:

    sep = ": "

    def __init__(
        self,
        config_file,
        override_dict,
    ):
        """
        Initializes an instance of the MetashapeWorkflow class based on the config file given
        """
        self.config_file = config_file
        self.doc = None
        self.log_file = None
        self.yaml_log_file = None
        self.run_id = None
        self.cfg = None
        # track the written paths
        self.written_paths = {}
        # benchmark monitor for performance logging
        self.benchmark = None
        # Parse the yaml confif
        self.read_yaml()
        # Apply any manual overrides
        self.override_config(override_dict)
        # Convert the objects in the config to metashape objects
        convert_objects(self.cfg)

    def read_yaml(self):
        with open(self.config_file, "r") as ymlfile:
            self.cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

        # Auto-detect and migrate old config format to new format
        config_format = detect_config_format(self.cfg)
        if config_format == 'old':
            print(f"Detected old config format. Auto-migrating to new format...")
            self.cfg = migrate_config_to_new_format(self.cfg)
            print(f"Config migration complete.")

    def override_config(self, override_dict):
        """
        Update self.cfg using a potentially-nested dictionary of override values, in the same
        stucture as the yaml config file.

        Note: CLI overrides for project-level settings (photo_path, project_path, output_path,
        project_name, project_crs) are mapped to the project section if using new config format.
        """
        # Map CLI overrides to project section for new config format
        # Support both old 'run_name' and new 'project_name' for backward compatibility
        project_keys = ['photo_path', 'photo_path_secondary', 'project_path', 'output_path', 'project_name', 'run_name', 'project_crs']

        # Create a modified override dict that properly nests project settings
        modified_override = {}
        for key, value in override_dict.items():
            # Map old 'run_name' to new 'project_name' for backward compatibility
            if key == 'run_name':
                key = 'project_name'
            if key in project_keys:
                # Map to project section
                if 'project' not in modified_override:
                    modified_override['project'] = {}
                modified_override['project'][key] = value
            else:
                # Keep other overrides at top level
                modified_override[key] = value

        # Update any of the fields in the override dict to that value
        self.cfg = recursive_update(self.cfg, modified_override)

    #### Functions for each major step in Metashape

    def run_step(self, step_name):
        """
        Run a single processing step.

        For the 'setup' step, creates a new project (overwriting if exists).
        For all other steps, loads the existing project first.

        Args:
            step_name (str): Name of the step to run. Valid steps: setup, match_photos,
                align_cameras, build_depth_maps, build_point_cloud, build_mesh,
                build_dem_orthomosaic, match_photos_secondary, align_cameras_secondary, finalize

        Raises:
            ValueError: If step_name is invalid or prerequisites not met
        """
        valid_steps = [
            "setup",
            "match_photos",
            "align_cameras",
            "build_depth_maps",
            "build_point_cloud",
            "build_mesh",
            "build_dem_orthomosaic",
            "match_photos_secondary",
            "align_cameras_secondary",
            "finalize",
        ]

        if step_name not in valid_steps:
            raise ValueError(
                f"Invalid step name: '{step_name}'. Valid steps are: {', '.join(valid_steps)}"
            )

        if step_name == "setup":
            # Setup step creates new project (may overwrite existing)
            self.validate_prerequisites(step_name)
            self.setup()
        else:
            # All other steps load existing project first
            self.load_existing_project()
            self.validate_prerequisites(step_name)
            method = getattr(self, step_name)
            method()

    def load_existing_project(self):
        """
        Load existing project for step-based execution.

        Constructs the expected project file path and loads it. Also sets up
        instance variables needed for logging and benchmarking.

        Raises:
            ValueError: If project file doesn't exist
        """
        # Construct the expected project file path (same logic as project_setup)
        project_name = self.cfg["project"]["project_name"]
        if project_name == "from_config_filename" or project_name == "":
            file_basename = os.path.basename(self.config_file)
            project_name, _ = os.path.splitext(file_basename)

        project_file = os.path.join(self.cfg["project"]["project_path"], ".".join([project_name, "psx"]))

        if not os.path.exists(project_file):
            raise ValueError(
                f"Project file not found: {project_file}\n"
                f"Run the 'setup' step first to create the project."
            )

        # Load the project
        self.doc = Metashape.Document()
        self.doc.open(project_file)

        # Set up instance variables (same as project_setup)
        self.run_id = project_name
        self.log_file = os.path.join(
            self.cfg["project"]["output_path"], ".".join([self.run_id + "_log", "txt"])
        )
        self.yaml_log_file = os.path.join(
            self.cfg["project"]["output_path"], f"{self.run_id}_metrics.yaml"
        )
        self.benchmark = BenchmarkMonitor(
            self.log_file, self.yaml_log_file, self._get_system_info
        )

    def validate_prerequisites(self, step_name):
        """
        Validate that prerequisites for a step are met.

        Args:
            step_name (str): Name of the step to validate

        Raises:
            ValueError: If prerequisites not met, with message indicating what's missing
                       and which step(s) need to run first.
        """
        # Steps without prerequisites: setup, match_photos, match_photos_secondary, finalize
        # Only check prerequisites for steps that require prior state
        prereqs = {
            "align_cameras": {
                "check": lambda: self.doc.chunk.tie_points is not None,
                "error": "Tie points not found. Run 'match_photos' step first.",
            },
            "build_depth_maps": {
                "check": lambda: len([c for c in self.doc.chunk.cameras if c.transform])
                > 0,
                "error": "No aligned cameras found. Run 'align_cameras' step first.",
            },
            "build_point_cloud": {
                "check": lambda: self.doc.chunk.depth_maps is not None,
                "error": "Depth maps not found. Run 'build_depth_maps' step first.",
            },
            "build_mesh": {
                "check": lambda: self.doc.chunk.depth_maps is not None,
                "error": "Depth maps not found. Run 'build_depth_maps' step first.",
            },
            "build_dem_orthomosaic": {
                "check": lambda: self.doc.chunk.point_cloud is not None
                or self.doc.chunk.model is not None,
                "error": "Neither point cloud nor mesh model found. Run 'build_point_cloud' or 'build_mesh' step first.",
            },
            "align_cameras_secondary": {
                "check": lambda: self.doc.chunk.tie_points is not None,
                "error": "Tie points not found. Run 'match_photos' step first (and 'match_photos_secondary' if aligning secondary cameras).",
            },
        }

        if step_name in prereqs:
            if not prereqs[step_name]["check"]():
                raise ValueError(
                    f"Prerequisites not met for step '{step_name}': {prereqs[step_name]['error']}"
                )

    #### Step methods

    def setup(self):
        """
        Setup step: Initialize project and add photos.

        This step:
        - Creates project directories and project file
        - Enables and logs GPU configuration
        - Adds photos if configured
        - Calibrates reflectance if configured
        """
        self.project_setup()
        self.enable_and_log_gpu()

        # Optional operation: add photos (check config)
        if (self.cfg["project"]["photo_path"] != "") and (
            self.cfg["add_photos"]["enabled"]
        ):
            self.add_photos()

        # Optional operation: calibrate reflectance (check config)
        if self.cfg["calibrate_reflectance"]["enabled"]:
            self.calibrate_reflectance()

        self.doc.save()

    def match_photos(self):
        """
        Match photos step: Find tie points between photos.

        This step runs Metashape's matchPhotos function to identify
        matching features between photos.
        """
        self.benchmark.set_step_name("match_photos")

        with self.benchmark.monitor("matchPhotos"):
            self.doc.chunk.matchPhotos(
                downscale=self.cfg["match_photos"]["downscale"],
                subdivide_task=self.cfg["project"]["subdivide_task"],
                keep_keypoints=self.cfg["match_photos"]["keep_keypoints"],
                generic_preselection=self.cfg["match_photos"]["generic_preselection"],
                reference_preselection=self.cfg["match_photos"]["reference_preselection"],
                reference_preselection_mode=self.cfg["match_photos"]["reference_preselection_mode"],
            )

        self.doc.save()

    def align_cameras(self):
        """
        Align cameras step: Estimate camera positions and perform post-alignment operations.

        This step:
        - Aligns cameras using tie points from match_photos
        - Resets the region
        - Optionally filters points (USGS part 1)
        - Optionally adds GCPs
        - Optionally optimizes cameras
        - Optionally filters points (USGS part 2)
        - Optionally exports cameras
        """
        self.benchmark.set_step_name("align_cameras")

        with self.benchmark.monitor("alignCameras"):
            self.doc.chunk.alignCameras(
                adaptive_fitting=self.cfg["align_cameras"]["adaptive_fitting"],
                subdivide_task=self.cfg["project"]["subdivide_task"],
                reset_alignment=self.cfg["align_cameras"]["reset_alignment"],
            )

        self.doc.save()
        self.reset_region()

        # Post-alignment operations
        if self.cfg["filter_points_usgs"]["enabled"]:
            self.filter_points_usgs_part1()
            self.reset_region()

        if self.cfg["add_gcps"]["enabled"]:
            self.add_gcps()
            self.reset_region()

        if self.cfg["optimize_cameras"]["enabled"]:
            self.optimize_cameras()
            self.reset_region()

        if self.cfg["filter_points_usgs"]["enabled"]:
            self.filter_points_usgs_part2()
            self.reset_region()

        if self.cfg["export_cameras"]["enabled"]:
            self.export_cameras()

    def match_photos_secondary(self):
        """
        Match secondary photos step: Add and match secondary photos.

        This step:
        - Validates that keep_keypoints=True and reset_alignment=False
        - Adds secondary photos from configured path
        - Matches them to existing tie points

        Secondary photos are matched to the existing tie points from primary photos
        without affecting the primary photogrammetry products.
        """
        # Validate config settings
        if self.cfg["align_cameras"]["reset_alignment"] == True:
            raise ValueError(
                "For aligning secondary photos, reset_alignment must be False."
            )
        if self.cfg["match_photos"]["keep_keypoints"] == False:
            raise ValueError(
                "For aligning secondary photos, keep_keypoints must be True."
            )

        self.benchmark.set_step_name("match_photos_secondary")

        # Add the secondary photos
        self.add_photos(secondary=True, log_header=False)

        # Match the secondary photos (only newly added photos will be matched)
        with self.benchmark.monitor("matchPhotos (secondary)"):
            self.doc.chunk.matchPhotos(
                downscale=self.cfg["match_photos"]["downscale"],
                subdivide_task=self.cfg["project"]["subdivide_task"],
                keep_keypoints=self.cfg["match_photos"]["keep_keypoints"],
                generic_preselection=self.cfg["match_photos"]["generic_preselection"],
                reference_preselection=self.cfg["match_photos"]["reference_preselection"],
                reference_preselection_mode=self.cfg["match_photos"]["reference_preselection_mode"],
            )

        self.doc.save()

    def align_cameras_secondary(self):
        """
        Align secondary cameras step: Align secondary cameras and optionally export.

        This step:
        - Aligns secondary cameras (only unaligned cameras are affected)
        - Optionally exports camera positions if configured

        Note: Primary photos are not re-aligned because reset_alignment=False.
        """
        self.benchmark.set_step_name("align_cameras_secondary")

        with self.benchmark.monitor("alignCameras (secondary)"):
            self.doc.chunk.alignCameras(
                adaptive_fitting=self.cfg["align_cameras"]["adaptive_fitting"],
                subdivide_task=self.cfg["project"]["subdivide_task"],
                reset_alignment=self.cfg["align_cameras"]["reset_alignment"],
            )

        self.doc.save()

        # Optionally export cameras after aligning secondary photos
        if self.cfg["export_cameras"]["enabled"]:
            self.export_cameras()

    def finalize(self):
        """
        Finalize step: Clean up and generate reports.

        This step:
        - Optionally removes point cloud from project if configured
        - Exports processing report
        - Writes completion timestamp to log
        """
        # Optional operation: remove point cloud after export
        if self.cfg["build_point_cloud"]["enabled"] and self.cfg["build_point_cloud"]["remove_after_export"]:
            self.remove_point_cloud()

        self.export_report()
        self.finish_run()

        self.doc.save()

    def remove_point_cloud(self):
        """
        Remove point cloud from project to reduce file size.

        This is typically called after all point-cloud-derived products
        (DEMs, orthomosaics) have been exported.
        """
        self.doc.chunk.remove(self.doc.chunk.point_clouds)
        self.doc.save()

    def _get_system_info(self):
        """Gather system information for logging."""
        gpustringraw = str(Metashape.app.enumGPUDevices())
        gpucount = gpustringraw.count("name': '")
        gpustring = ""
        currentgpu = 1
        while gpucount >= currentgpu:
            if gpustring != "":
                gpustring = gpustring + ", "
            gpustring = (
                gpustring + gpustringraw.split("name': '")[currentgpu].split("',")[0]
            )
            currentgpu = currentgpu + 1

        return {
            "node": platform.node(),
            "cpu": platform.processor(),
            "cpu_cores_available": os.cpu_count(),
            "gpu_count": gpucount,
            "gpu_model": gpustring,
            "gpu_mask": Metashape.app.gpu_mask,
        }

    def run(self):
        """
        Execute metashape workflow steps based on config file
        """
        self.setup()

        if self.cfg["match_photos"]["enabled"]:
            self.match_photos()

        if self.cfg["align_cameras"]["enabled"]:
            self.align_cameras()

        if self.cfg["build_depth_maps"]["enabled"]:
            self.build_depth_maps()

        if self.cfg["build_point_cloud"]["enabled"]:
            self.build_point_cloud()

        if self.cfg["build_mesh"]["enabled"]:
            self.build_mesh()

        # For this step, the check for whether it is enabled in the config happens inside the function, because there are two steps (DEM and ortho), each of which can be enabled independently
        self.build_dem_orthomosaic()

        if self.cfg["project"]["photo_path_secondary"] != "":
            self.match_photos_secondary()
            self.align_cameras_secondary()

        self.finalize()

    def project_setup(self):
        """
        Create output and project paths, if they don't exist
        Define a project ID based on specified project name and timestamp
        Define a project filename and a log filename
        Create the project
        Start a log file
        """

        # Make project directories (necessary even if loading an existing project because this workflow saves a new project based on the old one, leaving the old one intact
        if not os.path.exists(self.cfg["project"]["output_path"]):
            os.makedirs(self.cfg["project"]["output_path"])
        if not os.path.exists(self.cfg["project"]["project_path"]):
            os.makedirs(self.cfg["project"]["project_path"])

        ### Set a filename template for project files and output files based on the 'project_name' key of the config YML
        ## BUT if the value for project_name is "from_config_filename", then use the config filename for the project name.

        project_name = self.cfg["project"]["project_name"]

        if project_name == "from_config_filename" or project_name == "":
            file_basename = os.path.basename(
                self.config_file
            )  # extracts file base name from path
            project_name, _ = os.path.splitext(file_basename)  # removes extension

        self.run_id = project_name

        project_file = os.path.join(
            self.cfg["project"]["project_path"], ".".join([self.run_id, "psx"])
        )
        self.log_file = os.path.join(
            self.cfg["project"]["output_path"], ".".join([self.run_id + "_log", "txt"])
        )
        self.yaml_log_file = os.path.join(
            self.cfg["project"]["output_path"], f"{self.run_id}_metrics.yaml"
        )

        # Initialize benchmark monitor for performance logging
        # Pass _get_system_info as a callable so it can be called fresh for each API call
        # (since each step may run on a different node)
        self.benchmark = BenchmarkMonitor(
            self.log_file, self.yaml_log_file, self._get_system_info
        )

        """
        Create a doc and a chunk
        """

        # create a handle to the Metashape object
        self.doc = (
            Metashape.Document()
        )  # When running via Metashape, can use: doc = Metashape.app.document

        # If specified, open existing project
        if self.cfg["project"]["load_project"] != "":
            self.doc.open(self.cfg["project"]["load_project"])
        else:
            # Initialize a chunk, set its CRS as specified
            chunk = self.doc.addChunk()
            chunk.crs = Metashape.CoordinateSystem(self.cfg["project"]["project_crs"])
            chunk.marker_crs = Metashape.CoordinateSystem(
                self.cfg["add_gcps"]["gcp_crs"]
            )

        # Save doc doc as new project (even if we opened an existing project, save as a separate one so the existing project remains accessible in its original state)
        self.doc.save(project_file)

        """
        Log specs except for GPU
        """

        # log Metashape version, CPU specs, time, and project location to results file
        # open the results file
        # TODO: records the Slurm values for actual cpus and ram allocated
        # https://slurm.schedmd.com/sbatch.html#lbAI
        with open(self.log_file, "w") as file:

            # write a line with the Metashape version
            file.write(MetashapeWorkflow.sep.join(["Project", self.run_id]) + "\n")
            file.write(
                MetashapeWorkflow.sep.join(
                    ["Agisoft Metashape Professional Version", Metashape.app.version]
                )
                + "\n"
            )
            # write a line with the date and time
            file.write(
                MetashapeWorkflow.sep.join(["Processing started", stamp_time()]) + "\n"
            )
            # Node and system specs are now logged per-step

    def enable_and_log_gpu(self):
        """
        Configure GPU settings for Metashape
        """
        system_info = self._get_system_info()
        gpucount = system_info["gpu_count"]
        gpu_mask = system_info["gpu_mask"]

        # If GPUs exist but are not all enabled, enable all of them
        if gpucount > 0:
            # Create mask with all GPUs enabled (bitmask with gpucount bits set)
            all_gpus_mask = (1 << gpucount) - 1
            if gpu_mask != all_gpus_mask:
                Metashape.app.gpu_mask = all_gpus_mask

        # set Metashape to *not* use the CPU during GPU steps (appears to be standard wisdom)
        Metashape.app.cpu_enable = False

        # Write header for benchmark log
        with open(self.log_file, "a") as file:
            file.write(
                f"\n{'Step':<23} | {'API Call':<35} | {'Run Time':>8} | {'CPU %':>5} | {'GPU %':>5} | "
                f"{'CPUs':>4} | {'GPUs':>4} | {'GPU Model':<15} | {'Node':<15}\n"
            )

        return True

    def add_photos(self, secondary=False, log_header=True):
        """
        Add photos to project and change their labels to include their containing folder. Secondary: if
        True, this is a secondary set of photos to be aligned only, after all photogrammetry products
        have been produced from the primary set of photos.
        """

        if log_header:
            self.benchmark.set_step_name("setup")

        if secondary:
            photo_paths = self.cfg["project"]["photo_path_secondary"]
        else:
            photo_paths = self.cfg["project"]["photo_path"]

        # If it's a single string (i.e. one directory), make it a list of one string so we can iterate
        # over it the same as if it were a list of strings
        if isinstance(photo_paths, str):
            photo_paths = [photo_paths]

        for photo_path in photo_paths:

            grp = self.doc.chunk.addCameraGroup()

            ## Get paths to all the project photos
            a = glob.iglob(
                os.path.join(photo_path, "**", "*.*"), recursive=True
            )  # (([jJ][pP][gG])|([tT][iI][fF]))
            b = [path for path in a]
            photo_files = [
                x
                for x in b
                if (
                    re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)", x)
                    and (not re.search("dem_usgs.tif", x))
                )
            ]

            ## Add them
            if self.cfg["add_photos"]["multispectral"]:
                with self.benchmark.monitor("addPhotos"):
                    self.doc.chunk.addPhotos(
                        photo_files, layout=Metashape.MultiplaneLayout, group=grp
                    )
            else:
                with self.benchmark.monitor("addPhotos"):
                    self.doc.chunk.addPhotos(photo_files, group=grp)

        ## Need to change the label on each camera so that it includes the containing folder(s)
        for camera in self.doc.chunk.cameras:
            path = camera.photo.path
            camera.label = path

        if self.cfg["add_photos"]["separate_calibration_per_path"]:
            # Assign a different (new) sensor (i.e. independent calibration) to each group of photos
            for grp in self.doc.chunk.camera_groups:

                # Get the template for the sensor from the first photo in the group
                for cam in self.doc.chunk.cameras:
                    if cam.group == grp:
                        sensor = cam.sensor
                        break

                self.doc.chunk.addSensor(self.doc.chunk.cameras[0].sensor)
                sensor = self.doc.chunk.sensors[-1]

                for cam in self.doc.chunk.cameras:
                    if cam.group == grp:
                        cam.sensor = sensor

            # Remove the first (deafult) sensor, which should no longer be assigned to any photos
            self.doc.chunk.remove(self.doc.chunk.sensors[0])

        ## If specified, change the accuracy of the cameras to match the RTK flag (RTK fix if flag = 50, otherwise no fix
        if self.cfg["add_photos"]["use_rtk"]:
            for cam in self.doc.chunk.cameras:
                rtkflag = cam.photo.meta["DJI/RtkFlag"]
                if rtkflag == "50":
                    cam.reference.location_accuracy = Metashape.Vector(
                        [
                            self.cfg["add_photos"]["fix_accuracy"],
                            self.cfg["add_photos"]["fix_accuracy"],
                            self.cfg["add_photos"]["fix_accuracy"],
                        ]
                    )
                    cam.reference.accuracy = Metashape.Vector(
                        [
                            self.cfg["add_photos"]["fix_accuracy"],
                            self.cfg["add_photos"]["fix_accuracy"],
                            self.cfg["add_photos"]["fix_accuracy"],
                        ]
                    )
                else:
                    cam.reference.location_accuracy = Metashape.Vector(
                        [
                            self.cfg["add_photos"]["nofix_accuracy"],
                            self.cfg["add_photos"]["nofix_accuracy"],
                            self.cfg["add_photos"]["nofix_accuracy"],
                        ]
                    )
                    cam.reference.accuracy = Metashape.Vector(
                        [
                            self.cfg["add_photos"]["nofix_accuracy"],
                            self.cfg["add_photos"]["nofix_accuracy"],
                            self.cfg["add_photos"]["nofix_accuracy"],
                        ]
                    )

        # Set the sensor type (e.g. Frame camera, Spherical camera)
        self.set_sensor_type(self.cfg["add_photos"]["sensor_type"])

        self.doc.save()

        return True

    def set_sensor_type(self, sensor_type):
        """
        Sets the type of sensor used for data collection. Tested choices so far:
        Metashape.Sensor.Type.Frame, Metashape.Sensor.Type.Spherical.
        """
        for sensor in self.doc.chunk.sensors:
            sensor.type = sensor_type
        self.doc.save()
        return True

    def calibrate_reflectance(self):
        # TODO: Handle failure to find panels, or mulitple panel images by returning error to user.
        self.benchmark.set_step_name("setup")

        with self.benchmark.monitor("locateReflectancePanels"):
            self.doc.chunk.locateReflectancePanels()

        with self.benchmark.monitor("loadReflectancePanelCalibration"):
            self.doc.chunk.loadReflectancePanelCalibration(
                os.path.join(
                    self.cfg["project"]["photo_path"],
                    "calibration",
                    self.cfg["calibrate_reflectance"]["panel_filename"],
                )
            )

        with self.benchmark.monitor("calibrateReflectance"):
            self.doc.chunk.calibrateReflectance(
                use_reflectance_panels=self.cfg["calibrate_reflectance"][
                    "use_reflectance_panels"
                ],
                use_sun_sensor=self.cfg["calibrate_reflectance"]["use_sun_sensor"],
            )

        self.doc.save()

        return True

    def add_gcps(self):
        """
        Add GCPs (GCP coordinates and the locations of GCPs in individual photos.
        See the helper script (and the comments therein) for details on how to prepare the data needed by this function: R/prep_gcps.R
        """
        # Determine the location of the GCPs file, which is also the base path to prepend to the GCP
        # camera label (relative to what's specified in the GCPs file, which is a relative path), to
        # make it into an absolute path to match the label of the camera in the Metashape. Note the
        # difference between the two camera labels: one is the camera label specified in the GCPs file
        # (relative path), and one is the camera label in the Metashape (absolute). Currently, this
        # assumes that all of the GCPs apply to the first provided folder of cameras (i.e., the only
        # folder provided, or the first folder provided if multiple are provided) -- and that this is
        # the folder containing the GCP definition file. TODO: Tolerate GCPs split across multiple
        # folders of input images:
        # https://github.com/open-forest-observatory/automate-metashape-2/issues/49.

        photo_paths = self.cfg["project"]["photo_path"]

        # If it's a single string (i.e. one directory), make it a list of one string so we can take the
        # first element using the same operation we would use on a list of strings
        if isinstance(photo_paths, str):
            photo_paths = [photo_paths]

        # Take the first folder and assume it's the one with the GCPs file
        photo_path = photo_paths[0]

        ## Tag specific pixels in specific images where GCPs are located
        path = os.path.join(photo_path, "gcps", "prepared", "gcp_imagecoords_table.csv")
        file = open(path)
        content = file.read().splitlines()

        for line in content:
            marker_label, camera_label, x_proj, y_proj = line.split(",")
            if (
                marker_label[0] == '"'
            ):  # if it's in quotes (from saving CSV in Excel), remove quotes
                marker_label = marker_label[
                    1:-1
                ]  # need to get it out of the two pairs of quotes
            if (
                camera_label[0] == '"'
            ):  # if it's in quotes (from saving CSV in Excel), remove quotes
                camera_label = camera_label[1:-1]

            marker = get_marker(self.doc.chunk, marker_label)
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = marker_label

            # Prepend the image path to the GCP's camera label to make it an absolute path
            camera_label = os.path.join(photo_path, camera_label)

            camera = get_camera(self.doc.chunk, camera_label)
            if not camera:
                print(camera_label + " camera not found in project")
                continue

            marker.projections[camera] = Metashape.Marker.Projection(
                (float(x_proj), float(y_proj)), True
            )

        ## Assign real-world coordinates to each GCP
        path = os.path.join(photo_path, "gcps", "prepared", "gcp_table.csv")

        file = open(path)
        content = file.read().splitlines()

        for line in content:
            marker_label, world_x, world_y, world_z = line.split(",")
            if (
                marker_label[0] == '"'
            ):  # if it's in quotes (from saving CSV in Excel), remove quotes
                marker_label = marker_label[
                    1:-1
                ]  # need to get it out of the two pairs of quotes

            marker = get_marker(self.doc.chunk, marker_label)
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = marker_label

            marker.reference.location = (float(world_x), float(world_y), float(world_z))
            marker.reference.accuracy = (
                self.cfg["add_gcps"]["marker_location_accuracy"],
                self.cfg["add_gcps"]["marker_location_accuracy"],
                self.cfg["add_gcps"]["marker_location_accuracy"],
            )

        self.doc.chunk.marker_location_accuracy = (
            self.cfg["add_gcps"]["marker_location_accuracy"],
            self.cfg["add_gcps"]["marker_location_accuracy"],
            self.cfg["add_gcps"]["marker_location_accuracy"],
        )
        self.doc.chunk.marker_projection_accuracy = self.cfg["add_gcps"][
            "marker_projection_accuracy"
        ]

        self.doc.save()

        return True

    def export_cameras(self):
        self.benchmark.set_step_name("align_cameras")

        output_file = os.path.join(
            self.cfg["project"]["output_path"], self.run_id + "_cameras.xml"
        )
        # Defaults to xml format, which is the only one we've used so far
        with self.benchmark.monitor("exportCameras"):
            self.doc.chunk.exportCameras(path=output_file)
        self.written_paths["camera_export"] = output_file  # export

    def reset_region(self):
        """
        Reset the region and make it much larger than the points; necessary because if points go outside the region, they get clipped when saving
        """

        self.doc.chunk.resetRegion()
        region_dims = self.doc.chunk.region.size
        region_dims[2] *= 3
        self.doc.chunk.region.size = region_dims

        return True

    def optimize_cameras(self):
        """
        Optimize cameras
        """

        self.benchmark.set_step_name("align_cameras")

        # Disable camera locations as reference if specified in YML
        if (
            self.cfg["add_gcps"]["enabled"]
            and self.cfg["add_gcps"]["optimize_w_gcps_only"]
        ):
            n_cameras = len(self.doc.chunk.cameras)
            for i in range(0, n_cameras):
                self.doc.chunk.cameras[i].reference.enabled = False

        with self.benchmark.monitor("optimizeCameras"):
            self.doc.chunk.optimizeCameras(
                adaptive_fitting=self.cfg["optimize_cameras"]["adaptive_fitting"]
            )

        self.doc.save()

        return True

    def filter_points_usgs_part1(self):

        self.benchmark.set_step_name("align_cameras")

        with self.benchmark.monitor("optimizeCameras"):
            self.doc.chunk.optimizeCameras(
                adaptive_fitting=self.cfg["optimize_cameras"]["adaptive_fitting"]
            )

        rec_thresh_percent = self.cfg["filter_points_usgs"]["rec_thresh_percent"]
        rec_thresh_absolute = self.cfg["filter_points_usgs"]["rec_thresh_absolute"]
        proj_thresh_percent = self.cfg["filter_points_usgs"]["proj_thresh_percent"]
        proj_thresh_absolute = self.cfg["filter_points_usgs"]["proj_thresh_absolute"]
        reproj_thresh_percent = self.cfg["filter_points_usgs"]["reproj_thresh_percent"]
        reproj_thresh_absolute = self.cfg["filter_points_usgs"]["reproj_thresh_absolute"]

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ReconstructionUncertainty)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - rec_thresh_percent / 100))]
        if thresh < rec_thresh_absolute:
            thresh = rec_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        with self.benchmark.monitor("optimizeCameras"):
            self.doc.chunk.optimizeCameras(
                adaptive_fitting=self.cfg["optimize_cameras"]["adaptive_fitting"]
            )

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ProjectionAccuracy)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - proj_thresh_percent / 100))]
        if thresh < proj_thresh_absolute:
            thresh = proj_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        with self.benchmark.monitor("optimizeCameras"):
            self.doc.chunk.optimizeCameras(
                adaptive_fitting=self.cfg["optimize_cameras"]["adaptive_fitting"]
            )

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ReprojectionError)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
        if thresh < reproj_thresh_absolute:
            thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        with self.benchmark.monitor("optimizeCameras"):
            self.doc.chunk.optimizeCameras(
                adaptive_fitting=self.cfg["optimize_cameras"]["adaptive_fitting"]
            )

        self.doc.save()

    def filter_points_usgs_part2(self):

        self.benchmark.set_step_name("align_cameras")

        with self.benchmark.monitor("optimizeCameras"):
            self.doc.chunk.optimizeCameras(
                adaptive_fitting=self.cfg["optimize_cameras"]["adaptive_fitting"]
            )

        reproj_thresh_percent = self.cfg["filter_points_usgs"]["reproj_thresh_percent"]
        reproj_thresh_absolute = self.cfg["filter_points_usgs"]["reproj_thresh_absolute"]

        fltr = Metashape.TiePoints.Filter()
        fltr.init(self.doc.chunk, Metashape.TiePoints.Filter.ReprojectionError)
        values = fltr.values.copy()
        values.sort()
        thresh = values[int(len(values) * (1 - reproj_thresh_percent / 100))]
        if thresh < reproj_thresh_absolute:
            thresh = reproj_thresh_absolute  # don't throw away too many points if they're all good
        fltr.removePoints(thresh)

        with self.benchmark.monitor("optimizeCameras"):
            self.doc.chunk.optimizeCameras(
                adaptive_fitting=self.cfg["optimize_cameras"]["adaptive_fitting"]
            )

        self.doc.save()

    def classify_ground_points(self):

        with self.benchmark.monitor("classifyGroundPoints"):
            self.doc.chunk.point_cloud.classifyGroundPoints(
                max_angle=self.cfg["classify_ground_points"]["max_angle"],
                max_distance=self.cfg["classify_ground_points"]["max_distance"],
                cell_size=self.cfg["classify_ground_points"]["cell_size"],
            )

        self.doc.save()

    def build_depth_maps(self):
        """
        Build depth maps step: Generate depth maps from aligned photos.

        This step runs Metashape's buildDepthMaps function to create
        depth information for each photo, which will be used to build
        the dense point cloud or mesh model.
        """
        self.benchmark.set_step_name("build_depth_maps")

        with self.benchmark.monitor("buildDepthMaps"):
            self.doc.chunk.buildDepthMaps(
                downscale=self.cfg["build_depth_maps"]["downscale"],
                filter_mode=self.cfg["build_depth_maps"]["filter_mode"],
                reuse_depth=self.cfg["build_depth_maps"]["reuse_depth"],
                max_neighbors=self.cfg["build_depth_maps"]["max_neighbors"],
                subdivide_task=self.cfg["project"]["subdivide_task"],
            )

        self.doc.save()

    def build_point_cloud(self):
        """
        Build point cloud step: Generate dense 3D point cloud from depth maps.

        This step:
        - Builds dense point cloud from depth maps
        - Optionally classifies ground points if configured
        - Exports point cloud if configured
        - Optionally removes depth maps to save space if configured
        """
        self.benchmark.set_step_name("build_point_cloud")

        with self.benchmark.monitor("buildPointCloud"):
            self.doc.chunk.buildPointCloud(
                max_neighbors=self.cfg["build_point_cloud"]["max_neighbors"],
                keep_depth=self.cfg["build_point_cloud"]["keep_depth"],
                subdivide_task=self.cfg["project"]["subdivide_task"],
                point_colors=True,
            )

        self.doc.save()

        # classify ground points if specified
        if self.cfg["build_point_cloud"]["classify_ground_points"]:
            self.classify_ground_points()

        ### Export points

        if self.cfg["build_point_cloud"]["export"]:

            if (
                self.cfg["build_point_cloud"]["export_format"]
                == Metashape.PointCloudFormatCOPC
            ):
                export_file_ending = "_points-copc.laz"
            else:
                export_file_ending = "_points.laz"

            # Export the point cloud
            output_file = os.path.join(
                self.cfg["project"]["output_path"], self.run_id + export_file_ending
            )
            if self.cfg["build_point_cloud"]["classes"] == "ALL":
                # call without classes argument (Metashape then defaults to all classes)
                with self.benchmark.monitor("exportPointCloud"):
                    self.doc.chunk.exportPointCloud(
                        path=output_file,
                        source_data=Metashape.PointCloudData,
                        format=self.cfg["build_point_cloud"]["export_format"],
                        crs=Metashape.CoordinateSystem(self.cfg["project"]["project_crs"]),
                        subdivide_task=self.cfg["project"]["subdivide_task"],
                    )
                self.written_paths["point_cloud_all_classes"] = output_file  # export
            else:
                # call with classes argument
                with self.benchmark.monitor("exportPointCloud"):
                    self.doc.chunk.exportPointCloud(
                        path=output_file,
                        source_data=Metashape.PointCloudData,
                        format=Metashape.PointCloudFormatLAZ,
                        crs=Metashape.CoordinateSystem(self.cfg["project"]["project_crs"]),
                        classes=self.cfg["build_point_cloud"]["classes"],
                        subdivide_task=self.cfg["project"]["subdivide_task"],
                    )
                self.written_paths["point_cloud_subset_classes"] = output_file  # export

        return True

    def build_mesh(self):
        """
        Build mesh step: Generate and export 3D mesh model.

        This step:
        - Builds 3D mesh model from depth maps
        - Optionally applies coordinate frame shift if configured
        - Exports mesh model if configured
        """
        self.benchmark.set_step_name("build_mesh")

        with self.benchmark.monitor("buildModel"):
            self.doc.chunk.buildModel(
                surface_type=Metashape.Arbitrary,
                interpolation=Metashape.EnabledInterpolation,
                face_count=self.cfg["build_mesh"]["face_count"],
                face_count_custom=self.cfg["build_mesh"][
                    "face_count_custom"
                ],  # Only used if face_count is custom
                source_data=Metashape.DepthMapsData,
            )

        # Save the mesh
        self.doc.save()

        if self.cfg["build_mesh"]["export"]:

            # Check for whether shifting the coordinate frame is desired
            if self.cfg["build_mesh"]["shift_crs_to_cameras"] is True:
                shift = self.get_cameraset_origin()
            else:
                shift = Metashape.Vector([0, 0, 0])

            output_file = os.path.join(
                self.cfg["project"]["output_path"],
                self.run_id + "_mesh." + self.cfg["build_mesh"]["export_extension"],
            )
            # Export the georeferenced mesh in the project CRS. The metadata file is the only thing
            # that encodes the CRS.
            with self.benchmark.monitor("exportModel"):
                self.doc.chunk.exportModel(
                    path=output_file,
                    crs=Metashape.CoordinateSystem(self.cfg["project"]["project_crs"]),
                    save_metadata_xml=True,
                    shift=shift,
                )

        return True

    def build_dem_orthomosaic(self):
        """
        Build DEM and orthomosaic step.

        This step:
        - Optionally classifies ground points if configured
        - Builds DEMs based on configured surfaces (DTM-ptcloud, DSM-ptcloud, DSM-mesh)
        - Exports DEMs if configured
        - Builds orthomosaics on configured surfaces
        - Exports orthomosaics if configured
        - Optionally removes point cloud from project after export
        """
        # classify ground points if specified
        if self.cfg["build_dem"]["classify_ground_points"]:
            self.classify_ground_points()

        if self.cfg["build_dem"]["enabled"]:
            self.benchmark.set_step_name("build_dem_orthomosaic")

            # prepping params for buildDem
            projection = Metashape.OrthoProjection()
            projection.crs = Metashape.CoordinateSystem(self.cfg["project"]["project_crs"])

            # prepping params for export
            compression = Metashape.ImageCompression()
            compression.tiff_big = self.cfg["build_dem"]["tiff_big"]
            compression.tiff_tiled = self.cfg["build_dem"]["tiff_tiled"]
            compression.tiff_overviews = self.cfg["build_dem"]["tiff_overviews"]

            if "DSM-ptcloud" in self.cfg["build_dem"]["surface"]:
                with self.benchmark.monitor("buildDem (DSM-ptcloud)"):
                    self.doc.chunk.buildDem(
                        source_data=Metashape.PointCloudData,
                        subdivide_task=self.cfg["project"]["subdivide_task"],
                        projection=projection,
                        resolution=self.cfg["build_dem"]["resolution"],
                    )

                self.doc.chunk.elevation.label = "DSM-ptcloud"

                output_file = os.path.join(
                    self.cfg["project"]["output_path"], self.run_id + "_dsm-ptcloud.tif"
                )
                if self.cfg["build_dem"]["export"]:
                    with self.benchmark.monitor("exportRaster (DSM-ptcloud)"):
                        self.doc.chunk.exportRaster(
                            path=output_file,
                            projection=projection,
                            nodata_value=self.cfg["build_dem"]["nodata"],
                            source_data=Metashape.ElevationData,
                            image_compression=compression,
                        )
                    self.written_paths[f"DEM_{self.cfg['build_dem']['surface'][0]}"] = (
                        output_file  # export
                    )

            if "DTM-ptcloud" in self.cfg["build_dem"]["surface"]:
                with self.benchmark.monitor("buildDem (DTM-ptcloud)"):
                    self.doc.chunk.buildDem(
                        source_data=Metashape.PointCloudData,
                        classes=Metashape.PointClass.Ground,
                        subdivide_task=self.cfg["project"]["subdivide_task"],
                        projection=projection,
                        resolution=self.cfg["build_dem"]["resolution"],
                    )

                self.doc.chunk.elevation.label = "DTM-ptcloud"

                output_file = os.path.join(
                    self.cfg["project"]["output_path"], self.run_id + "_dtm-ptcloud.tif"
                )
                if self.cfg["build_dem"]["export"]:
                    with self.benchmark.monitor("exportRaster (DTM-ptcloud)"):
                        self.doc.chunk.exportRaster(
                            path=output_file,
                            projection=projection,
                            nodata_value=self.cfg["build_dem"]["nodata"],
                            source_data=Metashape.ElevationData,
                            image_compression=compression,
                        )

            if "DSM-mesh" in self.cfg["build_dem"]["surface"]:
                with self.benchmark.monitor("buildDem (DSM-mesh)"):
                    self.doc.chunk.buildDem(
                        source_data=Metashape.ModelData,
                        subdivide_task=self.cfg["project"]["subdivide_task"],
                        projection=projection,
                        resolution=self.cfg["build_dem"]["resolution"],
                    )

                self.doc.chunk.elevation.label = "DSM-mesh"

                output_file = os.path.join(
                    self.cfg["project"]["output_path"], self.run_id + "_dsm-mesh.tif"
                )
                if self.cfg["build_dem"]["export"]:
                    with self.benchmark.monitor("exportRaster (DSM-mesh)"):
                        self.doc.chunk.exportRaster(
                            path=output_file,
                            projection=projection,
                            nodata_value=self.cfg["build_dem"]["nodata"],
                            source_data=Metashape.ElevationData,
                            image_compression=compression,
                        )

        # Each DEM has a label associated with it which is used to identify and activate the correct DEM for orthomosaic generation
        if self.cfg["build_orthomosaic"]["enabled"]:
            self.benchmark.set_step_name("build_dem_orthomosaic")

            # Iterate through each specified surface in the configuration
            for surface in self.cfg["build_orthomosaic"]["surface"]:
                if surface == "Mesh":
                    # If the surface type is "Mesh", we do not need to activate an elevation model so we can go straight to building the orthomosaic
                    self.build_export_orthomosaic(from_mesh=True, file_ending="mesh")
                else:
                    # Otherwise, we need to activate the appropriate DEM based on the DEM labels assigned when the DEMs were generated
                    dem_found = False
                    # Iterate through all the available DEMs
                    for elevation in self.doc.chunk.elevations:
                        if elevation.label == surface:
                            # If the DEM label matches the surface, activate the appropriate DEM
                            self.doc.chunk.elevation = elevation
                            dem_found = True
                            break

                    if not dem_found:
                        raise ValueError(
                            f"Error: DEM for {surface} is not available.\n"
                            "Ensure the DEM for the specified surface has been generated because it is needed for orthomosaic generation."
                        )

                    self.build_export_orthomosaic(file_ending=surface.lower())

        self.doc.save()

        return True

    def build_export_orthomosaic(self, file_ending, from_mesh=False):
        """
        Helper function called by build_dem_orthomosaic. build_export_orthomosaic builds and exports an ortho based on the current elevation data.
        build_dem_orthomosaic sets the current elevation data and calls build_export_orthomosaic (one or more times depending on how many orthomosaics requested)

        Note that we have tried using the 'resolution' parameter of buildOrthomosaic, but it does not have any effect. An orthomosaic built onto a DSM always has a reslution of 1/4 the DSM, and one built onto the mesh has a resolution of ~the GSD.
        """

        # prepping params for buildDem
        projection = Metashape.OrthoProjection()
        projection.crs = Metashape.CoordinateSystem(self.cfg["project"]["project_crs"])

        if from_mesh:
            surface_data = Metashape.ModelData
        else:
            surface_data = Metashape.ElevationData

        with self.benchmark.monitor(f"buildOrthomosaic ({file_ending})"):
            self.doc.chunk.buildOrthomosaic(
                surface_data=surface_data,
                blending_mode=self.cfg["build_orthomosaic"]["blending"],
                fill_holes=self.cfg["build_orthomosaic"]["fill_holes"],
                refine_seamlines=self.cfg["build_orthomosaic"]["refine_seamlines"],
                subdivide_task=self.cfg["project"]["subdivide_task"],
                projection=projection,
            )

        self.doc.save()

        ## Export orthomosaic
        if self.cfg["build_orthomosaic"]["export"]:
            output_file = os.path.join(
                self.cfg["project"]["output_path"], self.run_id + "_ortho-" + file_ending + ".tif"
            )

            compression = Metashape.ImageCompression()
            compression.tiff_big = self.cfg["build_orthomosaic"]["tiff_big"]
            compression.tiff_tiled = self.cfg["build_orthomosaic"]["tiff_tiled"]
            compression.tiff_overviews = self.cfg["build_orthomosaic"]["tiff_overviews"]

            projection = Metashape.OrthoProjection()
            projection.crs = Metashape.CoordinateSystem(self.cfg["project"]["project_crs"])

            with self.benchmark.monitor(f"exportRaster (ortho-{file_ending})"):
                self.doc.chunk.exportRaster(
                    path=output_file,
                    projection=projection,
                    nodata_value=self.cfg["build_orthomosaic"]["nodata"],
                    source_data=Metashape.OrthomosaicData,
                    image_compression=compression,
                )
            self.written_paths["ortho_" + file_ending] = output_file  # export

        if self.cfg["build_orthomosaic"]["remove_after_export"]:
            self.doc.chunk.remove(self.doc.chunk.orthomosaics)

        return True

    def export_report(self):
        """
        Export report
        """

        self.benchmark.set_step_name("finalize")

        output_file = os.path.join(self.cfg["project"]["output_path"], self.run_id + "_report.pdf")

        with self.benchmark.monitor("exportReport"):
            self.doc.chunk.exportReport(path=output_file)
        self.written_paths["report"] = output_file  # export

        return True

    def finish_run(self):
        """
        Finish run (i.e., write completed time to log, write configuration to log)
        """

        # finish local results log and close it for the last time
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflow.sep.join(["Run Completed", stamp_time()]) + "\n"
            )

        # open run configuration again. We can't just use the existing self.cfg file because its objects had already been converted to Metashape objects (they don't write well)
        with open(self.config_file) as file:
            config_full = yaml.safe_load(file)

        # write the run configuration to the log file
        with open(self.log_file, "a") as file:
            file.write("\n\n### CONFIGURATION ###\n")
            documents = yaml.dump(config_full, file, default_flow_style=False)
            file.write("### END CONFIGURATION ###\n")

        return True

    def get_written_paths(self, as_json: bool = False):
        # Convert to a json string representation if requested
        if as_json:
            json_str = json.dumps(self.written_paths)
            return json_str
        # Otherwise just return the dictionary representation
        return self.written_paths

    def get_cameraset_origin(self, round: int = 100) -> Metashape.Vector:
        """
        Goes through the EXIF lat/lon data from the cameras, converts it into
        the project CRS, and then reports the (rounded) camera mean as the
        project origin. The purpose is to get around the accuracy limitations
        of float32 values (the default for point clouds and meshes) by having
        a fixed origin offset per project.

        NOTE: The shifted origin is reported by exportModel via the
        save_metadata_xml mechanism.

        Arguments:
            round (int): The value to round (really floor) the origin to. The
                purpose of this is to make the origin more human readable,
                while still getting the accuracy benefits that come when your
                float32 data points are values in the 100s-1000s instead of in
                the millions

        Returns: Metashape.Vector of the camera origin. For now Z is kept at 0
            and only (X, Y) are calculated from the cameras.
        """

        # The camera reference location is known to be in lat/lon
        camera_crs = Metashape.CoordinateSystem("EPSG::4326")

        # Average the camera locations without using libraries like numpy
        x = 0.0
        y = 0.0
        n_valid = 0
        for camera in self.doc.chunk.cameras:

            # Check for missing GPS EXIF data
            if camera.reference.location is None:
                continue

            # Get the camera location in the project CRS
            location = Metashape.CoordinateSystem.transform(
                camera.reference.location,
                source=camera_crs,
                target=Metashape.CoordinateSystem(self.cfg["project"]["project_crs"]),
            )
            x += location[0]
            y += location[1]
            n_valid += 1

        # Average over the number of valid images
        if n_valid > 0:
            x /= n_valid
            y /= n_valid

        # Round the values for easier readability
        x = int(x / round) * round
        y = int(y / round) * round

        return Metashape.Vector([x, y, 0])
