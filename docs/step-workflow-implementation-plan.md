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
| `match_photos` | matchPhotos | Yes | Config-driven: `matchPhotos.gpu_enabled` |
| `align_cameras` | alignCameras, reset_region, filter_points_usgs_part1, add_gcps, optimize_cameras, filter_points_usgs_part2, export_cameras | No | CPU only |
| `depth_maps` | buildDepthMaps | Yes | GPU only (always benefits) |
| `point_cloud` | buildPointCloud, classifyGroundPoints (optional), export | No | CPU only |
| `mesh` | buildModel, export | Yes | Config-driven: `buildMesh.gpu_enabled` |
| `dem_orthomosaic` | classify_ground_points (optional), build DEM/ortho operations | No | CPU only |
| `match_secondary_photos` | add_photos, matchPhotos | Yes | Config-driven: `matchPhotos.gpu_enabled` |
| `align_secondary_cameras` | alignCameras, export_cameras | No | CPU only |
| `finalize` | remove_point_cloud, export_report, finish_run | No | CPU only |

**Note:** For steps with optional GPU acceleration (match_photos, mesh), the config parameter determines:
- **In Argo**: Which node type (GPU vs CPU) to schedule the step on. If the `gpu_enabled` parameter is omitted, it defaults to `true` for backward compatibility.
- **In local execution**: The parameter has no effect; Metashape auto-detects available hardware

### CLI Interface

```bash
# Current behavior preserved (runs all enabled steps)
python metashape_workflow.py config.yml

# New: run single step, load project from previous step
python metashape_workflow.py config.yml --step setup
python metashape_workflow.py config.yml --step match_photos
python metashape_workflow.py config.yml --step align_cameras
python metashape_workflow.py config.yml --step depth_maps
python metashape_workflow.py config.yml --step point_cloud
python metashape_workflow.py config.yml --step mesh
python metashape_workflow.py config.yml --step dem_orthomosaic
python metashape_workflow.py config.yml --step match_secondary_photos
python metashape_workflow.py config.yml --step align_secondary_cameras
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

    if self.cfg["alignPhotos"]["enabled"]:
        self.match_photos()
        self.align_cameras()

    if self.cfg["buildDepthMaps"]["enabled"]:
        self.depth_maps()

    if self.cfg["buildPointCloud"]["enabled"]:
        self.point_cloud()

    if self.cfg["buildMesh"]["enabled"]:
        self.mesh()

    self.dem_orthomosaic()

    if self.cfg["photo_path_secondary"] != "":
        self.match_secondary_photos()
        self.align_secondary_cameras()

    self.finalize()

def run_step(self, step_name):
    """Run a single step, loading project from previous step."""
    # For setup step, project is created fresh
    # For other steps, project is loaded in project_setup() if load_project is set
    self.validate_prerequisites(step_name)

    # Step names match method names directly
    method = getattr(self, step_name)
    method()
```

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

**`depth_maps()` step:**
- Rename existing `build_depth_maps()` to `depth_maps()`
- Otherwise unchanged

**`point_cloud()` step:**
- Rename existing `build_point_cloud()` to `point_cloud()`
- Otherwise unchanged (already handles classify_ground_points internally)

**`mesh()` step:**
- Rename existing `build_mesh()` to `mesh()`
- Otherwise unchanged

**`dem_orthomosaic()` step:**
- Rename existing `build_dem_orthomosaic()` to `dem_orthomosaic()`
- Remove point cloud removal logic (lines 1067-1068) from the method
- Otherwise keeps all DEM/ortho building logic unchanged (including optional classifyGroundPoints if configured)

**`match_secondary_photos()` step:**
- Calls `add_photos(secondary=True, log_header=False)` to add secondary photos
- Calls matchPhotos API directly (extracted from the removed `align_photos()` method)
- Logs "Match Secondary Photos" header
- Saves project
- Note: Combines add + match into one step since add_photos is quick and doesn't need GPU

**`align_secondary_cameras()` step:**
- Calls alignCameras API directly (extracted from the removed `align_photos()` method)
- Calls `export_cameras()` if configured
- Logs "Align Secondary Cameras" header
- Saves project

**`finalize()` step:**
- Calls `remove_point_cloud()` if `buildPointCloud.remove_after_export` is true
- Calls `export_report()`
- Calls `finish_run()`

