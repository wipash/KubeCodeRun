---
# KubeCodeRun-gkee
title: Re-apply MinIO async file read (c5e7c36)
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:36:36Z
updated_at: 2026-05-04T22:36:12Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

Move MinIO response.read() into the thread executor so file downloads don't block the asyncio event loop (and uvicorn protocol handling).

## Source commit

`c5e7c36 fix: move MinIO response.read() into executor to unblock event loop`

## Files

- src/services/file.py (only)

## Conflict expectations

Clean — upstream doesn't touch src/services/file.py for this concern.

## Todo

- [x] git cherry-pick c5e7c36
- [x] Run tests/unit/test_file_service.py

## Summary of Changes

Cherry-picked `c5e7c36` cleanly. All 49 file_service tests pass.
