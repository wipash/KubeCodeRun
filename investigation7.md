# Socket Hang-Up Investigation - Phase 7

**Date:** 2026-02-10  
**Branch:** `hangup-fixes`  
**Current KCR HEAD:** `02ce52c` (includes `d1ae308`)  

## What was done in this phase

Read all prior investigation files (`investigation.md`, `investigation2.yaml`, `investigation3.md`, `investigation4.md`, `investigation5claude.md`) and then verified the client-side code paths directly from upstream GitHub source for:

- `danny-avila/LibreChat`
- `danny-avila/agents`

This phase focuses on proving whether the `~5s` disconnect is tied to the attachment path (`GET /files` before `POST /exec`).

## New Source-Backed Findings

## 1) LibreChat attachment path does a `GET /files` with `timeout: 5000`

Upstream file:

- `danny-avila/LibreChat` `api/server/services/Files/Code/process.js`

Confirmed logic:

- `getSessionInfo()` calls `GET {CODE_BASEURL}/files/{session_id}?detail=summary`
- Uses Axios request option `timeout: 5000`

Line evidence from fetched source:

- `process.js` lines `280-292`:
  - `method: 'get'`
  - `url: ${baseURL}/files/${session_id}`
  - `params: { detail: 'summary', ... }`
  - `timeout: 5000`

This exactly matches KCR access logs showing:

- `GET /files/{session_id}?detail=summary` before failing `POST /exec` calls.

## 2) `/exec` call in agents is `node-fetch` with no explicit timeout

Upstream file:

- `danny-avila/agents` `src/tools/CodeExecutor.ts`

Line evidence from fetched source:

- `CodeExecutor.ts` lines `181-196`:
  - `fetchOptions` for `POST /exec`
  - no timeout field
  - `await fetch(EXEC_ENDPOINT, fetchOptions)`

Same file also shows fallback file lookup via fetch:

- lines `140-153`:
  - `GET /files/{session_id}?detail=full`
  - no timeout field

## 3) LibreChat Axios instance does not define a custom keep-alive/timeout agent

Upstream file:

- `danny-avila/LibreChat` `packages/api/src/utils/axios.ts`

Line evidence:

- `createAxiosInstance()` (lines `66-90`) does `axios.create()`
- only optional proxy config is set
- no custom `httpAgent` / `httpsAgent` timeout settings

## 4) LibreChat Docker image uses Node 20

Upstream file:

- `danny-avila/LibreChat` `Dockerfile`

Line evidence:

- `FROM node:20-alpine AS node`

## 5) Axios timeout maps to socket timeout behavior (`req.setTimeout`)

Upstream file:

- `axios` `lib/adapters/http.js` (v1.8.4 inspected)

Line evidence:

- lines `629-650` show `if (config.timeout) ... req.setTimeout(timeout, ...)`
- comments in that block explicitly reference `"socket hang up"` behavior in slow responses

## Interpretation

The strongest working model now is:

1. Attachment flow triggers LibreChat `getSessionInfo()` calls to KCR `/files` with Axios `timeout: 5000`.
2. A reused keep-alive socket is then used for `POST /exec`.
3. Long-running `/exec` (>5s before response bytes) hits the carried socket timeout behavior and the client side tears down the connection.
4. KCR finishes execution successfully but logs:
   - `Client disconnected during request processing`
   - no uvicorn access log for `POST /exec`

This matches all observed `fail4.log` / `fail5.log` timing signatures (`~4.998s` / `~5.000s`) and the no-attachment success control (`success3.log`).

## KCR mitigation status

This repository already contains mitigation commit:

- `d1ae308` `fix: send Connection: close on GET /files to prevent socket hang-up`

Implementation:

- `src/api/files.py`:
  - `list_files(..., response: Response, ...)`
  - sets `response.headers["Connection"] = "close"`

This is designed to prevent socket reuse from `/files` to `/exec`.

## Validation to run next

Deploy image built from `hangup-fixes` HEAD (`02ce52c`) and repeat controlled matrix:

1. No attachment + `sleep(10)` (control)
2. 2KB attachment + `sleep(10)`
3. 45MB attachment + `sleep(10)`

Expected if mitigation works:

- no `socket hang up`
- no `client_disconnected=true` on KCR
- `POST /exec` has uvicorn access logs
- connection reuse signature should disappear for `/files -> /exec`

## If failures persist after deploying `d1ae308`

1. Capture request/response headers at KCR for `/files` and `/exec` (confirm `Connection: close` is observed by client path).
2. Capture packet trace to verify whether a new TCP connection is established for `POST /exec`.
3. If reuse still occurs despite `Connection: close`, fallback mitigation is streaming/heartbeat on `/exec` to emit early bytes before 5s.