**New `remove_point_cloud()` helper method:**
- Removes point clouds from chunk (no config checking - step method handles this)
- Saves project
- Extracted from line 1067-1068 in current `build_dem_orthomosaic()`

**Remove `align_photos()` and `add_align_secondary_photos()` methods:**
- The old `align_photos()` method is removed (replaced by `match_photos()` and `align_cameras()` steps)
- The old `add_align_secondary_photos()` method is removed (replaced by `match_secondary_photos()` and `align_secondary_cameras()` steps)
- The `run()` method is updated to call the new step methods instead

**Note:** GPU vs CPU selection for matchPhotos and buildModel is handled by Metashape's auto-detection based on available hardware during local execution. In Argo workflows, the optional config parameters `matchPhotos.gpu_enabled` and `buildMesh.gpu_enabled` determine which node type to schedule on. If omitted, these parameters default to `true` for backward compatibility.

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

Each step validates required prior state. Steps without prerequisites (`setup`, `match_photos`, `match_secondary_photos`, `finalize`) are not listed.

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
        'depth_maps': {
            'check': lambda: len([c for c in self.doc.chunk.cameras if c.transform]) > 0,
            'error': "No aligned cameras found. Run 'align_cameras' step first."
        },
        'point_cloud': {
            'check': lambda: self.doc.chunk.depth_maps is not None,
            'error': "Depth maps not found. Run 'depth_maps' step first."
        },
        'mesh': {
            'check': lambda: self.doc.chunk.depth_maps is not None,
            'error': "Depth maps not found. Run 'depth_maps' step first."
        },
        'dem_orthomosaic': {
            'check': lambda: self.doc.chunk.point_cloud is not None or self.doc.chunk.model is not None,
            'error': "Neither point cloud nor mesh model found. Run 'point_cloud' or 'mesh' step first."
        },
        'align_secondary_cameras': {
            'check': lambda: self.doc.chunk.tie_points is not None,
            'error': "Tie points not found for secondary cameras. Run 'match_secondary_photos' step first."
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
   - Add step name validation (valid steps: setup, match_photos, align_cameras, depth_maps, point_cloud, mesh, dem_orthomosaic, match_secondary_photos, align_secondary_cameras, finalize)

2. **Create setup step method**
   - Add `setup()` method that calls `project_setup()`, `enable_and_log_gpu()`, `add_photos()`, `calibrate_reflectance()`
   - All component methods remain unchanged

3. **Split align_photos into match_photos and align_cameras steps**
   - Create `match_photos()` method (extracts matchPhotos call from `align_photos()`)
   - Create `align_cameras()` method (extracts alignCameras call plus all post-alignment operations)
   - Remove old `align_photos()` method
   - Update `run()` method to call `match_photos()` and `align_cameras()` instead of `align_photos()`

4. **Rename simple step methods**
   - Rename `build_depth_maps()` to `depth_maps()`
   - Rename `build_point_cloud()` to `point_cloud()`
   - Rename `build_mesh()` to `mesh()`
   - Update `run()` method to call renamed methods

5. **Rename build_dem_orthomosaic to dem_orthomosaic and extract point cloud removal**
   - Rename `build_dem_orthomosaic()` to `dem_orthomosaic()`
   - Remove point cloud removal logic (lines 1067-1068) from `dem_orthomosaic()`
   - Create `remove_point_cloud()` helper method (just removes, no config checking)
   - Update `run()` method to call `dem_orthomosaic()` instead of `build_dem_orthomosaic()`

6. **Create secondary photos step methods**
   - Create `match_secondary_photos()` method (calls add_photos, matchPhotos API)
   - Create `align_secondary_cameras()` method (calls alignCameras API, export_cameras)
   - Remove old `add_align_secondary_photos()` method
   - Update `run()` method to call new secondary photo step methods

7. **Create finalize step method**
   - Create `finalize()` method (calls remove_point_cloud if configured, export_report, finish_run)
   - Update `run()` method to call `finalize()` instead of individual finalization steps

8. **Add prerequisite validation**
   - Implement `validate_prerequisites()` method with contextual error messages
   - Add prerequisite checks for steps that require prior state (align_cameras, depth_maps, point_cloud, mesh, dem_orthomosaic, align_secondary_cameras)
   - Error messages must explain what's missing and which step needs to run first

9. **Update tests and documentation**
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

The existing config YAML uses per-operation `enabled` flags (e.g., `alignPhotos.enabled`, `buildDem.enabled`). For Argo to skip disabled steps before pod creation, these must be translated to step-level enabled flags.

**Important:** A step being enabled does NOT mean all its component operations run—each operation checks its own config flag. For example, `align_cameras` could be enabled to add GCPs (`addGCPs.enabled: true`) even if alignment itself is disabled (`alignPhotos.enabled: false`), though this would be unusual.

**Config Parameters for GPU Selection:**

For GPU-capable operations, add optional config parameters:
```yaml
alignPhotos:
  enabled: true
  gpu_enabled: true  # Optional. For Argo: if true, run on GPU node; if false, run on CPU node. If omitted, defaults to true.

buildMesh:
  enabled: true
  gpu_enabled: false  # Optional. For Argo: if true, run on GPU node; if false, run on CPU node. If omitted, defaults to true.
```

These parameters are **optional** and serve different purposes depending on the execution environment:
- **In Argo**: Determine which node type (GPU vs CPU) to schedule the step on. If omitted, defaults to `true` for backward compatibility.
- **In local execution**: Have no effect; Metashape auto-detects available hardware

**Translation Logic:**

| Step Parameter | Enabled when... | Node Type |
|----------------|-----------------|-----------|
| `setup_enabled` | Always `true` | CPU |
| `match_photos_enabled` | `alignPhotos.enabled == true` | Determined by `alignPhotos.gpu_enabled` |
| `align_cameras_enabled` | `alignPhotos.enabled == true` OR `addGCPs.enabled == true` OR `filterPointsUSGS.enabled == true` OR `optimizeCameras.enabled == true` | CPU |
| `depth_maps_enabled` | `buildDepthMaps.enabled == true` | GPU |
| `point_cloud_enabled` | `buildPointCloud.enabled == true` | CPU |
| `mesh_enabled` | `buildMesh.enabled == true` | Determined by `buildMesh.gpu_enabled` |
| `dem_orthomosaic_enabled` | `buildDem.enabled == true` OR `buildOrthomosaic.enabled == true` | CPU |
| `match_secondary_photos_enabled` | `photo_path_secondary != ""` | Determined by `alignPhotos.gpu_enabled` |
| `align_secondary_cameras_enabled` | `photo_path_secondary != ""` | CPU |
| `finalize_enabled` | Always `true` | CPU |

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
    "match_photos_enabled": "true",
    "match_photos_use_gpu": "true",
    "align_cameras_enabled": "true",
    "depth_maps_enabled": "true",
    "point_cloud_enabled": "true",
    "mesh_enabled": "false",
    "dem_ortho_finalize_enabled": "true"
  },
  {
    "config": "/data/mission2/config.yml",
    "setup_enabled": "true",
    "match_photos_enabled": "true",
    "match_photos_use_gpu": "false",
    "align_cameras_enabled": "true",
    "depth_maps_enabled": "false",
    "point_cloud_enabled": "false",
    "mesh_enabled": "true",
    "mesh_use_gpu": "false",
    "dem_ortho_finalize_enabled": "true"
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
      - name: match_photos_enabled
      - name: match_photos_use_gpu
      - name: align_cameras_enabled
      - name: depth_maps_enabled
      - name: point_cloud_enabled
      - name: mesh_enabled
      - name: mesh_use_gpu
      - name: dem_orthomosaic_enabled
      - name: match_secondary_photos_enabled
      - name: match_secondary_photos_use_gpu
      - name: align_secondary_cameras_enabled
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
            when: "{{workflow.parameters.match_photos_enabled}} == 'true' && {{workflow.parameters.match_photos_use_gpu}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_photos"

          - name: match-photos-cpu
            depends: "setup"
            when: "{{workflow.parameters.match_photos_enabled}} == 'true' && {{workflow.parameters.match_photos_use_gpu}} == 'false'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_photos"

          - name: align-cameras
            depends: "match-photos-gpu || match-photos-cpu"
            when: "{{workflow.parameters.align_cameras_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "align_cameras"

          - name: depth-maps
            depends: "align-cameras.Succeeded || align-cameras.Skipped"
            when: "{{workflow.parameters.depth_maps_enabled}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "depth_maps"

          - name: point-cloud
            depends: "depth-maps"
            when: "{{workflow.parameters.point_cloud_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "point_cloud"

          # mesh: separate tasks for GPU vs CPU, mutually exclusive via when conditions
          - name: mesh-gpu
            depends: "point-cloud.Succeeded || point-cloud.Skipped"
            when: "{{workflow.parameters.mesh_enabled}} == 'true' && {{workflow.parameters.mesh_use_gpu}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "mesh"

          - name: mesh-cpu
            depends: "point-cloud.Succeeded || point-cloud.Skipped"
            when: "{{workflow.parameters.mesh_enabled}} == 'true' && {{workflow.parameters.mesh_use_gpu}} == 'false'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "mesh"

          - name: dem-orthomosaic
            depends: "(point-cloud.Succeeded || point-cloud.Skipped) && (mesh-gpu.Succeeded || mesh-gpu.Skipped || mesh-cpu.Succeeded || mesh-cpu.Skipped)"
            when: "{{workflow.parameters.dem_orthomosaic_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "dem_orthomosaic"

          # match_secondary_photos: separate tasks for GPU vs CPU, mutually exclusive via when conditions
          - name: match-secondary-photos-gpu
            depends: "dem-orthomosaic.Succeeded || dem-orthomosaic.Skipped"
            when: "{{workflow.parameters.match_secondary_photos_enabled}} == 'true' && {{workflow.parameters.match_secondary_photos_use_gpu}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_secondary_photos"

          - name: match-secondary-photos-cpu
            depends: "dem-orthomosaic.Succeeded || dem-orthomosaic.Skipped"
            when: "{{workflow.parameters.match_secondary_photos_enabled}} == 'true' && {{workflow.parameters.match_secondary_photos_use_gpu}} == 'false'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "match_secondary_photos"

          - name: align-secondary-cameras
            depends: "match-secondary-photos-gpu || match-secondary-photos-cpu"
            when: "{{workflow.parameters.align_secondary_cameras_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "align_secondary_cameras"

          - name: finalize
            depends: "(dem-orthomosaic.Succeeded || dem-orthomosaic.Skipped) && (align-secondary-cameras.Succeeded || align-secondary-cameras.Skipped)"
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

1. **Clean CLI Interface**: Users run `--step match_photos` or `--step mesh` (no GPU suffix)
2. **Config-Driven GPU Selection**: The `matchPhotos.gpu_enabled` and `buildMesh.gpu_enabled` config parameters control node scheduling
3. **Argo Task Names are Internal**: The `-gpu` and `-cpu` suffixes appear only in Argo task names (internal orchestration), not in the user-facing CLI or step values
4. **Mutually Exclusive Execution**: `when` conditions ensure only one variant (GPU or CPU) runs based on the `use_gpu` parameter
5. **Standard Argo Patterns**: Uses proven conditional execution rather than experimental template selection syntax
6. **Python Conventions**: Step names use underscores (match_photos) matching Python method naming, simplifying the dispatcher implementation
7. **Sequential Execution Guarantee**: The `depends` fields enforce strict sequential execution across all 10 steps. Steps never run in parallel because they share the same Metashape project file (.psx) and log files. The DAG dependencies ensure each step completes (or is skipped) before the next begins, preventing file conflicts. This includes the secondary photo steps, which execute sequentially after dem_orthomosaic and before finalize.

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
                - name: match_photos_enabled
                  value: "{{item.match_photos_enabled}}"
                - name: match_photos_use_gpu
                  value: "{{item.match_photos_use_gpu}}"
                - name: align_cameras_enabled
                  value: "{{item.align_cameras_enabled}}"
                - name: depth_maps_enabled
                  value: "{{item.depth_maps_enabled}}"
                - name: point_cloud_enabled
                  value: "{{item.point_cloud_enabled}}"
                - name: mesh_enabled
                  value: "{{item.mesh_enabled}}"
                - name: mesh_use_gpu
                  value: "{{item.mesh_use_gpu}}"
                - name: dem_orthomosaic_enabled
                  value: "{{item.dem_orthomosaic_enabled}}"
                - name: match_secondary_photos_enabled
                  value: "{{item.match_secondary_photos_enabled}}"
                - name: match_secondary_photos_use_gpu
                  value: "{{item.match_secondary_photos_use_gpu}}"
                - name: align_secondary_cameras_enabled
                  value: "{{item.align_secondary_cameras_enabled}}"
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
