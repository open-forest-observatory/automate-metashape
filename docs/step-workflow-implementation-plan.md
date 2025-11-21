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

**Key Benefit:** GPU-intensive steps (depth maps, point cloud, mesh generation) can run on expensive GPU nodes while CPU-only steps (setup, export, GCP addition) run on cheaper CPU nodes, optimizing resource costs across parallel mission processing.

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

Based on benchmarking data from Phase 1, the final step granularity may be adjusted. Initial step list:

| Step | Operations | GPU Required |
|------|------------|--------------|
| `setup` | project_setup, add_photos, calibrate_reflectance | No |
| `match-photos` | matchPhotos | **Yes** |
| `align-cameras` | alignCameras | **Yes** |
| `refine` | filter_points_part1, add_gcps, optimize_cameras, filter_points_part2, export_cameras | No |
| `depth-maps` | buildDepthMaps | **Yes** |
| `point-cloud` | buildPointCloud, classifyGroundPoints (optional) | **Yes** |
| `mesh` | buildModel | **Yes** |
| `dem` | buildDem (all configured types: DSM-ptcloud, DTM-ptcloud, DSM-mesh) | **Yes** |
| `ortho` | buildOrthomosaic (all configured surfaces) | **Yes** |
| `cleanup` | remove point cloud (if configured) | No |
| `export` | export_report, finish_run | No |

**Note:** After Phase 1 benchmarking, some steps may be combined if they're all CPU-bound and fast (e.g., dem + ortho + cleanup + export could become a single `products` step).

### CLI Interface

```bash
# Current behavior preserved (runs all enabled steps)
python metashape_workflow.py config.yml

# New: run single step, load project from previous step
python metashape_workflow.py config.yml --step match-photos
python metashape_workflow.py config.yml --step depth-maps
```

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

    step_methods = {
        'setup': self.run_setup,
        'match-photos': self.run_match_photos,
        'align-cameras': self.run_align_cameras,
        # ...
    }

    step_methods[step_name]()
    self.doc.save()
```

#### 2. Break Apart Tightly Coupled Methods

**`align_photos()`** → split into:
- `run_match_photos()`: calls matchPhotos, saves
- `run_align_cameras()`: calls alignCameras, saves

**`build_dem_orthomosaic()`** → split into:
- `run_dem()`: builds all configured DEMs (DSM-ptcloud, DTM-ptcloud, DSM-mesh)
- `run_ortho()`: builds all configured orthomosaics
- `run_cleanup()`: removes point cloud if configured

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
        'align-cameras': lambda: self.doc.chunk.point_cloud is not None,  # needs match results
        'depth-maps': lambda: len([c for c in self.doc.chunk.cameras if c.transform]) > 0,  # needs alignment
        'dem': lambda: self.doc.chunk.point_cloud is not None or self.doc.chunk.model is not None,
        'ortho': lambda: len(self.doc.chunk.elevations) > 0 or self.doc.chunk.model is not None,
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
      - name: match-photos-enabled
      - name: align-cameras-enabled
      - name: depth-maps-enabled
      # ... other enabled flags
  templates:
    - name: main
      dag:
        tasks:
          - name: setup
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "setup"

          - name: match-photos
            depends: "setup"
            when: "{{workflow.parameters.match-photos-enabled}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "match-photos"

          - name: align-cameras
            depends: "match-photos"
            when: "{{workflow.parameters.align-cameras-enabled}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "align-cameras"

          - name: dem
            depends: "point-cloud.Succeeded || mesh.Succeeded"
            when: "{{workflow.parameters.dem-enabled}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "dem"

          - name: ortho
            depends: "dem.Succeeded || dem.Skipped"
            when: "{{workflow.parameters.ortho-enabled}} == 'true'"
            template: gpu-step
            arguments:
              parameters:
                - name: step
                  value: "ortho"

          - name: cleanup
            depends: "ortho.Succeeded || ortho.Skipped"
            when: "{{workflow.parameters.cleanup-enabled}} == 'true'"
            template: cpu-step
            arguments:
              parameters:
                - name: step
                  value: "cleanup"

          # ... additional steps

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
```

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
                - name: match-photos-enabled
                  value: "{{item.match_photos_enabled}}"
                - name: dem-enabled
                  value: "{{item.dem_enabled}}"
                # ... other params
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
