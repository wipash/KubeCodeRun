---
# KubeCodeRun-mulr
title: Re-apply extra Python analysis & doc packages (8343d2c)
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:38:06Z
updated_at: 2026-05-04T22:50:11Z
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

- [x] Diff fork's additions — gmsh, fortranformat, ezdxf in python-analysis; pymupdf in python-documents
- [x] Add fortranformat and ezdxf to python-analysis.txt (gmsh deferred to gmsh ARM bean a5ke / python-optional.txt)
- [x] Add pymupdf to python-documents.txt
- [ ] Build the Python image to verify (deferred to validation bean y7ec)

## Summary of Changes

Fork's previous additions:
- python-analysis.txt: gmsh, fortranformat, ezdxf
- python-documents.txt: pymupdf

Added fortranformat and ezdxf to python-analysis.txt under a new "Engineering / CAD / file-format helpers" section. gmsh is handled separately in bean a5ke (python-optional.txt for ARM compatibility).

Added pymupdf to python-documents.txt in the PDF section.

None of these were already in upstream's refreshed lists.
