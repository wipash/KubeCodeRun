# REPL Server Documentation

This document describes the Python REPL (Read-Eval-Print Loop) server that enables sub-50ms Python execution.

## Overview

The REPL server is a Python process that runs inside Docker containers, keeping the Python interpreter warm with common libraries pre-imported. This eliminates the ~3 second Python startup overhead on each execution.

### Performance Impact

| Mode             | Simple Execution | Complex Execution |
| ---------------- | ---------------- | ----------------- |
| **With REPL**    | 20-40ms          | 50-200ms          |
| **Without REPL** | 3,000-4,000ms    | 3,500-5,000ms     |

**Improvement: ~100x faster for simple operations**

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Host (API Server)                               │
│                                                                             │
│   src/services/container/repl_executor.py                                   │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │  REPLExecutor                                                     │    │
│   │  - Communicates via Docker attach socket                          │    │
│   │  - Sends JSON requests                                            │    │
│   │  - Parses JSON responses                                          │    │
│   │  - Handles timeouts and errors                                    │    │
│   └───────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │ Docker attach socket
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Docker Container                                   │
│                                                                             │
│   docker/repl_server.py (PID 1)                                             │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │  REPL Server                                                      │    │
│   │  - Pre-imports: numpy, pandas, matplotlib, scipy, sklearn, etc.  │    │
│   │  - Maintains namespace across requests                            │    │
│   │  - Executes code in namespace                                     │    │
│   │  - Captures stdout, stderr                                        │    │
│   │  - Serializes state with cloudpickle + lz4                       │    │
│   │  - Returns JSON response                                          │    │
│   └───────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Files

| File               | Location                                  | Purpose                              |
| ------------------ | ----------------------------------------- | ------------------------------------ |
| `repl_server.py`   | `docker/repl_server.py`                   | In-container REPL server             |
| `repl_executor.py` | `src/services/container/repl_executor.py` | Host-side communication              |
| `entrypoint.sh`    | `docker/entrypoint.sh`                    | Mode-aware container startup         |
| `runner.py`        | `src/services/execution/runner.py`        | Routes to REPL or standard execution |

---

## Protocol Specification

### Communication Channel

The REPL uses Docker attach socket (not exec) for communication:

- **Attach socket**: Connects to container's stdin/stdout
- **JSON framing**: Messages delimited by special markers
- **Bidirectional**: Request in, response out

### Request Format

```json
{
  "code": "print('Hello, World!')",
  "state": "<base64-encoded-lz4-compressed-cloudpickle>",
  "capture_state": true
}
```

| Field           | Type    | Required | Description                     |
| --------------- | ------- | -------- | ------------------------------- |
| `code`          | string  | Yes      | Python code to execute          |
| `state`         | string  | No       | Previous session state (base64) |
| `capture_state` | boolean | No       | Whether to return state         |

### Response Format

```json
{
  "stdout": "Hello, World!\n",
  "stderr": "",
  "exit_code": 0,
  "state": "<base64-encoded-lz4-compressed-cloudpickle>",
  "files": ["output.png"],
  "error": null
}
```

| Field       | Type   | Description                             |
| ----------- | ------ | --------------------------------------- |
| `stdout`    | string | Captured standard output                |
| `stderr`    | string | Captured standard error                 |
| `exit_code` | int    | 0 for success, non-zero for error       |
| `state`     | string | Serialized namespace (if capture_state) |
| `files`     | array  | List of created files                   |
| `error`     | string | Error message if execution failed       |

### Delimiter Protocol

Messages are framed with special delimiters to handle partial reads:

```
>>> REQUEST_START <<<
{json request}
>>> REQUEST_END <<<

>>> RESPONSE_START <<<
{json response}
>>> RESPONSE_END <<<
```

---

## Pre-loaded Libraries

The REPL server pre-imports these libraries to eliminate import overhead:

### Data Science

```python
import numpy as np
import pandas as pd
from scipy import stats, optimize, interpolate
from sklearn import (
    linear_model, tree, ensemble, cluster,
    preprocessing, model_selection, metrics
)
import statsmodels.api as sm
```

### Visualization

```python
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
```

### Standard Library

```python
import json
import csv
import datetime
import collections
import itertools
import functools
import math
import random
import re
import os
import sys
```

### Notes

- Imports are done at container startup (during pool warmup)
- Import time is amortized across all requests to that container
- User can still import additional libraries in their code

---

## State Persistence Integration

The REPL server handles state serialization for the state persistence feature:

### State Capture

After code execution:

```python
# Filter namespace
namespace = {
    k: v for k, v in globals().items()
    if not k.startswith('_')
    and k not in BUILTIN_NAMES
    and not callable(getattr(v, '__module__', None))
}

# Serialize
state_bytes = cloudpickle.dumps(namespace)
compressed = lz4.frame.compress(state_bytes)
encoded = base64.b64encode(compressed).decode('utf-8')
```

