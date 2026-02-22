# Socket Hang Up Investigation

## Problem
After deploying the `dev` branch (incorporating three squash merges: pool-fix, uvicorn-timeout, capture-job-files), most code execution calls from LibreChat fails with:
```
Error: Execution error: request to http://kubecoderun.default.svc.cluster.local:8000/exec failed, reason: socket hang up
```

The LibreChat conversation involves a ~46MB CSV file (`FENZ_Incident_Data_2017_2025_Combined_Cleaned_part_1.csv`).

Calls with no attachments generally succeed. This was an issue before the recent commits but seems to be more prevalent now, especially with larger files, although this is just a gut feel.

## Key Evidence

### KCR server logs show SUCCESS (fail1.log)
- Two POST /exec requests processed successfully, both returning status 200
- First exec: request_id=k0DEoBEv, duration_ms=6001.14, exit_code=0
- Second exec: request_id=0Nx2Ux8b, duration_ms=5730.97, exit_code=0
- Both used warm pool pods (pool-py-f7bcd955, pool-py-8dd2e036)

### Critical clue: Missing uvicorn access logs
- GET /files requests have uvicorn access logs: `INFO: 10.244.0.244:43566 - "GET /files/... HTTP/1.1" 200 OK`
- POST /exec requests do **NOT** have uvicorn access logs, only middleware JSON logs
- Uvicorn writes its access log in the protocol handler AFTER the response body is fully sent to the socket
- **Missing access log means the response body was never fully written to the TCP socket**

### No client-side timeout
- LibreChat's code execution tool is in `danny-avila/agents` repo: `src/tools/CodeExecutor.ts`
- URL: https://raw.githubusercontent.com/danny-avila/agents/refs/heads/main/src/tools/CodeExecutor.ts
- Uses `node-fetch` (not axios) with **NO timeout, NO AbortController, NO AbortSignal**
- The error format `request to ${url} failed, reason: ${reason}` is node-fetch's `FetchError`
- "socket hang up" in Node.js means: TCP connection closed before HTTP response headers were received

### Other LibreChat timeouts (from DeepWiki analysis)
- GET /files/{session_id} (session info): 5000ms timeout (axios) — `api/server/services/Files/Code/process.js`
- GET /download (file download): 15000ms timeout (axios) — `api/server/services/Files/Code/crud.js`
- POST /exec: NO timeout (node-fetch) — `danny-avila/agents` CodeExecutor.ts

## Three Commits Analyzed

### 1. pool-fix (4356eb5)
- Event-based replenishment (`asyncio.Event` instead of `sleep(5)` polling)
- Concurrent pod creation via `asyncio.gather`
- Stale pod entry skipping in acquire (retry loop with deadline)
- Pod deletion moved outside lock in `release()`
- Health check interval: 30s → 15s, failure threshold: 3 → 2
- **Does NOT change the execution pipeline or response flow**

### 2. uvicorn-timeout (649377c)
- Added `timeout_keep_alive=75` to uvicorn (was default 5s)
- Added `api_timeout_keep_alive` setting with default 75
- **Only affects idle connection lifetime, should NOT affect active requests**

### 3. capture-job-files (f379e6b)
- JobExecutor now returns `JobHandle` from `execute_with_job()`
- `destroy_pod()` handles both PodHandle and JobHandle
- File detection logic restructured but **functionally identical for pool-hit requests**
- For pool-hit with mounted files, `_detect_generated_files()` was already being called before this change

## Current Theory: MetricsMiddleware using BaseHTTPMiddleware

### The middleware stack (src/main.py:260-262)
```python
app.add_middleware(MetricsMiddleware)       # OUTERMOST - uses BaseHTTPMiddleware!
app.add_middleware(RequestLoggingMiddleware) # pure ASGI
app.add_middleware(SecurityMiddleware)       # pure ASGI
```

### Why BaseHTTPMiddleware is suspicious
`MetricsMiddleware` (src/middleware/metrics.py) extends Starlette's `BaseHTTPMiddleware`. This is a well-known source of issues:

1. **BaseHTTPMiddleware spawns a background task** to run the inner ASGI app, then communicates response data via `anyio.MemoryObjectStream`
2. The inner app's response is **captured and re-sent** through a new `StreamingResponse`
3. This means the response goes through TWO send paths: inner ASGI chain → memory stream → BaseHTTPMiddleware → uvicorn
4. For long-running requests (6 seconds for POST /exec), the background task and memory stream interaction may fail silently
5. **BaseHTTPMiddleware does not properly detect client disconnection**
6. If the re-send via StreamingResponse fails, uvicorn never writes the response body → no access log → client gets "socket hang up"

