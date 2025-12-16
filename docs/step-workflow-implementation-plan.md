# Step-Based Workflow Refactoring for Argo Integration

## Executive Summary

Refactor automate-metashape to support running individual processing steps as separate container invocations, enabling integration with Argo Workflows for orchestrated, resource-efficient batch processing of multiple missions.

---

## Background & Motivation

**Current State:** automate-metashape runs as a monolithic workflow—all processing steps execute sequentially in a single container/process. Steps are enabled/disabled via YAML config flags.

**Target Use Case:** Integration into a larger Argo Workflows pipeline that:
- Reads a list of drone missions to process
- Runs pre-processing steps
- Processes multiple missions **in parallel**, each with its own Metashape project
- Runs post-processing steps
- Assigns **CPU or GPU nodes** to steps based on computational requirements

**Key Benefit:** GPU-intensive operations (matchPhotos, buildDepthMaps, buildModel) can run on expensive GPU nodes while CPU-only operations (alignCameras, buildPointCloud, buildDem, buildOrthomosaic, etc.) run on cheaper CPU nodes, optimizing resource costs across parallel mission processing. matchPhotos and buildModel should support optional GPU acceleration because depending on the context (dataset size and processing parameters), the benefits of GPU may outweigh the costs.

---

## Chosen Approach: Option C - WorkflowTemplate with Conditional Steps

**Architecture:**
- Define a fixed Argo WorkflowTemplate containing all possible Metashape processing steps
- Each step has a `when` condition based on parameters (e.g., `when: "{{inputs.parameters.align-enabled}} == 'true'"`)
- Steps with false conditions are **skipped without pod creation**—no resources allocated
- Outer workflow fans out over missions, calling the template with mission-specific enabled flags

**Why This Approach:**
- **Resource efficient**: Disabled GPU steps don't allocate GPU nodes (Argo evaluates conditions before scheduling)
- **Unified UI**: Single workflow view in Argo UI shows all missions and their step status
- **Simple integration**: Uses native Argo features, no custom workflow generation logic
- **Backward compatible**: Preserves ability to run full workflow in single command for local/manual use

---

## Phase 1: Enhanced Logging for Benchmarking

### Objective

Implement detailed per-API-call logging to benchmark processing times and resource utilization. This data will inform decisions about step granularity (which operations to lump together vs split).

### Deliverables

**Two log files per run:**

1. **Human-readable log** (`{run_id}_log.txt`):
   ```
   Project Setup           | 00:00:03 | CPU: 12% | GPU: 0%
   Add Photos              | 00:01:47 | CPU: 34% | GPU: 0%
   Match Photos            | 01:23:45 | CPU: 42% | GPU: 91%
   Align Cameras           | 00:08:12 | CPU: 38% | GPU: 85%
   Build Depth Maps        | 02:15:33 | CPU: 45% | GPU: 88%
   Build Point Cloud       | 00:45:22 | CPU: 51% | GPU: 76%
   Build DEM (DSM-ptcloud) | 00:12:15 | CPU: 65% | GPU: 42%
   Build Orthomosaic       | 00:18:33 | CPU: 58% | GPU: 38%
   ```

2. **Machine-readable log** (`{run_id}_metrics.yaml`):
   ```yaml
   - api_call: matchPhotos
     duration_seconds: 5025.3
     cpu_percent: 42.1
     gpu_percent: 91.3

   - api_call: alignCameras
     duration_seconds: 492.7
     cpu_percent: 38.4
     gpu_percent: 85.2

   - api_call: buildDepthMaps
     duration_seconds: 8133.1
     cpu_percent: 45.0
     gpu_percent: 88.4
   ```

### Implementation

1. **Monitoring infrastructure**
   - Add `psutil` dependency for CPU monitoring
   - Add `pynvml` dependency for GPU monitoring
   - Create decorator/context manager to wrap Metashape API calls
   - Background thread samples CPU/GPU utilization during call execution

2. **Wrap all Metashape API calls**
   - matchPhotos, alignCameras
   - buildDepthMaps
   - buildPointCloud, classifyGroundPoints
   - buildModel
   - buildDem (per DEM type)
   - buildOrthomosaic (per surface)
   - optimizeCameras
   - Other API calls as needed

3. **Output handling**
   - Human log: append formatted line after each call
   - YAML log: append structured entry after each call

### Estimated Effort

4-8 hours

### Success Criteria

- Every Metashape API call logs duration, CPU%, and GPU%
- Both log formats generated correctly
- Logs support append mode for multi-step workflow compatibility

---

## Phase 2: Step-Based Workflow Refactoring

### Step Definitions

Based on Phase 1 benchmarking results, only **matchPhotos, buildDepthMaps, and buildModel** actually utilize GPU. All other operations are CPU-only.

**Note on Operations column naming:**
- **snake_case names** (e.g., `add_photos`, `filter_points_usgs_part1`) refer to automate-metashape Python helper methods that the step calls
- **camelCase names** (e.g., `matchPhotos`, `alignCameras`, `buildDepthMaps`) refer to Metashape API calls made directly by the step method (no wrapper exists)

