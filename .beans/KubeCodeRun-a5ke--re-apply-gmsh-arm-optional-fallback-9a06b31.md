---
# KubeCodeRun-a5ke
title: Re-apply gmsh ARM optional fallback (9a06b31)
status: todo
type: task
priority: normal
created_at: 2026-05-04T21:38:06Z
updated_at: 2026-05-04T21:38:22Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
    - KubeCodeRun-mulr
---

gmsh has no ARM wheels; add it to a python-optional.txt installed with `|| true` so ARM builds succeed.

## Source commit

`9a06b31 fix: make gmsh a best-effort install for ARM compatibility`

## Files

- docker/python.Dockerfile (add the optional install layer)
- docker/requirements/python-analysis.txt (remove gmsh from required list)
- docker/requirements/python-optional.txt (new)

## Conflict expectations

- python.Dockerfile: heavily restructured by upstream #42 (multi-stage with runner) and #45 (DHI minimal). The optional-install layer needs to be re-introduced in the new structure.
- python-analysis.txt: depends on whether upstream's refreshed list still contains gmsh

## Todo

- [ ] Check whether upstream's python-analysis.txt still includes gmsh
- [ ] If yes, remove it
- [ ] Create python-optional.txt with gmsh
- [ ] Add the `pip install -r python-optional.txt || true` layer to python.Dockerfile in the appropriate stage
- [ ] Test build on amd64 and arm64 if possible
