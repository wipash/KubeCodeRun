---
# KubeCodeRun-a5ke
title: Re-apply gmsh ARM optional fallback (9a06b31)
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:38:06Z
updated_at: 2026-05-04T22:50:42Z
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

- [x] Check whether upstream's python-analysis.txt still includes gmsh — it doesn't (upstream's refresh removed it)
- [x] No removal needed
- [x] Create python-optional.txt with gmsh
- [x] Add the `pip install -r python-optional.txt || true` layer to python.Dockerfile in the builder stage (after the main pip install, before the runtime-deps stage)
- [ ] Test build on amd64 and arm64 (deferred to validation bean y7ec)

## Summary of Changes

Created `docker/requirements/python-optional.txt` containing only `gmsh>=4.15.1`. Added an extra `COPY` + `pip install -r ... || true` layer to `docker/python.Dockerfile` immediately after the main pip install in the builder stage.

The optional layer runs in the builder stage, so installed packages land in `/opt/python/lib/python3.14/site-packages` and are picked up by the existing `COPY --from=builder /opt/python/lib/python3.14/site-packages ...` in the final stage. No additional copy needed in the final stage.