### State Restoration

Before code execution:

```python
# Decode
compressed = base64.b64decode(encoded_state)
state_bytes = lz4.frame.decompress(compressed)
namespace = cloudpickle.loads(state_bytes)

# Inject into globals
globals().update(namespace)
```

### What's Excluded

These are not included in state:

- Names starting with `_` (private)
- Builtin functions and types
- Imported modules (must re-import)
- Generator objects
- Open file handles

---

## Configuration

### Environment Variables

| Variable                            | Default | Description                 |
| ----------------------------------- | ------- | --------------------------- |
| `REPL_ENABLED`                      | `true`  | Enable REPL mode for Python |
| `REPL_WARMUP_TIMEOUT_SECONDS`       | `15`    | Time to wait for REPL ready |
| `REPL_HEALTH_CHECK_TIMEOUT_SECONDS` | `5`     | Health check timeout        |

### Disabling REPL

To disable REPL mode:

```bash
REPL_ENABLED=false
```

When disabled:

- Python uses standard execution (docker exec)
- Startup overhead ~3 seconds per request
- State persistence still works (via file-based serialization)

---

## Container Lifecycle

### Startup Sequence

1. Container created with `repl_server.py` as entrypoint
2. REPL server initializes and pre-imports libraries (~10-15 seconds)
3. REPL server writes "ready" marker to stdout
4. Container pool marks container as available
5. Container waits for requests on stdin

### Request Processing

1. REPLExecutor sends JSON request via attach socket
2. REPL server reads until delimiter
3. REPL server executes code in namespace
4. REPL server captures output and state
5. REPL server sends JSON response
6. REPLExecutor parses response

### Container Destruction

After each request:

- Container is destroyed immediately
- No container reuse (fresh state each request)
- Pool replenishes in background

---

## Error Handling

### Timeout Handling

```python
# REPLExecutor
try:
    response = await asyncio.wait_for(
        self._execute(code, state),
        timeout=execution_timeout
    )
except asyncio.TimeoutError:
    # Container is killed, new container acquired for retry
    raise ExecutionTimeoutError("Execution timed out")
```

### Syntax Errors

Syntax errors are caught and returned in the response:

```json
{
  "stdout": "",
  "stderr": "SyntaxError: invalid syntax (line 1)",
  "exit_code": 1,
  "error": "SyntaxError: invalid syntax"
}
```

### Runtime Errors

Runtime errors include traceback:

```json
{
  "stdout": "",
  "stderr": "Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\nZeroDivisionError: division by zero",
  "exit_code": 1,
  "error": "ZeroDivisionError: division by zero"
}
```

### State Serialization Errors

If state cannot be serialized:

```json
{
  "stdout": "...",
  "stderr": "",
  "exit_code": 0,
  "state": null,
  "error": "State serialization failed: cannot pickle 'generator' object"
}
```

---

## Troubleshooting

### REPL Not Starting

1. **Check container logs**:

   ```bash
   docker logs <container_id>
   ```

2. **Check warmup timeout**:
   If libraries take too long to import, increase timeout:

   ```bash
   REPL_WARMUP_TIMEOUT_SECONDS=30
   ```

3. **Check memory**:
   REPL requires ~150MB for pre-imports. Ensure container has enough memory.

### High Latency

1. **Check attach socket health**:

   ```bash
   curl https://localhost/health/detailed | jq '.containers'
   ```

2. **Check for blocking operations**:
   User code with network or disk I/O can block the REPL.

3. **Check state size**:
   Large state causes serialization overhead. Keep state < 1MB for best performance.

### State Not Persisting

1. **Verify REPL mode**:

   ```bash
   echo $REPL_ENABLED  # Should be "true"
   ```

2. **Check for unsupported types**:
   Some objects cannot be pickled. Check logs for serialization errors.

3. **Check state size**:
   If state exceeds `STATE_MAX_SIZE_MB`, it won't be saved.

---

## Development

### Testing REPL Locally

```bash
# Build Python image
cd docker && ./build-images.sh -l python

# Run container with REPL
docker run -it --rm code-interp-python:latest

# In container, REPL server starts automatically
# Send test request via stdin
```

### Debugging REPL Server

Enable debug output in container:

```python
# In repl_server.py
DEBUG = True  # Logs all requests/responses to stderr
```

### Modifying Pre-imports

Edit `docker/repl_server.py`:

```python
# Add new imports to PRELOAD_MODULES list
PRELOAD_MODULES = [
    "numpy",
    "pandas",
    # Add your module here
    "your_module",
]
```

Remember to rebuild the Docker image after changes.

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [STATE_PERSISTENCE.md](STATE_PERSISTENCE.md) - State persistence details
- [PERFORMANCE.md](PERFORMANCE.md) - Performance tuning
- [CONFIGURATION.md](CONFIGURATION.md) - All configuration options
