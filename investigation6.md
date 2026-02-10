# Socket Hang-Up Investigation - Phase 6

**Date:** 2026-02-10
**Branch:** `hangup-fixes`
**Version:** `2.1.3.dev4` + Connection: close fix
**Previous phases:** investigation.md → investigation5claude.md

## Root Cause Identified

The 5-second socket hang-up is caused by **HTTP socket timeout inheritance through Node.js keep-alive connection reuse** between LibreChat's axios calls and the agents framework's node-fetch calls.

### The Chain of Events

1. **LibreChat's `getSessionInfo()`** in `api/server/services/Files/Code/process.js` calls `GET /files/{session_id}` using axios with `timeout: 5000`:
   ```javascript
   axios.request({
     url: `${baseURL}/files/${session_id}`,
     timeout: 5000,  // ← THE 5-SECOND KILLER
   });
   ```

2. **axios internally calls `socket.setTimeout(5000)`** on the underlying TCP socket. This is how Node.js HTTP request timeouts work — they set an inactivity timer on the socket itself.

3. **The request completes in ~2ms**, but the socket goes back to Node.js's `http.globalAgent` keep-alive pool **with the 5000ms timeout still active**. axios does not clear `socket.setTimeout()` after request completion.

4. **The agents framework's `CodeExecutor.ts`** (in `danny-avila/agents`) then makes:
   - `GET /files/${session_id}?detail=full` via node-fetch (no timeout) — to fetch file references
   - `POST /exec` via node-fetch (no timeout) — to execute code

5. **Both axios and node-fetch use `http.globalAgent` by default**, so they share the same socket pool. node-fetch picks up the same socket that axios used, complete with its inherited `socket.setTimeout(5000)`.

6. **POST /exec takes >5s** (code execution, file upload to sidecar, etc.). After 5000ms of no data received on the socket, the timeout fires → `socket.destroy()` → node-fetch sees "socket hang up".

### Evidence That Confirms This

| Evidence | Explanation |
|----------|-------------|
| **Exactly 5.000s timing** (investigation5) | Matches `timeout: 5000` in LibreChat's `getSessionInfo()` |
| **File size irrelevant** — 2KB fails same as 45MB (investigation5) | It's not about server-side processing; it's about socket timeout inheritance |
| **No-file requests succeed** even at 10+ seconds (investigation5) | No GET /files → no axios timeout → fresh socket → no inherited timeout |
| **Same source port** for GET /files and POST /exec (investigation5 logs) | Proves HTTP keep-alive connection reuse |
| **Client disconnects first** (investigation4 diagnostic logs) | The socket timeout fires on the client side, not server side |
| **Server completes execution successfully** (all phases) | KCR processes the request fine; the connection is already dead by response time |

### Timeline Reconstruction (from fail5.log — 2KB file)

```
09:47:22.879  GET /files/session (LibreChat axios, timeout:5000)
              → socket.setTimeout(5000) set on TCP socket (port 34228)
              → response received in ~5ms
              → socket returned to http.globalAgent pool WITH 5s timeout still active

09:47:27.181  GET /files/session?detail=full (agents node-fetch, no timeout)
              → reuses same socket (port 34228) from pool
              → sending request resets the inactivity timer
              → response received in ~2ms
              → socket stays in pool, timeout still ticking

09:47:27.188  POST /exec (agents node-fetch, no timeout)
              → reuses same socket (port 34228)
              → request body sent (resets inactivity timer)
              → server starts processing...
              → no response data coming back (server is executing code)...

09:47:32.188  *** 5000ms of inactivity on socket ***
              → socket.setTimeout fires
              → socket.destroy() called
              → node-fetch receives "socket hang up" error
              → LibreChat shows: "Execution error: request to ... failed, reason: socket hang up"

09:47:37.237  KCR server finishes execution (exit_code=0)
              → tries to send HTTP 200 response
              → transport.is_closing() = true (client already gone)
              → response silently dropped, no uvicorn access log
```

## Sources Consulted

### DeepWiki: danny-avila/LibreChat

Key findings from LibreChat's codebase:

- **`api/server/services/Files/Code/process.js`** — `getSessionInfo()` uses axios with `timeout: 5000` (5 seconds) to call GET /files
- **`api/server/services/Files/Code/crud.js`** — `getCodeOutputDownloadStream()` uses axios with `timeout: 15000` (15 seconds), `uploadCodeEnvFile()` has no explicit timeout
- **`packages/api/src/utils/axios.ts`** — `createAxiosInstance()` has no default timeout, no custom HTTP agent, no keepAlive configuration
- File handling flow: `processAgentFileUpload` → `uploadCodeEnvFile` → returns `fileIdentifier` with session_id and fileId

### DeepWiki: danny-avila/agents

Key findings from the agents framework:

- **`src/tools/CodeExecutor.ts`** — uses `node-fetch` for both GET /files and POST /exec with **no timeout** on either
- File attachment priority: (1) `_injected_files` from `config.toolCall`, (2) fallback fetch from `/files/${session_id}?detail=full`
- **`src/tools/ProgrammaticToolCalling.ts`** — has `DEFAULT_TIMEOUT = 60000` (60s), but CodeExecutor does not
- Both tools use `HttpsProxyAgent` only if `PROXY` env var is set; otherwise default `http.globalAgent`

