# Socket Hang-Up Investigation - Phase 3

## Current Status

Branch: `hangup-fixes`
Version tested: `2.1.3.dev2`
Date: 2026-02-10

Three prior fixes deployed (pure ASGI middleware, 75s keep-alive, fire-and-forget cleanup). Two new commits added:
- `9d665ab` - Diagnostic logging in MetricsMiddleware and exec endpoint
- `160e690` - Fix blocking `response.read()` in MinIO file downloads

## Updated Understanding of the Problem

**The failure is intermittent.** Key observations:
- Fails with 46MB files (consistently?)
- Fails with 1MB files **sometimes** (not always)
- Succeeds with very small files (a few KB) even under rapid concurrent load (10 calls)
- Succeeds when no files are attached

This rules out file size as the sole cause. The presence of any file attachment increases failure probability, with larger files making it more likely. This points to a **timing-dependent race condition** rather than a hard threshold.

## The Smoking Gun (unchanged from Phase 2)

In `fail2.log`, POST /exec requests complete through ALL middleware layers (status 200 in RequestLoggingMiddleware) but produce **no uvicorn access log**. GET /files requests on the same pod DO produce uvicorn access logs.

This means the response successfully traverses the entire middleware chain but uvicorn fails to write it to the TCP socket. In uvicorn's httptools protocol, `transport.write()` checks `if self.transport.is_closing(): return` and silently drops the data.

## Timeline (from fail2.log)

```
03:46:55.709  POST /exec received by KCR
03:46:55.711  Session lookup (Redis) - fast
~03:46:56.0   File download from MinIO (~46MB) - BLOCKS EVENT LOOP (bug, now fixed)
03:46:56.169  Starting code execution
~03:46:56-57  46MB file upload to sidecar via httpx POST /files
~03:47:00     *** TCP CONNECTION CLOSED (by unknown cause) ***
~03:47:00-02  Code executes in sidecar (pandas read_csv)
03:47:02.438  Execution completed, response ready
03:47:02.439  Middleware logs status=200 - but uvicorn silently drops response (transport closing)
              NO uvicorn access log appears
```

LibreChat sees "socket hang up" at ~03:47:00 NZDT (= 03:47:00 UTC), approximately 2 seconds BEFORE KCR finishes processing. The TCP connection lived for ~5 seconds before being closed.

## Bug Fixed: Blocking Event Loop During MinIO Downloads

`src/services/file.py` `get_file_content()` had a blocking I/O bug:

```python
# BEFORE (broken): response.read() blocks the event loop
response = await loop.run_in_executor(None, self.minio_client.get_object, ...)
content = response.read()      # <-- BLOCKS main thread!
response.close()               # <-- BLOCKS main thread!
response.release_conn()        # <-- BLOCKS main thread!

# AFTER (fixed): entire download runs in executor
def _download() -> bytes:
    response = self.minio_client.get_object(self.bucket_name, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
content = await loop.run_in_executor(None, _download)
```

`get_object()` was correctly in the executor, but `response.read()` (which does the actual network I/O to read the file body) ran on the main event loop thread. For any file, this blocks all concurrent async activity including uvicorn's protocol handling. For 46MB this could block for seconds; for 1MB it might block for 10-100ms.

### Why this might not be THE root cause

Blocking the event loop doesn't directly cause TCP connections to close. The kernel's TCP stack operates independently - it will continue responding to TCP keepalive probes, managing window sizes, etc. even while the application's event loop is frozen.

However, it could **contribute** to the problem by:
1. Creating a window where uvicorn can't process incoming ASGI events
2. Delaying response delivery, extending the time window for other issues to occur
3. Potentially interfering with uvicorn's internal connection state management when the event loop resumes

### Why intermittent failures with 1MB files matter