| Step | Operations | GPU Capable | Node Type Selection |
|------|------------|-------------|---------------------|
| `setup` | project_setup, enable_and_log_gpu, add_photos, calibrate_reflectance | No | CPU only |
| `match_photos` | matchPhotos | Yes | Config-driven: `match_photos.gpu_enabled` |
| `align_cameras` | alignCameras, reset_region, filter_points_usgs_part1, add_gcps, optimize_cameras, filter_points_usgs_part2, export_cameras | No | CPU only |
| `build_depth_maps` | buildDepthMaps | Yes | GPU only (always benefits) |
| `build_point_cloud` | buildPointCloud, classifyGroundPoints, export | No | CPU only |
| `build_mesh` | buildModel, export | Yes | Config-driven: `build_mesh.gpu_enabled` |
| `build_dem_orthomosaic` | classify_ground_points, build DEM/ortho operations | No | CPU only |
| `match_photos_secondary` | add_photos, matchPhotos | Yes | Config-driven: `match_photos.gpu_enabled` |
| `align_cameras_secondary` | alignCameras, export_cameras | No | CPU only |
| `finalize` | remove_point_cloud, export_report, finish_run | No | CPU only |

**Config-to-Step Mapping:**

This table shows the relationship between step methods, config sections, and Argo parameters:

| Step Method | Config Section(s) | Argo Parameter |
|-------------|-------------------|----------------|
| `setup()` | `setup:` | `setup_enabled` |
| `match_photos()` + `align_cameras()` | `align_photos:` | `align_photos_enabled` |
| `build_depth_maps()` | `build_depth_maps:` | `build_depth_maps_enabled` |
| `build_point_cloud()` | `build_point_cloud:` | `build_point_cloud_enabled` |
| `build_mesh()` | `build_mesh:` | `build_mesh_enabled` |
| `build_dem_orthomosaic()` | `build_dem:` + `build_orthomosaic:` | `build_dem_orthomosaic_enabled` |
| `match_photos_secondary()` + `align_cameras_secondary()` | `align_photos_secondary:` | `align_photos_secondary_enabled` |
| `finalize()` | `finalize:` | `finalize_enabled` |

**Notes:**
- **Flat config structure:** All operations are top-level config sections with their own `enabled` flag and parameters
- **GPU acceleration:** For GPU-capable operations (match_photos, build_mesh):
  - Config parameters: `align_photos.match_photos_gpu_enabled`, `align_photos_secondary.match_photos_gpu_enabled`, `build_mesh.gpu_enabled`
  - **In Argo**: Determine which node type (GPU vs CPU) to schedule the operation on. If omitted, defaults to `true` for backward compatibility.
  - **In local execution**: Have no effect; Metashape auto-detects available hardware