### Node.js Socket Timeout Behavior

- `axios` internally calls `req.setTimeout(timeout)` which delegates to `socket.setTimeout(timeout)` on the TCP socket
- `socket.setTimeout()` sets an **inactivity timer** — fires after N ms of no read/write activity
- The timeout is **NOT automatically cleared** when a request completes
- When the socket returns to `http.globalAgent`'s keep-alive pool, the timeout persists
- `node-fetch` (and any other client using the same agent) inherits the timeout when reusing the socket
- This is a well-known Node.js footgun: socket-level timeouts leak through keep-alive connection reuse

## Fix Applied

### `Connection: close` on GET /files responses

**File:** `src/api/files.py` — `list_files()` endpoint

Added `Connection: close` response header to force the client to close the TCP socket after each GET /files request. This prevents the poisoned socket (with inherited 5s timeout) from being reused for POST /exec.

```python
@router.get("/files/{session_id}")
async def list_files(session_id: str, response: Response, ...):
    # Prevent HTTP keep-alive socket reuse for this endpoint.
    # LibreChat's getSessionInfo() calls GET /files with a 5s axios timeout, which sets
    # socket.setTimeout(5000) on the underlying TCP socket. When that socket is reused
    # via keep-alive for the subsequent POST /exec (node-fetch, no timeout), the 5s
    # timeout persists and fires during long-running executions → "socket hang up".
    # Sending Connection: close forces a fresh socket for the next request.
    response.headers["Connection"] = "close"
    ...
```

### How This Fixes the Problem

With `Connection: close`:

```
BEFORE (broken):
  [socket A] → GET /files (axios, timeout:5000) → response → keep-alive
  [socket A] → GET /files (node-fetch) → response → keep-alive
  [socket A] → POST /exec (node-fetch) → 5s timeout fires → DISCONNECT

AFTER (fixed):
  [socket A] → GET /files (axios, timeout:5000) → response + Connection:close → CLOSED
  [socket B] → GET /files (node-fetch) → response + Connection:close → CLOSED
  [socket C] → POST /exec (node-fetch, fresh socket, NO inherited timeout) → SUCCESS
```

### Trade-offs

- **+** Directly eliminates the root cause (no poisoned socket reuse)
- **+** Minimal change (one header on one endpoint)
- **+** Zero risk to existing functionality
- **-** Each GET /files forces a new TCP connection (~1ms overhead within cluster, negligible)
- **-** Doesn't protect against other hypothetical timeout leaks from other endpoints

## Validation Plan

1. **Deploy** image with this fix
2. **Reproduce** with the controlled experiment from investigation5:
   - `time.sleep(10); print("done")` with a 2KB text file attachment
   - This previously failed at exactly 5.000s every time
3. **Expected result:** Execution completes at ~10s with no disconnect
4. **Verify in logs:**
   - GET /files responses should show `Connection: close` header
   - POST /exec should arrive on a different source port than GET /files
   - `client_disconnected: false` in exec completion log
   - Uvicorn access log present for POST /exec

## Upstream Fix Recommendation

The real bug is in the LibreChat/agents ecosystem. The proper fix should be filed as an issue:

**Option 1 (LibreChat):** Clear socket timeout after `getSessionInfo()` completes, or use a dedicated HTTP agent with short timeout for metadata requests so the socket pool doesn't leak timeouts to execution requests.

**Option 2 (agents):** Use a custom `http.Agent` with `keepAlive: false` for POST /exec requests in CodeExecutor.ts, or set an explicit long timeout (60s+) that overrides any inherited socket timeout.

**Option 3 (agents):** Set `agent: new http.Agent({ keepAlive: false })` on the fetch call to avoid socket reuse entirely.

## Previous Fixes on This Branch (Still Valid)

| Commit | Fix | Status |
|--------|-----|--------|
| `a5322f5` | Replace BaseHTTPMiddleware with pure ASGI | Correct improvement, not root cause |
| `b21969c` | Increase uvicorn keep-alive to 75s | Correct improvement, not root cause |
| `160e690` | Move MinIO response.read() into executor | Real bug fix, not root cause of 5s disconnect |
| `9d665ab` | Diagnostic logging (disconnect detection) | Provided the evidence that confirmed client-side disconnect |
| **NEW** | `Connection: close` on GET /files | **Root cause mitigation** |

## Open Items

1. **Deploy and validate** — the controlled experiment will definitively confirm
2. **File upstream issue** — LibreChat/agents should fix the socket timeout leak at the source
3. **Consider heartbeat streaming** — investigation4 proposed streaming whitespace before JSON response as a second layer of defense; this would protect against ANY client-side idle timeout, not just this specific one. Worth considering if other timeout sources emerge.
4. **Remove diagnostic logging** — once validated, the diagnostic logging from `9d665ab` can be simplified (keep the disconnect detection, remove the verbose tracing)
