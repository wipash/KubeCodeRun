---
# KubeCodeRun-sw3t
title: Re-apply ASGI middleware swap (99d6139)
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:36:24Z
updated_at: 2026-05-04T22:35:56Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

Replace BaseHTTPMiddleware with pure ASGI in metrics/security/headers middleware. Fixes silent response loss on long-running POST /exec requests.

## Source commit

`99d6139 fix: replace BaseHTTPMiddleware with pure ASGI to prevent socket hang up`

## Files

- src/middleware/headers.py
- src/middleware/metrics.py
- src/middleware/security.py
- src/services/orchestrator.py (small follow-on)
- tests/unit/test_metrics_middleware.py

## Conflict expectations

Orthogonal to upstream #42 — none of these middleware files are touched by upstream. Should cherry-pick cleanly.

## Todo

- [x] git cherry-pick 99d6139 (or rewrite by hand)
- [x] Run tests/unit/test_metrics_middleware.py
- [x] Run `just lint` and `just typecheck`

## Summary of Changes

Cherry-picked `99d6139` cleanly (only auto-merge in orchestrator.py). All metrics middleware tests passing, lint and typecheck clean.
