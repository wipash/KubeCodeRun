---
# KubeCodeRun-taa0
title: Re-apply Python-side mount safety + dir filter (subset of 0a9be5d)
status: in-progress
type: task
priority: normal
created_at: 2026-05-04T21:37:00Z
updated_at: 2026-05-04T22:37:46Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

Original commit covered 5 layers of defense; 2 of them lived in docker/sidecar/main.py which upstream #42 deletes. Re-apply only the Python-side layers.

## Source commit

`0a9be5d fix: raise on file mount failures and filter directories from generated files (#16)`

## What to keep (Python side, all still applicable)

- src/services/orchestrator.py — `_mount_files()` collects failures and raises ValidationError; `_handle_generated_files` skips None content
- src/services/execution/runner.py — `_detect_generated_files` skips is_file=False entries
- src/services/kubernetes/manager.py — `copy_file_from_pod` rejects JSON directory listings
- tests/unit/test_issue_16_file_disappearance.py
- tests/unit/test_orchestrator.py changes

## What to drop

- docker/sidecar/main.py changes (file deleted by upstream #42)

## Optional follow-up (defer)

The Go runner's `HandleList` and `HandleDownload` (docker/runner/files.go) do NOT filter directories. Python-side defenses handle this, but a small upstream PR to filter at the runner layer would be cleaner — defer.

## Conflict expectations

Real semantic conflicts:
- runner.py: upstream #42 and #50 changed `_detect_generated_files` shape; merge by hand
- manager.py: upstream #42 rewrote pod manifest creation; merge JSON-rejection in carefully
- orchestrator.py: upstream #38, #42, #50 all touched it

## Todo

- [ ] Hand-port orchestrator.py mount-failure aggregation (don't cherry-pick — file diverged too much)
- [ ] Hand-port runner.py is_file filter
- [ ] Hand-port manager.py JSON-directory-listing rejection
- [ ] Re-apply tests/unit/test_issue_16_file_disappearance.py (verify naming still relevant)
- [ ] Run tests