### Why this explains the symptoms
- GET /files (2ms): Fast enough that BaseHTTPMiddleware works fine
- POST /exec (6000ms): Long-running request where BaseHTTPMiddleware's background task + memory stream may fail
- Middleware logs 200: The inner ASGI chain (RequestLoggingMiddleware) captures status from `http.response.start` which passes through the memory stream successfully
- No uvicorn access log: The response body is never fully sent to the socket by BaseHTTPMiddleware's outer StreamingResponse
- "socket hang up": Node-fetch sees the connection closed without receiving HTTP response headers

### Additional concern: SecurityMiddleware header handling
In `src/middleware/security.py:83`, the security middleware converts ASGI headers to a dict and back:
```python
headers = dict(message.get("headers", []))
# ... add security headers ...
message["headers"] = list(headers.items())
```
This is generally fine but could theoretically drop duplicate headers. Worth verifying but unlikely to be the root cause.

## Recommended Fix

### Priority 1: Convert MetricsMiddleware to pure ASGI
Replace `BaseHTTPMiddleware` with a pure ASGI middleware implementation (matching the pattern used by RequestLoggingMiddleware and SecurityMiddleware). This eliminates the background task + memory stream mechanism that likely causes the response delivery failure.

### Priority 2: Move cleanup to truly background
In `src/services/orchestrator.py:596-657`, the `_cleanup()` method awaits event publishing and metrics recording BEFORE the response is returned:
```python
response = self._build_response(ctx)
await self._cleanup(ctx)  # blocks on event_bus.publish + metrics
return response
```
Move ALL cleanup (including event publishing and metrics) to a fire-and-forget background task, or use FastAPI's `BackgroundTasks` to run cleanup after the response is sent.

### Priority 3: Add diagnostic logging
Add logging to detect when the client disconnects before the response is sent. This would help confirm the theory and diagnose any remaining issues.

## Files Involved

| File | Role |
|------|------|
| `src/middleware/metrics.py` | **PRIMARY SUSPECT** - MetricsMiddleware uses BaseHTTPMiddleware |
| `src/middleware/security.py` | SecurityMiddleware (pure ASGI) + RequestLoggingMiddleware (pure ASGI) |
| `src/main.py` | Middleware registration order (lines 260-262), uvicorn config |
| `src/api/exec.py` | POST /exec endpoint |
| `src/services/orchestrator.py` | Execution pipeline, cleanup blocks before response return |
| `src/services/execution/runner.py` | Code execution runner |
| `src/services/kubernetes/pool.py` | Pod pool management |
| `src/services/kubernetes/manager.py` | Kubernetes manager |
| `src/config/__init__.py` | Settings including `api_timeout_keep_alive` |
| `helm-deployments/kubecoderun/values.yaml` | Default Helm values |
| `helm-deployments/kubecoderun/templates/configmap.yaml` | ConfigMap template |

## User's Deployment Config
- Location: `/home/sean/homelab/kubernetes/apps/default/librechat/kubecoderun/helmrelease.yaml`
- Image: `ghcr.io/wipash/kubecoderun-api:2.1.3-dev1`
- Sidecar: `ghcr.io/wipash/kubecoderun-sidecar:2.1.3-dev1`
- Python poolSize: 2
- API pod: 512Mi memory limit
- `maxFileSizeMb: 250`, `maxTotalFileSizeMb: 500`
- `debug: true`, `logLevel: "DEBUG"`
- LibreChat connects via: `http://kubecoderun.default.svc.cluster.local:8000`

## Execution Timeline (from fail1.log)

```
02:14:05.282 - POST /exec request received (k0DEoBEv)
02:14:05.733 - File mounted (46MB from MinIO, 450ms)
02:14:05.733 - Pod acquired from pool (pool-py-f7bcd955)
02:14:05.xxx - File uploaded to sidecar (POST /files, 46MB)
02:14:05.xxx - Code execution started (POST /execute)
02:14:10.xxx - Code execution completed on sidecar (exit_code=0)
02:14:10.xxx - File detection (GET /files to sidecar)
02:14:11.277 - Execution completed (5522ms execution time)
02:14:11.278 - Cleanup: event publishing + metrics
02:14:11.282 - Middleware logs "Request processed" status=200, duration=6001ms
               *** NO uvicorn access log for this request ***
02:14:11.303 - Background: pod destroyed
```

## What Has NOT Been Investigated
- Exact Starlette version (check if BaseHTTPMiddleware bugs were fixed)
- Whether the Kubernetes CNI or service mesh adds timeouts
- Whether Node.js 19+ global agent keepAlive behavior interacts with uvicorn's timeout_keep_alive=75
- Packet-level analysis of the TCP connection (would definitively show who closes the connection)
- Benefit of additional logging in KCR