- **Config-to-step relationships:**
  - **align_photos section:** Single `enabled` flag controls BOTH `match_photos()` and `align_cameras()` steps. These steps are always run together (can't align cameras without matching first). Despite sharing a config section, they remain separate step methods for Argo GPU/CPU optimization.
  - **setup() step:** Checks multiple config sections (`add_photos`, `calibrate_reflectance`)
  - **align_cameras() step:** Checks multiple config sections (`add_gcps`, `filter_points_usgs`, `optimize_cameras`, `export_cameras`)
  - **build_dem_orthomosaic() step:** Reads from TWO separate config sections (`build_dem` and `build_orthomosaic`) because these are independent products. The step runs if either section has `enabled: true`.

### CLI Interface

```bash
# Current behavior preserved (runs all enabled steps)
python metashape_workflow.py config.yml

# New: run single step, load project from previous step
python metashape_workflow.py config.yml --step setup
python metashape_workflow.py config.yml --step match_photos
python metashape_workflow.py config.yml --step align_cameras
python metashape_workflow.py config.yml --step build_depth_maps
python metashape_workflow.py config.yml --step build_point_cloud
python metashape_workflow.py config.yml --step build_mesh
python metashape_workflow.py config.yml --step build_dem_orthomosaic
python metashape_workflow.py config.yml --step match_photos_secondary
python metashape_workflow.py config.yml --step align_cameras_secondary
python metashape_workflow.py config.yml --step finalize
```

**Note:** The step name doesn't specify GPU vs CPU. For GPU-capable steps, hardware selection is automatic:
- Local execution: Metashape auto-detects available GPU (the `gpu_enabled` config parameter has no effect)
- Argo execution: The optional `gpu_enabled` config parameter determines node scheduling. If omitted, defaults to `true` for backward compatibility.

### Implementation Details

#### 1. Refactor for Step Execution

- Add `--step` CLI argument to `metashape_workflow.py`
- Create step dispatcher in `MetashapeWorkflow` class
- Update `run()` method to call new step orchestration methods
- Each step: loads project (if needed) → executes operations → saves project

```python
def run(self):
    """Execute full metashape workflow by calling step methods."""
    self.setup()

    # align_photos encompasses both match and align steps
    if self.cfg["align_photos"]["enabled"]:
        self.match_photos()
        self.align_cameras()

    if self.cfg["build_depth_maps"]["enabled"]:
        self.build_depth_maps()

    if self.cfg["build_point_cloud"]["enabled"]:
        self.build_point_cloud()

    if self.cfg["build_mesh"]["enabled"]:
        self.build_mesh()

    # build_dem_orthomosaic has multiple independent operations, use helper
    if self.should_run_build_dem_orthomosaic():
        self.build_dem_orthomosaic()

    # align_photos_secondary encompasses both match and align steps
    if self.cfg["align_photos_secondary"]["enabled"]:
        self.match_photos_secondary()
        self.align_cameras_secondary()

    self.finalize()

def should_run_build_dem_orthomosaic(self):
    """Check if any DEM or orthomosaic operations are enabled.

    This step can build multiple independent products:
    - DEM(s): DSM from point cloud, DSM from mesh, DTM (config: build_dem section)
    - Orthomosaic(s): from DEM or mesh surface (config: build_orthomosaic section)

    Returns:
        bool: True if any DEM or orthomosaic operation is enabled
    """
    dem_enabled = self.cfg["build_dem"]["enabled"]
    ortho_enabled = self.cfg["build_orthomosaic"]["enabled"]
    return dem_enabled or ortho_enabled

def run_step(self, step_name):
    """Run a single step, loading project from previous step."""
    # For setup step, project is created fresh
    # For other steps, project is loaded in project_setup() if load_project is set
    self.validate_prerequisites(step_name)

    # Step names match method names directly
    method = getattr(self, step_name)
    method()
```

**Step Execution Logic:**

Most steps have a simple top-level `enabled` flag in their config section. However, some steps contain multiple independent operations and need OR logic:

| Step | Execution Check | Rationale |
|------|----------------|-----------|
| `setup` | Always runs | Required initialization |
| `match_photos` + `align_cameras` | `align_photos.enabled` | Logically coupled pair (can't align without matching); single enabled flag |
| `build_depth_maps` | `build_depth_maps.enabled` | Single operation |
| `build_point_cloud` | `build_point_cloud.enabled` | Single operation (classify is optional enhancement) |
| `build_mesh` | `build_mesh.enabled` | Single operation |
| `build_dem_orthomosaic` | `should_run_build_dem_orthomosaic()` helper | Multiple independent products (DEMs and/or orthomosaics) |
| `match_photos_secondary` + `align_cameras_secondary` | `align_photos_secondary.enabled` | Logically coupled pair; single enabled flag |
| `finalize` | Always runs | Required cleanup/reporting |

**Note on `build_dem_orthomosaic`:** This step differs from others because it can produce completely independent outputs. A user might want only a DEM, only an orthomosaic, or both. The helper method ensures the step runs if ANY of its products are requested.


#### 2. Create Step Methods

Each step in the workflow gets a method that coordinates its component operations. Step methods handle config checking; atomic helper methods just perform their operations.

**`setup()` step:**
- Calls `project_setup()`, `enable_and_log_gpu()`
- Calls `add_photos()` if configured
- Calls `calibrate_reflectance()` if configured
- Keeps: `project_setup()`, `enable_and_log_gpu()`, `add_photos()`, `calibrate_reflectance()` unchanged

**`match_photos()` step:**
- Extracts just the matchPhotos call from existing `align_photos()` method
- Logs "Match Photos" header
- Saves project

**`align_cameras()` step:**
- Extracts the alignCameras call from existing `align_photos()` method
- Calls `reset_region()`
- Calls `filter_points_usgs_part1()` if configured, then `reset_region()`
- Calls `add_gcps()` if configured, then `reset_region()`
- Calls `optimize_cameras()` if configured, then `reset_region()`
- Calls `filter_points_usgs_part2()` if configured, then `reset_region()`
- Calls `export_cameras()` if configured
- Keeps: all component methods unchanged (`filter_points_usgs_part1()`, `add_gcps()`, `optimize_cameras()`, etc.)

**`build_depth_maps()` step:**
- Keep existing `build_depth_maps()` method name
- Otherwise unchanged

**`build_point_cloud()` step:**
- Keep existing `build_point_cloud()` method name
- Otherwise unchanged (already handles classify_ground_points internally)

**`build_mesh()` step:**
- Keep existing `build_mesh()` method name
- Otherwise unchanged

**`build_dem_orthomosaic()` step:**
- Keep existing `build_dem_orthomosaic()` method name
- Remove point cloud removal logic (lines 1067-1068) from the method
- Reads from TWO config sections: `build_dem` and `build_orthomosaic`
- Builds DEM(s) if `build_dem.enabled` is true
- Builds orthomosaic(s) if `build_orthomosaic.enabled` is true
- Otherwise keeps all DEM/ortho building logic unchanged (including optional classifyGroundPoints if configured)

**`match_photos_secondary()` step:**
- Calls `add_photos(secondary=True, log_header=False)` to add secondary photos
- Calls matchPhotos API directly (extracted from the removed `align_photos()` method)
- Logs "Match Secondary Photos" header
- Saves project
- Note: Combines add + match into one step since add_photos is quick and doesn't need GPU

**`align_cameras_secondary()` step:**
- Calls alignCameras API directly (extracted from the removed `align_photos()` method)
- Calls `export_cameras()` if configured
- Logs "Align Secondary Cameras" header
- Saves project

**`finalize()` step:**
- Calls `remove_point_cloud()` if `build_point_cloud.remove_after_export` is true
- Calls `export_report()`
- Calls `finish_run()`

**New `remove_point_cloud()` helper method:**
- Removes point clouds from chunk (no config checking - step method handles this)
- Saves project
- Extracted from line 1067-1068 in current `build_dem_orthomosaic()`

**Remove `align_photos()` and `add_align_secondary_photos()` methods:**
- The old `align_photos()` method is removed (replaced by `match_photos()` and `align_cameras()` steps)
- The old `add_align_secondary_photos()` method is removed (replaced by `match_photos_secondary()` and `align_cameras_secondary()` steps)
- The `run()` method is updated to call the new step methods instead

**Note:** GPU vs CPU selection for matchPhotos and buildModel is handled by Metashape's auto-detection based on available hardware during local execution. In Argo workflows, the optional config parameters `match_photos.gpu_enabled` and `build_mesh.gpu_enabled` determine which node type to schedule on. If omitted, these parameters default to `true` for backward compatibility.

**Example Step Method Implementations:**

Below are concrete code examples showing how step methods perform config checks for optional operations:

```python
def setup(self):
    """Setup step: Initialize project and add photos."""
    self.project_setup()
    self.enable_and_log_gpu()

    # Optional operation: add photos (check config)
    if self.cfg["add_photos"]["enabled"]:
        self.add_photos()

    # Optional operation: calibrate reflectance (check config)
    if self.cfg["calibrate_reflectance"]["enabled"]:
        self.calibrate_reflectance()

    self.doc.save()

def match_photos(self):
    """Match photos step: Generate tie points."""
    self.log("Match Photos", "header")

    # Direct Metashape API call (no config check here - run() method already checked align_photos.enabled)
    self.doc.chunk.matchPhotos(
        downscale=self.cfg["align_photos"]["downscale"],
        generic_preselection=self.cfg["align_photos"]["generic_preselection"],
        reference_preselection=self.cfg["align_photos"]["reference_preselection"]
    )

    self.doc.save()

def align_cameras(self):
    """Align cameras step: Perform alignment and post-alignment operations."""
    self.log("Align Cameras", "header")

    # Direct Metashape API call (no config check - already checked in run())
    self.doc.chunk.alignCameras()
    self.reset_region()

    # Optional operation: filter sparse points (part 1)
    if self.cfg["filter_points_usgs"]["enabled"]:
        self.filter_points_usgs_part1()
        self.reset_region()

    # Optional operation: add GCPs
    if self.cfg["add_gcps"]["enabled"]:
        self.add_gcps()
        self.reset_region()

    # Optional operation: optimize cameras
    if self.cfg["optimize_cameras"]["enabled"]:
        self.optimize_cameras()
        self.reset_region()

    # Optional operation: filter sparse points (part 2)
    if self.cfg["filter_points_usgs"]["enabled"]:
        self.filter_points_usgs_part2()
        self.reset_region()

    # Optional operation: export cameras
    if self.cfg["export_cameras"]["enabled"]:
        self.export_cameras()

    self.doc.save()

def finalize(self):
    """Finalize step: Clean up and generate reports."""
    self.log("Finalize", "header")

    # Optional operation: remove point cloud after export
    if self.cfg["build_point_cloud"]["enabled"] and self.cfg["build_point_cloud"]["remove_after_export"]:
        self.remove_point_cloud()

    # Always run these operations
    self.export_report()
    self.finish_run()

    self.doc.save()
```

**Key patterns:**
- **Step-level checks** happen in `run()` method (e.g., `if self.cfg["align_photos"]["enabled"]:` runs both match_photos() and align_cameras())
- **Operation-level checks** happen inside step methods (e.g., `if self.cfg["add_gcps"]["enabled"]: self.add_gcps()`)
- Each operation has its own top-level config section with `enabled` flag and operation-specific parameters
- Helper methods like `add_gcps()`, `filter_points_usgs_part1()`, etc. contain NO config checks—they just perform their operation
- Step methods coordinate operations and handle all config logic

#### 3. Unified Logging Across Steps

- All steps append to the same log files in the output directory
- Files opened in append mode
- Sequential execution ensures no conflicts (for local execution; for Argo execution, see Phase 3)

```python
# Each step appends to unified logs
with open(self.log_file, "a") as f:
    f.write(f"{operation_name} | {duration} | CPU: {cpu}% | GPU: {gpu}%\n")
```

#### 4. Prerequisite Validation

Each step validates required prior state. Steps without prerequisites (`setup`, `match_photos`, `match_photos_secondary`, `finalize`) are not listed.

**Important:** Error messages must include context about what's missing and what prerequisite step needs to be run first.

```python
def validate_prerequisites(self, step_name):
    """Validate that prerequisites for a step are met.

    Raises:
        ValueError: If prerequisites not met, with message indicating what's missing
                   and which step(s) need to run first.
    """
    prereqs = {
        'align_cameras': {
            'check': lambda: self.doc.chunk.tie_points is not None,
            'error': "Tie points not found. Run 'match_photos' step first."
        },
        'build_depth_maps': {
            'check': lambda: len([c for c in self.doc.chunk.cameras if c.transform]) > 0,
            'error': "No aligned cameras found. Run 'align_cameras' step first."
        },
        'build_point_cloud': {
            'check': lambda: self.doc.chunk.depth_maps is not None,
            'error': "Depth maps not found. Run 'build_depth_maps' step first."
        },
        'build_mesh': {
            'check': lambda: self.doc.chunk.depth_maps is not None,
            'error': "Depth maps not found. Run 'build_depth_maps' step first."
        },
        'build_dem_orthomosaic': {
            'check': lambda: self.doc.chunk.point_cloud is not None or self.doc.chunk.model is not None,
            'error': "Neither point cloud nor mesh model found. Run 'build_point_cloud' or 'build_mesh' step first."
        },
        'align_cameras_secondary': {
            'check': lambda: self.doc.chunk.tie_points is not None,
            'error': "Tie points not found for secondary cameras. Run 'match_photos_secondary' step first."
        },
    }

    if step_name in prereqs:
        if not prereqs[step_name]['check']():
            raise ValueError(f"Prerequisites not met for step '{step_name}': {prereqs[step_name]['error']}")
```

**Note on `chunk.tie_points` vs `chunk.point_cloud`:**
- `chunk.tie_points`: Sparse point cloud created by `matchPhotos()` operation
- `chunk.point_cloud`: Dense point cloud created by `buildPointCloud()` operation
- After `match_photos` step, tie points exist but dense point cloud does not yet exist

### Commit Structure

Phase 2 should be implemented as a **single PR** with the following logical commits:

1. **Add --step CLI infrastructure and dispatcher**
   - Add `--step` argument to CLI parser
   - Implement `run_step()` method in `MetashapeWorkflow` class that dispatches to step methods
   - Add step name validation (valid steps: setup, match_photos, align_cameras, build_depth_maps, build_point_cloud, build_mesh, build_dem_orthomosaic, match_photos_secondary, align_cameras_secondary, finalize)

2. **Create setup step method**
   - Add `setup()` method that calls `project_setup()`, `enable_and_log_gpu()`, `add_photos()`, `calibrate_reflectance()`
   - All component methods remain unchanged

3. **Split align_photos into match_photos and align_cameras steps**
   - Create `match_photos()` method (extracts matchPhotos call from `align_photos()`)
   - Create `align_cameras()` method (extracts alignCameras call plus all post-alignment operations)
   - Remove old `align_photos()` method
   - Update `run()` method to call `match_photos()` and `align_cameras()` instead of `align_photos()`

4. **Keep existing build_* step method names**
   - Keep `build_depth_maps()`, `build_point_cloud()`, `build_mesh()`, `build_dem_orthomosaic()` method names unchanged
   - Update `run()` method to reference these methods with new config structure

5. **Extract point cloud removal from build_dem_orthomosaic**
   - Remove point cloud removal logic (lines 1067-1068) from `build_dem_orthomosaic()`
   - Create `remove_point_cloud()` helper method (just removes, no config checking)

6. **Add helper method for build_dem_orthomosaic step execution logic**
   - Implement `should_run_build_dem_orthomosaic()` helper method
   - Method checks if `build_dem.enabled` OR `build_orthomosaic.enabled` is true
   - Update `run()` method to call helper instead of checking single enabled flag
   - This allows the step to run if either product is requested

7. **Create secondary photos step methods**
   - Create `match_photos_secondary()` method (calls add_photos, matchPhotos API)
   - Create `align_cameras_secondary()` method (calls alignCameras API, export_cameras)
   - Remove old `add_align_secondary_photos()` method
   - Update `run()` method to call new secondary photo step methods

8. **Create finalize step method**
   - Create `finalize()` method (calls remove_point_cloud if configured, export_report, finish_run)
   - Update `run()` method to call `finalize()` instead of individual finalization steps

9. **Migrate config structure to flat, operation-based naming**
   - Flatten config: all operations become top-level sections with `enabled` flag
   - Create top-level sections: `add_photos`, `calibrate_reflectance`, `align_photos`, `add_gcps`, `filter_points_usgs`, `optimize_cameras`, `export_cameras`
   - Rename `buildDepthMaps` → `build_depth_maps`, `buildPointCloud` → `build_point_cloud`, `buildMesh` → `build_mesh`
   - Split `buildDem` and `buildOrthomosaic` into separate `build_dem` and `build_orthomosaic` sections
   - Create `align_photos_secondary` section for secondary photo operations
   - Add `match_photos_gpu_enabled` parameter to `align_photos` and `align_photos_secondary` sections
   - Update all config references throughout the codebase to use new section names
   - Add backward compatibility note in documentation for existing configs

10. **Add prerequisite validation**
   - Implement `validate_prerequisites()` method with contextual error messages
   - Add prerequisite checks for steps that require prior state (align_cameras, build_depth_maps, build_point_cloud, build_mesh, build_dem_orthomosaic, align_cameras_secondary)
   - Error messages must explain what's missing and which step needs to run first

11. **Update tests and documentation**
   - Add tests for step-based execution
   - Test prerequisite validation
   - Test full workflow mode with new step methods
   - Update README with `--step` usage examples
   - Add docstrings for new step methods

### Estimated Effort

- Refactor workflow into step dispatcher: 4-6 hours
- Break apart coupled methods: 2-3 hours
- Add prerequisite validation: 2-3 hours
- Testing and documentation: 4-6 hours

**Total: 12-18 hours**

---

## Phase 3: Argo Workflow Integration

### Config-to-Step Translation

The Phase 2 config restructuring aligns config sections with step names for clarity and consistency. Each step's `enabled` flag determines whether the entire step runs.

**Config Structure (after Phase 2 migration):**

```yaml
add_photos:  # Part of setup() step
  enabled: true
  # Photo paths and import parameters

calibrate_reflectance:  # Part of setup() step
  enabled: true
  use_reflectance_panels: true
  # Other calibration parameters

align_photos:  # Part of match_photos() and align_cameras() steps
  enabled: true
  match_photos_gpu_enabled: true  # Optional. For Argo: if true, run match_photos on GPU node; if false, on CPU node. If omitted, defaults to true.
  # Match photos parameters
  downscale: 1
  generic_preselection: true
  reference_preselection: true

add_gcps:  # Part of align_cameras() step
  enabled: false
  path: "/path/to/gcps.txt"
  # Other GCP parameters

filter_points_usgs:  # Part of align_cameras() step
  enabled: false
  # Filter parameters

optimize_cameras:  # Part of align_cameras() step
  enabled: true
  # Optimization parameters

export_cameras:  # Part of align_cameras() step
  enabled: true
  path: "/path/to/export"
  # Export parameters

build_depth_maps:
  enabled: true
  # Depth map parameters

build_point_cloud:
  enabled: true
  # Point cloud parameters

build_mesh:
  enabled: true
  gpu_enabled: false  # Optional. For Argo: if true, run on GPU node; if false, run on CPU node. If omitted, defaults to true.
  surface_type: Arbitrary
  source_data: DepthMapsData

build_dem:
  enabled: true
  # DEM-specific parameters (types, resolution, etc.)

build_orthomosaic:
  enabled: true
  # Orthomosaic-specific parameters (surface, blending, etc.)
```

**Notes on config structure:**
- **Flat structure:** All operations are top-level config sections with their own `enabled` flag and parameters
- **Multi-step sections:** Some config sections are checked by multiple step methods:
  - `align_photos`: Checked by `match_photos()` and `align_cameras()` steps (single `enabled` flag controls both)
    - `match_photos_gpu_enabled` parameter controls GPU usage for match_photos only
  - `align_photos_secondary`: Same pattern for secondary photo steps
    - `match_photos_gpu_enabled` parameter controls GPU usage for match_photos_secondary only
- **Multi-section steps:** Some step methods check multiple config sections:
  - `setup()`: Checks `add_photos.enabled` and `calibrate_reflectance.enabled`
  - `align_cameras()`: Checks `add_gcps.enabled`, `filter_points_usgs.enabled`, `optimize_cameras.enabled`, `export_cameras.enabled`
  - `build_dem_orthomosaic()`: Checks `build_dem.enabled` and `build_orthomosaic.enabled` (step runs if either is true)
- **GPU parameters:** For GPU-capable operations (match_photos, build_mesh):
  - **In Argo**: Determine which node type (GPU vs CPU) to schedule the operation on. If omitted, defaults to `true` for backward compatibility.
  - **In local execution**: Have no effect; Metashape auto-detects available hardware

**Translation Logic (Config → Argo Parameters):**

| Argo Step Parameter | Config Enabled Check | GPU Parameter Mapping | Node Type |
|---------------------|---------------------|----------------------|-----------|
| `setup_enabled` | Always `true` | N/A | CPU |
| `align_photos_enabled` | `align_photos.enabled == true` | `match_photos_use_gpu` ← `align_photos.match_photos_gpu_enabled` | match_photos: GPU/CPU<br>align_cameras: CPU |
| `build_depth_maps_enabled` | `build_depth_maps.enabled == true` | N/A (always GPU) | GPU |
| `build_point_cloud_enabled` | `build_point_cloud.enabled == true` | N/A | CPU |
| `build_mesh_enabled` | `build_mesh.enabled == true` | `build_mesh_use_gpu` ← `build_mesh.gpu_enabled` | GPU/CPU |
| `build_dem_orthomosaic_enabled` | `build_dem.enabled == true` OR `build_orthomosaic.enabled == true` | N/A | CPU |
| `align_photos_secondary_enabled` | `align_photos_secondary.enabled == true` | `match_photos_secondary_use_gpu` ← `align_photos_secondary.match_photos_gpu_enabled` | match_photos_secondary: GPU/CPU<br>align_cameras_secondary: CPU |
| `finalize_enabled` | Always `true` | N/A | CPU |

**Preprocess Step:**

A lightweight Python script runs once per workflow to:
1. Read all mission config YAML files
2. Apply translation logic above for each mission
3. Read `gpu_enabled` parameters to determine node type for GPU-capable steps (defaulting to `true` if omitted)
4. Output a JSON array of missions with step-level enabled flags and node types

Example output structure:
```json
[
  {
    "config": "/data/mission1/config.yml",
    "setup_enabled": "true",
    "align_photos_enabled": "true",
    "match_photos_use_gpu": "true",
    "build_depth_maps_enabled": "true",
    "build_point_cloud_enabled": "true",
    "build_mesh_enabled": "false",
    "build_dem_orthomosaic_enabled": "true",
    "align_photos_secondary_enabled": "false",
    "match_photos_secondary_use_gpu": "false",
    "finalize_enabled": "true"
  },
  {
    "config": "/data/mission2/config.yml",
    "setup_enabled": "true",
    "align_photos_enabled": "true",
    "match_photos_use_gpu": "false",
    "build_depth_maps_enabled": "false",
    "build_point_cloud_enabled": "false",
    "build_mesh_enabled": "true",
    "build_mesh_use_gpu": "false",
    "build_dem_orthomosaic_enabled": "true",
    "align_photos_secondary_enabled": "false",
    "match_photos_secondary_use_gpu": "false",
    "finalize_enabled": "true"
  }
]
```

This ensures disabled steps are skipped by Argo before pod scheduling, and GPU-capable steps are scheduled on the appropriate node type.

### WorkflowTemplate Structure

```yaml
apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata:
  name: metashape-processing
spec:
  arguments:
    parameters:
      - name: project-path
      - name: config-path
      - name: setup_enabled
      - name: align_photos_enabled
      - name: match_photos_use_gpu
      - name: build_depth_maps_enabled
      - name: build_point_cloud_enabled
      - name: build_mesh_enabled
      - name: build_mesh_use_gpu
      - name: build_dem_orthomosaic_enabled
      - name: align_photos_secondary_enabled
      - name: match_photos_secondary_use_gpu
      - name: finalize_enabled
  templates:
    - name: main
      dag:
        tasks:
          - name: setup
            when: "{{workflow.parameters.setup_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "setup"

          # match_photos: separate tasks for GPU vs CPU, mutually exclusive via when conditions
          - name: match-photos-gpu
            depends: "setup"
            when: "{{workflow.parameters.align_photos_enabled}} == 'true' && {{workflow.parameters.match_photos_use_gpu}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_photos"

          - name: match-photos-cpu
            depends: "setup"
            when: "{{workflow.parameters.align_photos_enabled}} == 'true' && {{workflow.parameters.match_photos_use_gpu}} == 'false'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_photos"

          - name: align-cameras
            depends: "match-photos-gpu || match-photos-cpu"
            when: "{{workflow.parameters.align_photos_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "align_cameras"

          - name: build-depth-maps
            depends: "align-cameras.Succeeded || align-cameras.Skipped"
            when: "{{workflow.parameters.build_depth_maps_enabled}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "build_depth_maps"

          - name: build-point-cloud
            depends: "build-depth-maps"
            when: "{{workflow.parameters.build_point_cloud_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "build_point_cloud"

          # build_mesh: separate tasks for GPU vs CPU, mutually exclusive via when conditions
          - name: build-mesh-gpu
            depends: "build-point-cloud.Succeeded || build-point-cloud.Skipped"
            when: "{{workflow.parameters.build_mesh_enabled}} == 'true' && {{workflow.parameters.build_mesh_use_gpu}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "build_mesh"

          - name: build-mesh-cpu
            depends: "build-point-cloud.Succeeded || build-point-cloud.Skipped"
            when: "{{workflow.parameters.build_mesh_enabled}} == 'true' && {{workflow.parameters.build_mesh_use_gpu}} == 'false'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "build_mesh"

          - name: build-dem-orthomosaic
            depends: "(build-point-cloud.Succeeded || build-point-cloud.Skipped) && (build-mesh-gpu.Succeeded || build-mesh-gpu.Skipped || build-mesh-cpu.Succeeded || build-mesh-cpu.Skipped)"
            when: "{{workflow.parameters.build_dem_orthomosaic_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "build_dem_orthomosaic"

          # match_photos_secondary: separate tasks for GPU vs CPU, mutually exclusive via when conditions
          - name: match-photos-secondary-gpu
            depends: "build-dem-orthomosaic.Succeeded || build-dem-orthomosaic.Skipped"
            when: "{{workflow.parameters.align_photos_secondary_enabled}} == 'true' && {{workflow.parameters.match_photos_secondary_use_gpu}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_photos_secondary"

          - name: match-photos-secondary-cpu
            depends: "build-dem-orthomosaic.Succeeded || build-dem-orthomosaic.Skipped"
            when: "{{workflow.parameters.align_photos_secondary_enabled}} == 'true' && {{workflow.parameters.match_photos_secondary_use_gpu}} == 'false'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_photos_secondary"

          - name: align-cameras-secondary
            depends: "match-photos-secondary-gpu || match-photos-secondary-cpu"
            when: "{{workflow.parameters.align_photos_secondary_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "align_cameras_secondary"

          - name: finalize
            depends: "(build-dem-orthomosaic.Succeeded || build-dem-orthomosaic.Skipped) && (align-cameras-secondary.Succeeded || align-cameras-secondary.Skipped)"
            when: "{{workflow.parameters.finalize_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "finalize"

    - name: cpu-step
      inputs:
        parameters:
          - name: step
      nodeSelector:
        node-type: cpu
      container:
        image: metashape:latest
        command: ["python", "metashape_workflow.py"]
        args: ["{{workflow.parameters.config-path}}", "--step", "{{inputs.parameters.step}}"]
        volumeMounts:
          - name: shared-storage
            mountPath: /data
        env:
          - name: AGISOFT_FLS
            value: "license-server:27000"

    - name: gpu-step
      inputs:
        parameters:
          - name: step
      nodeSelector:
        nvidia.com/gpu: "true"
      container:
        image: metashape:latest
        resources:
          limits:
            nvidia.com/gpu: 1
        command: ["python", "metashape_workflow.py"]
        args: ["{{workflow.parameters.config-path}}", "--step", "{{inputs.parameters.step}}"]
        volumeMounts:
          - name: shared-storage
            mountPath: /data
        env:
          - name: AGISOFT_FLS
            value: "license-server:27000"
```

**Key Design Points:**

1. **Clean CLI Interface**: Users run `--step match_photos` or `--step build_mesh` (no GPU suffix)
2. **Config-Driven GPU Selection**: The `match_photos.gpu_enabled` and `build_mesh.gpu_enabled` config parameters control node scheduling
3. **Argo Task Names are Internal**: The `-gpu` and `-cpu` suffixes appear only in Argo task names (internal orchestration), not in the user-facing CLI or step values
4. **Mutually Exclusive Execution**: `when` conditions ensure only one variant (GPU or CPU) runs based on the `use_gpu` parameter
5. **Standard Argo Patterns**: Uses proven conditional execution rather than experimental template selection syntax
6. **Python Conventions**: Step names use underscores (match_photos, build_mesh) matching Python method naming, simplifying the dispatcher implementation
7. **Sequential Execution Guarantee**: The `depends` fields enforce strict sequential execution across all 10 steps. Steps never run in parallel because they share the same Metashape project file (.psx) and log files. The DAG dependencies ensure each step completes (or is skipped) before the next begins, preventing file conflicts. This includes the secondary photo steps, which execute sequentially after build_dem_orthomosaic and before finalize.

### Outer Workflow Integration

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
spec:
  templates:
    - name: main
      steps:
        - - name: preprocess
            template: preprocess-step

        - - name: process-missions
            template: metashape-processing
            arguments:
              parameters:
                - name: config-path
                  value: "{{item.config}}"
                - name: setup_enabled
                  value: "{{item.setup_enabled}}"
                - name: align_photos_enabled
                  value: "{{item.align_photos_enabled}}"
                - name: match_photos_use_gpu
                  value: "{{item.match_photos_use_gpu}}"
                - name: build_depth_maps_enabled
                  value: "{{item.build_depth_maps_enabled}}"
                - name: build_point_cloud_enabled
                  value: "{{item.build_point_cloud_enabled}}"
                - name: build_mesh_enabled
                  value: "{{item.build_mesh_enabled}}"
                - name: build_mesh_use_gpu
                  value: "{{item.build_mesh_use_gpu}}"
                - name: build_dem_orthomosaic_enabled
                  value: "{{item.build_dem_orthomosaic_enabled}}"
                - name: align_photos_secondary_enabled
                  value: "{{item.align_photos_secondary_enabled}}"
                - name: match_photos_secondary_use_gpu
                  value: "{{item.match_photos_secondary_use_gpu}}"
                - name: finalize_enabled
                  value: "{{item.finalize_enabled}}"
            withParam: "{{steps.preprocess.outputs.parameters.missions}}"

        - - name: postprocess
            template: postprocess-step
```

### Estimated Effort

- Create WorkflowTemplate YAML: 4-6 hours
- Integration testing: 4-6 hours
- Documentation: 2-3 hours

**Total: 10-15 hours**

---

## Key Technical Considerations

### Large Project Files

Metashape `.psx` projects can be tens of GB. Use shared persistent storage (NFS/PVC) mounted to all pods—not Argo artifacts.

### Metashape Licensing

Floating license server must be accessible from all pods. Ensure `AGISOFT_FLS` environment variable is configured in all step containers.

### Dependencies

Add to Docker image:
- `psutil` (CPU monitoring)
- `pynvml` (GPU monitoring)

---

## Success Criteria

### Phase 1
- Every Metashape API call logs duration, CPU%, and GPU%
- Both human-readable and YAML log formats generated
- Benchmarking data available for step granularity decisions

### Phase 2
- Individual steps can be invoked via CLI
- Steps produce valid project files that can be resumed
- Full-workflow mode continues to work for local/manual use
- Unified logs maintained across multi-step runs

### Phase 3
- Argo workflow correctly skips disabled steps without resource allocation
- GPU steps run on GPU nodes, CPU steps on CPU nodes
- Multiple missions process in parallel successfully
- Complete visibility in Argo UI

---

## Timeline Summary

| Phase | Deliverable | Effort |
|-------|-------------|--------|
| Phase 1 | Enhanced logging for benchmarking | 4-8 hours |
| Phase 2 | Step-based workflow refactoring | 12-18 hours |
| Phase 3 | Argo workflow integration | 10-15 hours |
| **Total** | | **26-41 hours** |
