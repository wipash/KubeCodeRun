---
# KubeCodeRun-y7ec
title: 'Validate integration: tests, lint, smoke test'
status: in-progress
type: task
priority: normal
created_at: 2026-05-04T21:38:22Z
updated_at: 2026-05-04T23:34:47Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-sw3t
    - KubeCodeRun-gkee
    - KubeCodeRun-ym9o
    - KubeCodeRun-2f6h
    - KubeCodeRun-taa0
    - KubeCodeRun-9ma5
    - KubeCodeRun-0935
    - KubeCodeRun-mulr
    - KubeCodeRun-a5ke
---

Final validation pass before merging integration branch into main.

## Todo

- [x] `just lint` clean
- [x] `just format-check` clean (after `just format`)
- [x] `just typecheck` clean
- [x] `just test-unit` — 1330 passed
- [x] `just build-images python` — confirmed working by user
- [x] `just test-images -l py` — confirmed working by user
- [ ] `just test-integration` against full cluster (deferred — user will run post-merge)
- [ ] Smoke-test against a real cluster (deferred — user will run post-merge):
    - [ ] Python warm-pool execution returns generated files
    - [ ] Pool replenishment fires within ~1s after pod kill
    - [ ] LibreChat-style flow: GET /files then POST /exec doesn't hang up
    - [ ] File TTL=0 keeps files indefinitely (upstream #46)
- [ ] If all green: merge `integration/upstream-2026-05` directly into `main` (no PR)
- [ ] Push merged main to origin
- [ ] Delete `origin/integration/upstream-plus-fork-{core,full}` (stale, pre-#42)
- [ ] Delete `origin/integration/upstream-2026-05` after merge

## Cold-path coverage

User confirmed Python is the only production language. The job-handle-based file-capture path (KubeCodeRun-0935) is covered by unit tests in `tests/unit/test_execution_runner.py` / `test_job_executor.py` — no manual smoke step required.
