---
# KubeCodeRun-ym9o
title: Re-apply uvicorn keep-alive timeout (b21969c)
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:36:36Z
updated_at: 2026-05-04T22:36:34Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

Bump uvicorn timeout-keep-alive default from 5s to 75s; expose via API_TIMEOUT_KEEP_ALIVE.

## Source commit

`b21969c fix: increase uvicorn keep-alive timeout to prevent socket hang-ups`

## Files

- src/config/__init__.py
- src/config/api.py
- src/main.py
- helm-deployments/kubecoderun/templates/configmap.yaml
- helm-deployments/kubecoderun/values.yaml

## Conflict expectations

Textual conflicts likely — upstream #42, #47, #48, #52 also touch config files (helm + python config). Resolve by adding the keep-alive setting alongside upstream's new settings.

## Todo

- [x] git cherry-pick b21969c
- [x] Resolve conflicts in config/__init__.py, helm configmap, values.yaml (auto-merged cleanly)
- [x] Verify both new upstream settings AND keep-alive setting are present

## Summary of Changes

Cherry-picked `b21969c` cleanly — git auto-merged the helm config files alongside upstream's #41/#47/#48 additions. Verified `api_timeout_keep_alive=75` plumbed through config → main → uvicorn.
