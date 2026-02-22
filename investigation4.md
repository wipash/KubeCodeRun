# Socket Hang-Up Investigation - Phase 4

**Date:** 2026-02-10  
**Branch:** `hangup-fixes`  
**Deployed version analyzed:** `2.1.3.dev4`  
**Primary evidence files:** `fail3.log`, `success2.log`

## Executive Summary

The root cause is now confirmed: the LibreChat side closes the `/exec` HTTP connection before KubeCodeRun can return a response on heavy requests. KubeCodeRun completes execution successfully, but by response time the client has already disconnected.

This is not a KubeCodeRun execution failure and not a sidecar execution failure. It is a connection-lifecycle issue between request start and first response bytes.

Most likely trigger (high confidence): a ~5 second client-side socket timeout behavior in the LibreChat/Node request path for `CodeExecutor` requests.

## Current Status

1. Diagnostic logging is deployed and active in `2.1.3.dev4`.
2. Two new corrected logs (`fail3.log`, `success2.log`) provide decisive evidence.
3. Previous KubeCodeRun fixes did not change symptoms because they targeted server internals, while the observed disconnect is upstream.
4. We cannot change LibreChat code right now, so mitigation must happen on KubeCodeRun side.

## What We Learned (Definitive Evidence)

## 1) Failing requests are not failing execution; they are failing response delivery after client disconnect

### Fail case #1 (`fail3.log`)

- Request accepted: `07:49:12.841` (`fail3.log:22`)
- Execution started: `07:49:13.317` (`fail3.log:24`)
- LibreChat error: `socket hang up` at `07:49:17.835` (`fail3.log:33`, `fail3.log:35`)
- Sidecar execution success: `POST /execute 200` at `07:49:18.835` (`fail3.log:39`)
- KCR execution completed: `07:49:18.849` (`fail3.log:43`)
- KCR logs disconnect: `Client disconnected during request processing` (`fail3.log:45`)
- KCR confirms response could not be delivered: `Client disconnected before response could be sent` (`fail3.log:46`)

Observed gap from request start to LibreChat error: ~4.99 seconds.

### Fail case #2 (`fail3.log`)

- Request accepted: `07:49:21.099` (`fail3.log:59`)
- Execution started: `07:49:21.533` (`fail3.log:61`)
- LibreChat error: `socket hang up` at `07:49:26.099` (`fail3.log:74`, `fail3.log:76`)
- Sidecar execution success: `POST /execute 200` at `07:49:26.860` (`fail3.log:80`)
- KCR execution completed: `07:49:26.874` (`fail3.log:84`)
- KCR logs disconnect + unable to send response (`fail3.log:86`, `fail3.log:87`)

Observed gap from request start to LibreChat error: ~5.00 seconds.

## 2) Successful requests do not show disconnects

In `success2.log`:

- Long-running calls (~9s and ~19s) complete with normal `POST /exec ... 200 OK` uvicorn access logs (`success2.log:116`, `success2.log:135`, `success2.log:184`).
- `client_disconnected: false` for completed responses (`success2.log:69`, `success2.log:72`, `success2.log:115`, `success2.log:134`, `success2.log:183`).

This rules out a hard KubeCodeRun 5-second execution cap.

## 3) The timing signature is the key

The failing calls terminate near a consistent ~5-second window before KubeCodeRun returns response bytes. That strongly matches a socket/idle timeout behavior on the caller side path.

## 4) Why the error string is `socket hang up`

In Node + `node-fetch`, `socket hang up` is the surfaced fetch error when the socket is reset/closed in a way exposed as connection failure (commonly `ECONNRESET` in the underlying layer). This wording does not mean KubeCodeRun logic failed; it means the HTTP socket died before response headers/body were delivered to caller code.

## Hypotheses Investigated and Status

1. `BaseHTTPMiddleware` response bridging issue: **not root cause** (converted to pure ASGI already; symptom unchanged).
2. Uvicorn keep-alive timeout too low: **not root cause** (increased to 75s; symptom unchanged).
3. Blocking MinIO `response.read()` event-loop stall: **real bug, fixed**, but **not root cause of persistent 5s disconnect signature**.
4. Sidecar execution failure: **ruled out** (sidecar returns `POST /execute 200`, execution completes).
5. Kubernetes readiness/liveness probe removal: **unlikely** and inconsistent with observed per-request timing and success patterns.
6. Client-side request transport timeout behavior: **most likely root cause**.

## Working Root-Cause Statement

When `/exec` requests with larger file-related processing exceed ~5 seconds before first response bytes, the LibreChat caller path disconnects the socket. KubeCodeRun then completes execution but cannot deliver the HTTP response because the client is already gone.

This explains:

- why server-side execution succeeds,
- why KubeCodeRun logs disconnect at response time,
- why `socket hang up` appears on LibreChat,
- why previous server-only fixes did not resolve symptoms.

## Constraints for Mitigation

