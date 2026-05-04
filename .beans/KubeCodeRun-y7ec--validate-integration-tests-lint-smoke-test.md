---
# KubeCodeRun-y7ec
title: 'Validate integration: tests, lint, smoke test'
status: todo
type: task
priority: normal
created_at: 2026-05-04T21:38:22Z
updated_at: 2026-05-04T22:28:20Z
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

- [ ] `just lint` clean
- [ ] `just format-check` clean
- [ ] `just typecheck` clean
- [ ] `just test-unit` all green
- [ ] `just test-integration` against local docker-compose Redis/MinIO + a real cluster
- [ ] Build all language images (`just docker-build` or scripts/build-images.sh)
- [ ] Smoke-test against a real cluster:
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
