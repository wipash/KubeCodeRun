# Socket Hang-Up Investigation - Phase 5

**Date:** 2026-02-10
**Branch:** `hangup-fixes`
**Version:** `2.1.3.dev4`
**Evidence:** `success3.log`, `fail4.log`, `fail5.log`

## The Controlled Experiment

Three tests were run from LibreChat as agent tool calls, all executing the same Python code (`time.sleep(10); print(...)`). The only variable changed was the file attachment:

| Test | File | Size | Duration | Disconnect at | Result |
|------|------|------|----------|---------------|--------|
| success3 | None | - | 10,160ms | Never | OK |
| fail4 | CSV | 45MB | 10,768ms | 4.998s | socket hang up |
| fail5 | TXT | 2KB | 10,064ms | 5.000s | socket hang up |

**File size is irrelevant.** A 2KB text file triggers the exact same failure as a 45MB CSV. The 2KB file uploads to the sidecar in 3ms. There is no meaningful I/O, no memory pressure, no event loop blocking.

## What the Logs Show

### success3.log (no attachment, 10s sleep - SUCCESS)

```
09:41:54.739  POST /exec received (new session, no files)
09:41:54.855  Starting execution
09:42:04.892  Sidecar: exit_code=0, stdout="10s wait"
09:42:04.896  client_disconnected: false
09:42:04.896  INFO: POST /exec 200 OK (uvicorn access log present)
```

No preceding GET /files requests. POST /exec arrives on a fresh TCP connection (port 33598). 10s execution completes with no issues.

### fail4.log (45MB attachment, 10s sleep - FAIL)

```
09:44:39.837  GET /files from port 39538 → 200 OK (1.96ms)
09:44:44.347  GET /files from port 39538 → 200 OK (1.67ms)  ← same connection
09:44:44.359  POST /exec received (12ms after GET, likely same connection)
09:44:44.831  Starting execution
09:44:45.079  File uploaded to sidecar (POST /files 200 OK)
09:44:49.357  *** LibreChat: socket hang up ***  (4.998s from POST /exec)
09:44:55.112  Sidecar: exit_code=0 (execution actually succeeds)
09:44:55.126  client_disconnected: true
              No uvicorn access log for POST /exec
```

### fail5.log (2KB attachment, 10s sleep - FAIL)

```
09:47:22.879  GET /files from port 34228 → 200 OK (4.73ms)
09:47:27.181  GET /files from port 34228 → 200 OK (1.98ms)  ← same connection
09:47:27.188  POST /exec received (7ms after GET, likely same connection)
09:47:27.199  Starting execution
09:47:27.202  File uploaded to sidecar (3ms for 2KB!)
09:47:32.188  *** LibreChat: socket hang up ***  (5.000s from POST /exec)
09:47:37.237  Sidecar: exit_code=0 (execution actually succeeds)
09:47:37.251  client_disconnected: true
              No uvicorn access log for POST /exec
```

## The Critical Difference: HTTP Connection Reuse

The ONLY structural difference between success and failure cases:

**When files are attached**, LibreChat makes GET /files requests to check file existence BEFORE sending POST /exec. These GET requests and the subsequent POST /exec **share the same TCP connection** (HTTP keep-alive — same source port in the logs).

**When no files are attached**, LibreChat sends POST /exec on a **fresh TCP connection** with no preceding requests.

```
SUCCESS PATH:
  [fresh connection] → POST /exec → wait 10s → response → OK

FAILURE PATH:
  [connection] → GET /files → response
  [same connection, keep-alive] → GET /files → response
  [same connection, keep-alive] → POST /exec → wait 5s → DISCONNECT
```

## Analysis

### What we can rule out

1. **File size** — 2KB triggers identical failure to 45MB (5.000s vs 4.998s)
2. **Event loop blocking** — 2KB MinIO download + 3ms sidecar upload is negligible
3. **Memory pressure** — 2KB file uses no meaningful memory
4. **KCR-side execution differences** — the code path differences for a 2KB file are milliseconds of async work
5. **A simple 5s client-side timeout** — if LibreChat had a blanket 5s timeout, success3 (10s, no files) would also fail

