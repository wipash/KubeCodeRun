---
# KubeCodeRun-p391
title: Create integration branch from upstream/main
status: completed
type: task
priority: high
created_at: 2026-05-04T21:36:14Z
updated_at: 2026-05-04T22:35:29Z
parent: KubeCodeRun-1ue3
---

Branch off upstream/main as the new base for re-applying fork-only changes.

```bash
git fetch upstream
git switch -c integration/upstream-2026-05 upstream/main
```

## Todo

- [x] git fetch upstream
- [x] git switch -c integration/upstream-2026-05 upstream/main
- [x] Verify HEAD is upstream's e248070 (fix: redis kwargs #55)
- [x] Push branch to origin

## Summary of Changes

Created `integration/upstream-2026-05` from `upstream/main` (HEAD: `e248070`). Pushed to origin.
