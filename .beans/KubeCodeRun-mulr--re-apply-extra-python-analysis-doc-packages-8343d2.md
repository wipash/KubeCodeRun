---
# KubeCodeRun-mulr
title: Re-apply extra Python analysis & doc packages (8343d2c)
status: todo
type: task
created_at: 2026-05-04T21:38:06Z
updated_at: 2026-05-04T21:38:06Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

Add fork-specific Python packages on top of upstream's refreshed requirements files (#35 made big changes to those files).

## Source commit

`8343d2c feat: add more python analysis and doc packages`

## Files

- docker/requirements/python-analysis.txt
- docker/requirements/python-documents.txt

## Approach

Don't cherry-pick — `git diff 8343d2c~1..8343d2c -- docker/requirements/` to see exactly which package names were added, then add them to upstream's refreshed lists. Upstream may have already added some of them.

## Todo

- [ ] Diff fork's additions
- [ ] Add missing packages to upstream's python-analysis.txt
- [ ] Add missing packages to upstream's python-documents.txt
- [ ] Build the Python image to verify
