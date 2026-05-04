---
# KubeCodeRun-0935
title: 'Decide: fork''s job-files capture vs upstream #50'
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:37:44Z
updated_at: 2026-05-04T22:49:27Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

Both fork and upstream solve the same bug — generated files lost when running cold-path languages via Job (no warm pool). Pick one approach.

## The two approaches

### Fork: `341db59` — return JobHandle, reuse pipeline

```
job_executor: returns (ExecutionResult, JobHandle), caller owns cleanup
manager: isinstance dispatch in destroy_pod
runner: always detect files for job-sourced executions (no Python-keyword heuristic)
```

**Pro:** simpler, reuses the existing warm-pool file pipeline. Files fetched on-demand from the pod handle.
**Con:** if the pod gets evicted between job completion and file fetch, files are lost.

### Upstream #50: `00e14ca` — pre-download into ExecutionResult

```
job_executor: new get_generated_file_content(path) method
ExecutionResult: gains file_contents dict keyed by (session_id, path)
ExecutionServiceInterface: new method to read pre-downloaded content
orchestrator: use pre-downloaded content when container is unavailable
```

**Pro:** files are captured BEFORE pod cleanup, so eviction races are impossible.
**Con:** download happens whether or not the file is needed; bigger memory footprint for large files.

## Decision: Option A — fork's approach (341db59)

User confirmed Python is the only language exercised in production. The cold-path file-capture flow that #50 hardens is theoretical for this fork's use, so the simpler architecture wins.

Behavioral bonuses we get from fork's approach:
- Files captured even when exit_code ≠ 0 (#50 drops them)
- No leaked entries in a per-session cache dict
- One unified `_detect_generated_files` pipeline instead of two

## Todo

- [x] Read post-#42 `job_executor.py` end-to-end
- [x] Hand-port `execute_with_job` to return `(ExecutionResult, JobHandle | None)`; remove auto-delete on success; delete on exception
- [x] Removed upstream's `_collect_generated_files` method (no longer needed)
- [x] Hand-port `manager.execute_code` to thread the JobHandle through
- [x] Hand-port `manager.destroy_pod` isinstance dispatch (PodHandle → pool.release, JobHandle → job_executor.delete_job)
- [x] Hand-port `runner._detect_generated_files` type widening to `PodHandle | JobHandle`
- [x] Removed upstream's job-files cache (`_job_file_contents`, `pop_job_file_content`) — pipeline now unified
- [x] Removed upstream's `ExecutionResult.generated_files` field — no longer needed
- [x] Export JobHandle from `src/services/kubernetes/__init__.py`
- [x] Removed `pop_job_file_content` from ExecutionServiceInterface
- [x] Updated tests/unit/test_execution_runner.py, test_job_executor.py, test_kubernetes_manager.py, test_orchestrator.py — removed upstream #50 tests, updated signatures

## Summary of Changes

Replaced upstream #50's pre-download cache architecture with the fork's unified-pipeline approach:

**job_executor.py** — `execute_with_job` now returns `tuple[ExecutionResult, JobHandle | None]`. The job is no longer auto-deleted in a `finally:` block; the caller (manager.destroy_pod) owns lifecycle. Exceptions still delete the job before re-raising. Removed the entire `_collect_generated_files` method (~85 lines).

**manager.py** — `execute_code` unpacks and threads the JobHandle through to the orchestrator. `destroy_pod` dispatches via `isinstance(handle, JobHandle)` to `job_executor.delete_job`. `_active_handles` widened to `dict[str, PodHandle | JobHandle]`.

**runner.py** — `_detect_generated_files` accepts `PodHandle | JobHandle`. Removed the `_job_file_contents` dict, the `pop_job_file_content` method, and the entire "job path" branch in `execute()` (was copying upstream's pre-downloaded bytes into the cache).

**orchestrator.py** — `_get_file_from_container` no longer takes `session_id` (was only used for job-cache lookup); when container is None, returns None directly.

**interfaces.py** — Removed the `pop_job_file_content` method from ExecutionServiceInterface.

**models.py** — Removed `ExecutionResult.generated_files` field.

**__init__.py** — Exported JobHandle from the kubernetes package.

Net change: ~180 lines removed (upstream #50 was 212+/15-, this reversal is most of that). The remaining file-detection pipeline is the original pool-path logic, now used uniformly for both pool and job execution. Test count: 1330 (1334 minus 3 removed pop_job_file_content tests, minus 1 removed test_get_file_no_container_with_job_content).
