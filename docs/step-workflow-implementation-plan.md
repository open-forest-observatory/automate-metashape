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

| Step | Operations | GPU Capable | Node Type Selection |
|------|------------|-------------|---------------------|
| `setup` | project_setup, add_photos, calibrate_reflectance | No | CPU only |
| `match_photos` | matchPhotos | Yes | Config-driven: `matchPhotos.gpu_enabled` |
| `align_cameras` | alignCameras, filter_points_part1, add_gcps, optimize_cameras, filter_points_part2, export_cameras | No | CPU only |
| `depth_maps` | buildDepthMaps | Yes | GPU only (always benefits) |
| `point_cloud` | buildPointCloud, classifyGroundPoints (optional) | No | CPU only |
| `mesh` | buildModel | Yes | Config-driven: `buildMesh.gpu_enabled` |
| `dem_ortho_finalize` | buildDem, buildOrthomosaic, remove_point_cloud, export_report, finish_run | No | CPU only |

**Note:** For steps with optional GPU acceleration (match_photos, mesh), the config parameter determines:
- **In Argo**: Which node type (GPU vs CPU) to schedule the step on
- **In local execution**: Metashape auto-detects available hardware; the parameter serves as documentation only

### CLI Interface

```bash
# Current behavior preserved (runs all enabled steps)
python metashape_workflow.py config.yml

# New: run single step, load project from previous step
python metashape_workflow.py config.yml --step match_photos
python metashape_workflow.py config.yml --step depth_maps
python metashape_workflow.py config.yml --step mesh
```

**Note:** The step name doesn't specify GPU vs CPU. For GPU-capable steps, hardware selection is automatic:
- Local execution: Metashape auto-detects available GPU
- Argo execution: Config parameter determines node scheduling

### Implementation Details

#### 1. Refactor for Step Execution

- Add `--step` CLI argument to `metashape_workflow.py`
- Create step dispatcher in `MetashapeWorkflow` class
- Each step: loads project → executes operations → saves project

```python
def run_step(self, step_name):
    """Run a single step, loading project from previous step."""
    self.load_project()
    self.validate_prerequisites(step_name)

    # Step names match method names directly
    method = getattr(self, step_name)
    method()
    self.doc.save()
```

#### 2. Break Apart Tightly Coupled Methods

**`align_photos()`** → split into:
- `match_photos()`: calls matchPhotos, saves
- `align_cameras()`: calls alignCameras, then filter_points_part1, add_gcps, optimize_cameras, filter_points_part2, export_cameras

**`build_dem_orthomosaic()`** → becomes:
- `dem_ortho_finalize()`: builds all configured DEMs and orthomosaics (buildDem, buildOrthomosaic), then calls remove_point_cloud, export_report, finish_run

**`build_mesh()`** → extract/rename:
- `build_mesh()`: calls buildModel, saves

**Create new method** for point cloud removal:
- `remove_point_cloud()`: checks config and removes point cloud if configured (wraps `chunk.remove(point_clouds)`)

**Note:** GPU vs CPU selection for matchPhotos and buildModel is handled by Metashape's auto-detection based on available hardware. In Argo workflows, the config parameters `matchPhotos.gpu_enabled` and `buildMesh.gpu_enabled` determine which node type to schedule on.

#### 3. Unified Logging Across Steps

- All steps append to the same log files in the output directory
- Files opened in append mode
- Sequential execution ensures no conflicts

```python
# Each step appends to unified logs
with open(self.log_file, "a") as f:
    f.write(f"{operation_name} | {duration} | CPU: {cpu}% | GPU: {gpu}%\n")
```

#### 4. Prerequisite Validation

Each step validates required prior state:

```python
def validate_prerequisites(self, step_name):
    prereqs = {
        'align_cameras': lambda: self.doc.chunk.point_cloud is not None,  # needs match results
        'depth_maps': lambda: len([c for c in self.doc.chunk.cameras if c.transform]) > 0,  # needs alignment
        'point_cloud': lambda: self.doc.chunk.depth_maps is not None,  # needs depth maps
        'mesh': lambda: self.doc.chunk.depth_maps is not None,  # needs depth maps
        'dem_ortho_finalize': lambda: self.doc.chunk.point_cloud is not None or self.doc.chunk.model is not None,
        # ...
    }
    if step_name in prereqs and not prereqs[step_name]():
        raise ValueError(f"Prerequisites not met for step '{step_name}'")
```

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
  gpu_enabled: true  # If true, run on GPU node; if false, run on CPU node

buildMesh:
  enabled: true
  gpu_enabled: false  # If true, run on GPU node; if false, run on CPU node
```

These parameters serve dual purposes:
- **In Argo**: Determine which node type (GPU vs CPU) to schedule the step on
- **In local execution**: Documentation only; Metashape auto-detects available hardware

**Translation Logic:**

| Step Parameter | Enabled when... | Node Type |
|----------------|-----------------|-----------|
| `setup_enabled` | Always `true` | CPU |
| `match_photos_enabled` | `alignPhotos.enabled == true` | Determined by `alignPhotos.gpu_enabled` |
| `align_cameras_enabled` | `alignPhotos.enabled == true` OR `addGCPs.enabled == true` OR `filterPointsUSGS.enabled == true` OR `optimizeCameras.enabled == true` | CPU |
| `depth_maps_enabled` | `buildDepthMaps.enabled == true` | GPU |
| `point_cloud_enabled` | `buildPointCloud.enabled == true` | CPU |
| `mesh_enabled` | `buildMesh.enabled == true` | Determined by `buildMesh.gpu_enabled` |
| `dem_ortho_finalize_enabled` | Always `true` | CPU |

**Preprocess Step:**

A lightweight Python script runs once per workflow to:
1. Read all mission config YAML files
2. Apply translation logic above for each mission
3. Read `gpu_enabled` parameters to determine node type for GPU-capable steps
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
      - name: dem_ortho_finalize_enabled
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
            depends: "depth-maps"
            when: "{{workflow.parameters.mesh_enabled}} == 'true' && {{workflow.parameters.mesh_use_gpu}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "mesh"

          - name: mesh-cpu
            depends: "depth-maps"
            when: "{{workflow.parameters.mesh_enabled}} == 'true' && {{workflow.parameters.mesh_use_gpu}} == 'false'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "mesh"

          - name: dem-ortho-finalize
            depends: "(point-cloud.Succeeded || point-cloud.Skipped) && (mesh-gpu || mesh-cpu)"
            when: "{{workflow.parameters.dem_ortho_finalize_enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "dem_ortho_finalize"

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
                - name: dem_ortho_finalize_enabled
                  value: "{{item.dem_ortho_finalize_enabled}}"
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
