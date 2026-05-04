---
# KubeCodeRun-2f6h
title: 'Re-apply Connection: close on /files (ad69970)'
status: completed
type: task
priority: normal
created_at: 2026-05-04T21:37:00Z
updated_at: 2026-05-04T22:37:46Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

LibreChat sets a 5s socket timeout on GET /files via axios. When the socket gets reused via HTTP keep-alive for POST /exec, that 5s timer fires mid-execution and produces 'socket hang up'. Send Connection: close to force a fresh socket.

## Source commit

`ad69970 fix: send Connection: close on GET /files to prevent socket hang-up`

## Files

- src/api/files.py
- tests/unit/test_api_files.py

## Conflict expectations

Real overlap with upstream #49 (`434231f fix: use session last_activity as lastModified`) — both touch the GET /files summary endpoint. Resolve by:

1. Keeping upstream's lastModified-from-last_activity logic
2. Layering on the Connection: close response header

## Todo

- [x] Cherry-pick or hand-apply Connection: close changes
- [x] Verify upstream's lastModified handling preserved
- [x] Run tests/unit/test_api_files.py (which now contains both upstream's #49 tests and the fork's Connection: close tests)

## Summary of Changes

Cherry-picked `ad69970` with one conflict in test_api_files.py — resolved by keeping upstream's `mock_session_service` parameter on the new `test_list_files_sets_connection_close` test, then added missing `response=Response()` arg to two upstream tests that predated the response param. All 36 api_files tests pass.
