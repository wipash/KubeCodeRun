---
# KubeCodeRun-0935
title: 'Decide: fork''s job-files capture vs upstream #50'
status: todo
type: task
priority: normal
created_at: 2026-05-04T21:37:44Z
updated_at: 2026-05-04T22:11:23Z
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

- [ ] Read post-#42 `job_executor.py` end-to-end (file structure changed substantially under the runner-binary rewrite)
- [ ] Hand-port the signature change: `execute_with_job` returns `(ExecutionResult, JobHandle | None)`, removes auto-delete on success, deletes on exception
- [ ] Hand-port `manager.execute_with_pod_or_job` to thread the JobHandle through
- [ ] Hand-port `manager.destroy_pod` isinstance dispatch (PodHandle → pool.release, JobHandle → job_executor.delete_job)
- [ ] Hand-port `runner._detect_generated_files` type widening to `PodHandle | JobHandle`
- [ ] Hand-port the `container_source == 'job'` branch that always detects files (skip Python keyword heuristic)
- [ ] Export JobHandle from `src/services/kubernetes/__init__.py`
- [ ] Re-apply tests/unit/test_execution_runner.py, test_job_executor.py, test_kubernetes_manager.py changes
- [ ] Verify any upstream #50 tests in test_orchestrator.py / test_execution_runner.py are removed or rewritten (they test the pre-download path that won't exist)