1. LibreChat code cannot be changed right now.
2. We can make KubeCodeRun behavior changes immediately (development environment).
3. No feature flags required for this phase.
4. We should implement tests first.

---

# Implementation Plan (No Code): Always-On `/exec` Heartbeat Streaming

## Goal

Keep the HTTP connection alive for long `/exec` requests by sending periodic response bytes before final JSON, so caller-side idle socket timeouts are not hit.

## Design Principle

Return a streaming JSON response for long-running requests:

- send heartbeat chunks while execution is running,
- send final JSON payload at completion,
- keep output parseable by existing clients that call `response.json()`.

Heartbeat chunks will be JSON-safe leading whitespace/newlines so final body remains valid JSON.

## Test-First Execution Plan

## Phase A: Write failing tests (RED)

### A1. Integration tests in `tests/integration/test_exec_api.py`

Add tests that currently fail under existing non-streaming behavior:

1. `test_exec_sends_early_heartbeat_for_long_request`
   - Simulate slow orchestrator execution (>6s).
   - Assert first bytes are received before execution completes (time-to-first-byte well under 5s).

2. `test_exec_streamed_response_ends_with_valid_exec_json`
   - Consume full streamed response.
   - Assert final body parses as valid JSON.
   - Assert it contains expected `ExecResponse` keys (`session_id`, `files`, `stdout`, `stderr`).

3. `test_exec_streamed_path_handles_runtime_error_with_json_payload`
   - Simulate exception after stream has started.
   - Assert response remains parseable JSON and includes error text in payload (`stderr` or equivalent planned contract).
   - Assert no raw traceback leakage.

### A2. Unit tests in `tests/unit/test_api_exec.py`

Add direct endpoint behavior tests with mocks:

1. `test_execute_code_fast_path_returns_normal_non_stream_response`
   - Orchestrator completes quickly.
   - Assert existing behavior preserved.

2. `test_execute_code_slow_path_returns_streaming_response`
   - Orchestrator deliberately delayed.
   - Assert response object is streaming path and emits heartbeat chunks before final payload.

3. `test_execute_code_streaming_path_logs_disconnect_and_completion`
   - Simulate disconnect state and ensure existing diagnostics still fire.

4. `test_execute_code_streaming_path_error_after_commit_is_json`
   - Ensure committed stream errors are converted into parseable JSON payload, not broken connection.

## Phase B: Endpoint behavior refactor

Refactor `src/api/exec.py` to support two internal paths:

1. **Fast path:** keep existing immediate JSON response behavior when execution completes quickly.
2. **Streaming path:** for in-flight requests beyond the initial short wait window.

Execution model:

- Start `orchestrator.execute(...)` in an async task.
- Wait a short initial window.
- If done: return normal JSON response.
- If not done: begin streaming response and emit heartbeat chunks until task completion.

## Phase C: Heartbeat streaming mechanics

1. Use `StreamingResponse` with `application/json`.
2. Emit periodic whitespace/newline chunks (JSON-safe) while task is running.
3. When execution completes, append final serialized JSON payload as final chunk.
4. Ensure no extra bytes after final JSON to preserve parseability.

## Phase D: Error handling strategy for streaming

Need deterministic behavior for two timing cases:

1. **Error before stream starts:** keep current exception handling/status behavior.
2. **Error after stream started (headers committed):** emit final JSON error payload (200 response already committed) and log structured streaming error event.

This avoids truncated/broken streams that clients cannot parse.

## Phase E: Logging and observability

Add structured logs around streaming lifecycle:

1. stream start decision (`fast_path` vs `stream_path`)
2. heartbeat interval and count
3. execution completion timing
4. disconnect events (already present; keep integrated)
5. stream-ended-with-error indicator

This allows clear validation during reproductions.

## Phase F: Validation and acceptance criteria

Success criteria:

1. Reproducing prior fail scenario no longer yields `socket hang up` for long `/exec` calls.
2. KCR no longer reports `client_disconnected=true` for those calls.
3. Long `/exec` requests still produce parseable final JSON payloads.
4. Existing short-request behavior remains correct.
5. Unit + integration test suites pass for `/exec` and related middleware behaviors.

---

# Risks and Mitigations

1. **Risk:** Some clients may not tolerate streamed JSON with leading whitespace.
   - **Mitigation:** use strict JSON-safe whitespace only; validate against LibreChat behavior in integration tests.

2. **Risk:** Exception after stream commit could otherwise corrupt response.
   - **Mitigation:** explicit committed-stream JSON error payload path.

3. **Risk:** Additional complexity in endpoint control flow.
   - **Mitigation:** isolate streaming orchestration into small helper functions and keep fast path explicit.

4. **Risk:** If upstream enforces absolute total request deadline (not idle deadline), heartbeat will not help.
   - **Mitigation:** tests and runtime evidence currently indicate idle/first-byte behavior; re-evaluate only if failures persist post-streaming.

---

# Immediate Next Step

Proceed with the RED phase first: add failing integration and unit tests that prove heartbeat-before-5s and final parseable JSON behavior are currently missing.