### What the evidence points to

The 5s disconnect is tied to HTTP **connection reuse**. When POST /exec runs on a connection that previously handled GET /files requests, it disconnects at exactly 5s. When POST /exec runs on a fresh connection, it does not.

Possible mechanisms:

1. **Socket timeout inherited from GET /files handling.** LibreChat (or its HTTP library) sets a socket-level timeout during the GET /files request (e.g., `socket.setTimeout(5000)` for a quick metadata check). When the socket is reused for POST /exec via HTTP keep-alive, the timeout persists. After 5s of no response data on POST /exec, the timeout fires and `socket.destroy()` is called, producing "socket hang up."

2. **Node.js HTTP agent behavior.** The Node.js `http.Agent` with `keepAlive: true` pools connections. If the agent has a socket timeout configured (or if the GET /files call path configures one), it may carry over to reused connections.

3. **LibreChat's file-checking code path sets a per-request timeout** that inadvertently leaks to the connection level rather than the request level.

### Why this looks like a client-side issue despite being triggered by file presence

The KCR server-side code path for a 2KB file vs no file is nearly identical in timing:
- Without file: request → session → execute (no `_mount_files`)
- With 2KB file: request → session → MinIO download (< 1ms) → sidecar upload (3ms) → execute

The 4ms of extra server-side work cannot cause a 5s timeout. The difference must be in HOW the connection is established and managed, not in WHAT happens during request processing.

### Connection reuse is testable

If the root cause is connection reuse, we can verify by forcing KCR to send `Connection: close` on GET /files responses. This would force LibreChat to open a new connection for POST /exec, matching the success path.

## Proposed Mitigations

### Option A: Force fresh connections for /exec (quick test)

Add `Connection: close` header to GET /files responses, forcing the client to open a new TCP connection for POST /exec.

**Pros:** Simple, directly tests the connection reuse theory, zero risk
**Cons:** Slightly increases latency (new TCP handshake per request), doesn't fix the root cause

### Option B: Heartbeat streaming (from investigation4)

Send periodic whitespace bytes before the JSON response to reset idle socket timers.

**Pros:** Works regardless of connection state, keeps connection alive
**Cons:** Adds complexity, error handling after headers committed, may not work if timeout is absolute (not idle)

### Option C: Early response byte

Send an HTTP 200 with chunked transfer encoding immediately, then send the actual JSON body when ready. No periodic heartbeat needed — just one early write.

**Pros:** Simpler than full heartbeat, resets the idle timer once
**Cons:** Commits 200 status before knowing if execution succeeds

### Recommended immediate action

**Test Option A first** — it's a 2-line change that directly validates the theory. If adding `Connection: close` to GET /files fixes the problem, we know the root cause is connection reuse and can decide on the right permanent fix (which might be a LibreChat-side fix, or Option B/C on our side).

## Open Questions

1. **What in LibreChat sets the 5s socket timeout?** We can't see LibreChat's HTTP client configuration. Searching their codebase for `setTimeout`, `timeout: 5000`, or agent configuration would confirm.
2. **Is 5s a default somewhere in the Node.js HTTP stack?** Node.js `http.Agent` has `keepAliveTimeout` and `freeSocketTimeout` defaults that have changed across versions.
3. **Would `Connection: close` on GET /files be sufficient?** Or does LibreChat reuse connections in other scenarios too?

## Files Referenced

| File | Description |
|------|-------------|
| success3.log | 10s sleep, no file — succeeds at 10.1s |
| fail4.log | 10s sleep, 45MB file — disconnects at 4.998s |
| fail5.log | 10s sleep, 2KB file — disconnects at 5.000s |
| src/api/exec.py | POST /exec endpoint (has diagnostic logging) |
| src/middleware/metrics.py | ASGI middleware (has disconnect detection) |
| src/services/orchestrator.py | _mount_files() handles file downloads |
| src/services/kubernetes/pool.py | execute_in_pod() uploads files to sidecar |
