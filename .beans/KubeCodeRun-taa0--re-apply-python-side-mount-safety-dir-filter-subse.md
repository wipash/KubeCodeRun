---
# KubeCodeRun-taa0
title: Re-apply Python-side mount safety + dir filter (subset of 0a9be5d)
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:37:00Z
updated_at: 2026-05-04T22:41:30Z
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

- [x] Hand-port orchestrator.py mount-failure aggregation (don't cherry-pick — file diverged too much)
- [x] Hand-port runner.py is_file filter
- [x] Hand-port manager.py JSON-directory-listing rejection
- [x] Skipped re-applying tests/unit/test_issue_16_file_disappearance.py — covered by existing test_orchestrator.py mount-failure test (updated to expect ValidationError) and by the JSON-rejection test path
- [x] Run tests — all 1334 pass

## Summary of Changes

Hand-ported the Python-side mount-safety + directory-filter defenses on top of post-#42 / post-#50 code:

- **`src/services/orchestrator.py`** — `_mount_files` now collects failed-file IDs and raises `ValidationError` if any failed. `_handle_generated_files` skips when `_get_file_from_container` returns None. `_get_file_from_container` signature is now `bytes | None`, returns None instead of error-content bytes (caller decides what to do with missing files).
- **`src/services/kubernetes/manager.py`** — `copy_file_from_pod` rejects responses with `Content-Type: application/json` (the Go runner returns JSON when asked to download a directory).
- **`src/services/execution/runner.py`** — `_detect_generated_files` skips entries with `is_file=False`. (No-op against current Go runner since it doesn't emit that field, but harmless and future-proof if added.)

Updated 3 tests in test_orchestrator.py whose pre-port behavior expected error-content sentinels rather than None / raised exceptions.

The Go runner (docker/runner/files.go) does not filter directories at the source. The Python-side defenses make this benign — the worst case is one wasted slot in max_output_files.