If it were purely about event loop blocking duration, 1MB files should rarely fail (< 100ms block time on a local network). The intermittent nature with small files suggests either:
- A race condition that file operations make more likely (but don't guarantee)
- A transient issue in the infrastructure (MinIO, Kubernetes networking, Redis)
- Something about the request lifecycle when files are involved that's different from file-less requests

## What's Different When Files Are Attached

The execution path with files vs. without files:

| Step | No Files | With Files |
|------|----------|------------|
| Session lookup | Redis call | Redis call |
| File info lookup | Skipped | Redis call per file |
| **File download** | **Skipped** | **MinIO download (was blocking, now fixed)** |
| Pool acquire | Same | Same |
| **File upload to sidecar** | **Skipped** | **httpx POST /files (30s timeout, async)** |
| Execute | Same | Same |
| File list from sidecar | Same | Same |

The two extra steps when files are attached:
1. MinIO download - now runs in executor (fixed), but still adds latency
2. Sidecar file upload - httpx POST with 30s timeout, sends file content as multipart

## Diagnostic Logging Added

### MetricsMiddleware (outermost ASGI middleware)

- **receive_wrapper**: Monitors for `http.disconnect` events, logs when client disconnects during processing with elapsed time
- **send_wrapper**: Tracks `response_body_sent` flag, wraps `await send(message)` in try/except to catch and log send failures
- **finally block**: Warns if `response_status` was set (headers sent) but `response_body_sent` is False (body never confirmed sent)

### exec.py endpoint

- Checks `await http_request.is_disconnected()` after orchestrator returns
- Logs warning if client disconnected before response could be sent
- Adds `client_disconnected` field to the completion log

### Expected diagnostic scenarios

**Scenario A: Client disconnects first**
```
"Client disconnected during request processing" (receive_wrapper got http.disconnect)
"Client disconnected before response could be sent" (exec.py is_disconnected check)
Possibly: "Response headers sent but body not confirmed"
```
Interpretation: Something on the client side (LibreChat or network) is closing the connection.

**Scenario B: send() throws an exception**
```
"Failed to send response to client" with error details
```
Interpretation: uvicorn or the transport layer actively rejects the write.

**Scenario C: Silent drop (most likely based on current evidence)**
```
"Response headers sent but body not confirmed" WITHOUT any send error or disconnect log
```
Interpretation: The transport entered closing state silently. The `http.disconnect` event may or may not have been received depending on when in the ASGI lifecycle the close occurred.

## Theories (Ranked by Confidence)

### 1. Connection closed by something outside KCR's application layer (MEDIUM-HIGH)

The ~5 second timing is very specific. It's not a standard timeout value for any obvious component. But "socket hang up" in Node.js means the **server** (KCR) closed the connection, not the client (LibreChat). So something in the KCR pod's stack (kernel, uvicorn, or process) is sending TCP FIN or RST.

Possible sub-causes:
- uvicorn bug triggered by event loop contention
- Kernel TCP stack issue under memory pressure
- Kubernetes networking rule change mid-connection

### 2. uvicorn httptools transport race condition (MEDIUM)

uvicorn's httptools protocol implementation may have a race condition where:
1. The transport enters a closing state (for reasons not fully understood)
2. When the response is ready, `transport.write()` sees `is_closing()=True` and silently drops
3. The connection effectively hangs from the client's perspective until TCP timeout

This matches the evidence: middleware sees status=200, but no uvicorn access log. The access log is written AFTER the response body is sent to the transport.

### 3. Blocking event loop creating a timing window (MEDIUM)

The `response.read()` blocking call (now fixed) freezes the event loop. During this freeze:
- If uvicorn's protocol receives a TCP FIN from anywhere, it can't process it until the event loop resumes
- When the event loop resumes, uvicorn may process the connection close before the response can be sent
- This would be more likely with larger files (longer freeze) but could happen intermittently with small files

### 4. Shared httpx client interference (LOW-MEDIUM)

The PodPool uses a shared `httpx.AsyncClient` (10s default timeout) for:
- Health checks (every 30s, 5s timeout)
- File uploads (30s timeout)
- Code execution (timeout+10s)

If a health check and a file upload happen concurrently through the same client, and the health check fails/times out, could it affect the file upload connection? httpx should handle this via separate connections, but connection pool limits could potentially cause queueing.

### 5. LibreChat or agent framework timeout (LOW)

Despite node-fetch having no timeout, there could be a timeout at a higher level (agent framework, tool execution timeout). However, "socket hang up" specifically means the server closed the connection, not a client-side abort. If LibreChat aborted, we'd see "request aborted" or "AbortError", not "socket hang up".

## Recommended Next Steps

1. **Deploy diagnostic build** - Build image with commits `9d665ab` + `160e690`, deploy, reproduce with large file, collect logs
2. **Test with curl** - Bypass LibreChat entirely, call POST /exec directly from within the cluster to isolate whether the issue is in KCR or the network path
3. **Monitor pod events** - `kubectl get events --field-selector involvedObject.name=<pod> -w` during reproduction to catch probe failures or endpoint changes
4. **TCP capture** - If diagnostics don't reveal the cause, capture TCP traffic on the KCR pod during reproduction: `kubectl debug -it <pod> --image=nicolaka/netshoot -- tcpdump -i eth0 port 8000 -w /tmp/capture.pcap`
5. **Check uvicorn issues** - Search uvicorn GitHub for issues related to silent response drops or transport closing unexpectedly

## Files Modified on This Branch

| File | Change | Commit |
|------|--------|--------|
| `src/middleware/metrics.py` | Pure ASGI conversion | `a5322f5` |
| `src/middleware/metrics.py` | Diagnostic logging (disconnect, send errors, body tracking) | `9d665ab` |
| `src/api/exec.py` | Diagnostic logging (disconnect check after execution) | `9d665ab` |
| `src/services/file.py` | Fix blocking `response.read()` in MinIO downloads | `160e690` |
| `src/main.py` | 75s keep-alive timeout | `b21969c` |
| `src/services/orchestrator.py` | Fire-and-forget cleanup | earlier |

## Open Questions

1. **What exactly sends the TCP FIN/RST?** The diagnostic logging should answer whether it's a client disconnect, a send error, or a silent transport close.
2. **Why ~5 seconds?** Is 5 seconds a coincidence or a specific timeout value somewhere we haven't found?
3. **Does the blocking I/O fix resolve it?** The fix is correct regardless, but it's unclear if it's the root cause given that 1MB files also fail intermittently.
4. **Is there a uvicorn bug?** Versions: uvicorn 0.40.0, httptools 0.7.1, starlette 0.50.0.
5. **What does a direct curl test show?** If curl works reliably, the issue is in the LibreChat→KCR interaction specifically.
