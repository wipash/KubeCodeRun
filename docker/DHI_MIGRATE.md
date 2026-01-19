# Docker Hardened Images (DHI) Migration Guide

This guide documents lessons learned migrating KubeCodeRun images to Docker Hardened Images (dhi.io).

## Overview

DHI images are security-focused, minimal container images. Key differences from standard images:

| Aspect | Standard Images | DHI Images |
|--------|-----------------|------------|
| Package manager | Available | Only in `-dev` variants |
| Shell | Available | Only in `-dev` variants |
| Default user | root | Non-root (UID 65532) |
| Python location | `/usr/local/` | `/opt/python/` |
| Node.js location | `/usr/local/` | `/opt/nodejs/node-v<version>/` |
| Go location | `/usr/local/go/` | `/usr/local/go/` (same) |

## Image Variants

- `dhi.io/<image>:<tag>` - Minimal runtime (no shell, no package manager)
- `dhi.io/<image>:<tag>-dev` - Development variant (has shell, apt, build tools)

**Which to use for final stage:**
- **Interpreted languages** (Python, Node, Go, PHP, R): Use minimal (no `-dev`)
- **Compiled languages** (Rust, C, Java, Fortran, D): Use `-dev` (need shell for compile && run)

Note: `-dev` images default to root user, so add `USER 65532` at the end.

## Multi-Stage Build Pattern

DHI typically uses a 3-stage build pattern for minimal images:

```dockerfile
# Stage 1: Build/compile with -dev variant
FROM dhi.io/python:3.14-debian13-dev AS builder
# Install build deps, compile packages

# Stage 2: Install runtime dependencies with -dev variant
FROM dhi.io/python:3.14-debian13-dev AS runtime-deps
# Install runtime libraries that will be copied to final image

# Stage 3: Minimal runtime image
FROM dhi.io/python:3.14-debian13 AS final
# Copy artifacts from builder and runtime-deps
```

**For compiled languages using `-dev` final stage**, you can simplify to 2 stages:

```dockerfile
# Stage 1: Build dependencies
FROM dhi.io/eclipse-temurin:25-jdk-debian13-dev AS builder
# Download/verify JARs, etc.

# Stage 2: Final (uses -dev because we need shell for javac && java)
FROM dhi.io/eclipse-temurin:25-jdk-debian13-dev AS final
COPY --from=builder /build/lib /opt/java/lib
RUN mkdir -p /mnt/data && chown 65532:65532 /mnt/data
USER 65532
# ... rest of config
```

## Key Issues and Solutions

### 1. Missing `update-rc.d` (x11-common fails)

**Error:**
```
/var/lib/dpkg/info/x11-common.postinst: line 13: update-rc.d: command not found
```

**Solution:** Install `init-system-helpers` before packages that need X11:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends init-system-helpers && \
    # Now install packages that depend on x11-common
    apt-get install -y libcairo2-dev ...
```

### 2. Service startup failures during package install

**Error:** dpkg postinst scripts trying to start services

**Solution:** Create a policy-rc.d that blocks service starts:
```dockerfile
RUN echo 'exit 101' > /usr/sbin/policy-rc.d && \
    chmod +x /usr/sbin/policy-rc.d && \
    apt-get install -y ...
```

### 3. Python installed in non-standard location

**DHI Python paths:**
- Binary: `/opt/python/bin/python`
- Site-packages: `/opt/python/lib/python3.14/site-packages`
- NOT `/usr/local/` like standard images

**Solution:** Update COPY commands and PATH:
```dockerfile
COPY --from=builder /opt/python/lib/python3.14/site-packages /opt/python/lib/python3.14/site-packages
COPY --from=builder /opt/python/bin /opt/python/bin

ENV PATH=/opt/python/bin:/usr/bin:/bin
```

### 4. Multi-arch library paths

When copying libraries for both amd64 and arm64, create empty directories first:
```dockerfile
RUN mkdir -p /usr/lib/x86_64-linux-gnu /usr/lib/aarch64-linux-gnu && \
    apt-get install -y ...
```

Then copy both (one will be empty depending on build arch):
```dockerfile
COPY --from=runtime-deps /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu
COPY --from=runtime-deps /usr/lib/aarch64-linux-gnu /usr/lib/aarch64-linux-gnu
```

### 5. Version-agnostic symlinks for versioned paths

DHI images often install languages in versioned directories:
- Node.js: `/opt/nodejs/node-v<version>/`
- PHP: `/opt/php-<major.minor>/`

This causes problems for ENTRYPOINT (exec form doesn't expand variables).

**Solution:** Create a version-agnostic symlink during build:
```dockerfile
# Node.js example
RUN ln -sf /opt/nodejs/node-* /opt/node

# PHP example
RUN ln -sf /opt/php-${PHP_MAJOR} /opt/php

# Then use the symlink in ENTRYPOINT
ENTRYPOINT ["/usr/bin/env", "-i", \
    "PATH=/opt/php/bin:/usr/bin:/bin", \
    ...]
```

Copy both the versioned directory and symlink to final stage:
```dockerfile
COPY --from=builder /opt/php-${PHP_MAJOR}/lib/php/extensions/ /opt/php-${PHP_MAJOR}/lib/php/extensions/
COPY --from=builder /opt/php /opt/php
```

### 6. No shell in final image - use env -i ENTRYPOINT pattern

The minimal DHI image has no shell. Copy `/usr/bin/env` and `/usr/bin/sleep` from a
`-dev` stage and use the `env -i` ENTRYPOINT pattern for ALL DHI images:

```dockerfile
# Copy env for ENTRYPOINT, sleep for default CMD
COPY --from=runtime-deps /usr/bin/env /usr/bin/sleep /usr/bin/

# Sanitized environment via env -i
ENTRYPOINT ["/usr/bin/env", "-i", \
    "PATH=/opt/python/bin:/usr/bin:/bin", \
    "HOME=/tmp", \
    "TMPDIR=/tmp", \
    "PYTHONUNBUFFERED=1", \
    "PYTHONPATH=/mnt/data"]
CMD ["sleep", "infinity"]
```

**Why this pattern is required:**
- The sidecar uses `nsenter -m` to enter the container's mount namespace
- With mount namespace only, the spawned process inherits the SIDECAR's environment
- The sidecar reads `/proc/<pid>/environ` to get the container's environment
- This only works if the container was started with `env -i` setting explicit env vars
- Using `ENV` directive alone won't populate `/proc/<pid>/environ` correctly

### 7. Shell-less execution with wrapper scripts

When a language requires multi-step execution (compile then run), you can't use
shell command chaining (`&&`) in a no-shell image. Use a wrapper script instead.

**Example: TypeScript runner script (`/opt/scripts/ts-runner.js`):**
```javascript
const { execFileSync } = require('child_process');
const path = require('path');

const file = process.argv[2];
const outDir = '/tmp';
const outFile = path.join(outDir, path.basename(file, '.ts') + '.js');

// Compile TypeScript
execFileSync('tsc', [file, '--outDir', outDir, '--module', 'commonjs'], {
  stdio: 'inherit'
});

// Run the compiled JavaScript
require(outFile);
```

**Usage:** `node /opt/scripts/ts-runner.js /mnt/data/code.ts`

This avoids the need for shell command chaining like `tsc file.ts && node file.js`.

### 8. Non-root user (UID 65532)

DHI images run as non-root by default. Create directories with correct ownership:
```dockerfile
# In a -dev stage where you have shell access:
RUN mkdir -p /mnt/data && chown 65532:65532 /mnt/data

# Then copy to final:
COPY --from=runtime-deps /mnt/data /mnt/data
```

### 9. Debian 13 package name changes

Some packages have different names in Debian 13 (trixie):
- `libssl3` → `libssl3t64`
- `libpng16-16` → `libpng16-16t64`

### 10. Go module cache ownership

**Problem:** Go modules downloaded in the builder stage are owned by root. The non-root
user can't download transitive dependencies at runtime.

**Error:**
```
mkdir /go/pkg/mod/cache/download/github.com/...: permission denied
```

**Solution:** Use `--chown` when copying the module cache:
```dockerfile
# Copy pre-downloaded Go modules with correct ownership
COPY --from=builder --chown=65532:65532 /go/pkg/mod /go/pkg/mod
```

Also create the GOCACHE directory with correct ownership:
```dockerfile
# In runtime-deps stage
RUN mkdir -p /mnt/data/go-build && chown 65532:65532 /mnt/data/go-build
```

### 11. BuildKit cache mounts don't persist

**Problem:** Using `--mount=type=cache` for Go modules means they won't be in the final image.

**Error:**
```
COPY --from=builder /go/pkg/mod /go/pkg/mod
# ERROR: "/go/pkg/mod": not found
```

**Solution:** Don't use cache mounts if you need the artifacts in the final image:
```dockerfile
# DON'T do this if you need modules in final image:
RUN --mount=type=cache,target=/go/pkg/mod go mod download

# DO this instead:
RUN go mod download
```

Cache mounts are ephemeral and only available during the RUN command. They speed up
rebuilds but don't persist in image layers.

### 12. Alpine to Debian package equivalents

When migrating from Alpine to Debian-based DHI images:

| Alpine | Debian |
|--------|--------|
| `apk add` | `apt-get install` |
| `musl-dev` | `libc6-dev` |
| `--no-cache` | `rm -rf /var/lib/apt/lists/*` |
| `adduser -D` | `useradd` (but use DHI's UID 65532) |

## Packages to Avoid

These packages cause significant complexity with X11 dependencies:
- `libcairo2-dev` / `libcairo2` (requires x11-common chain)
- `libpango1.0-dev` / `libpango-1.0-0` (requires x11-common chain)
- `tcl8.6-dev` / `tk8.6` (X11 dependencies)
- `pygame` (requires SDL2)

Consider whether these are truly needed. Alternatives:
- matplotlib works without Cairo (has multiple backends)
- Pillow handles most image operations
- PDF generation works with reportlab (no Cairo needed)

## Dockerfile Template

```dockerfile
# syntax=docker/dockerfile:1
FROM dhi.io/python:3.14-debian13-dev AS builder

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    gcc g++ make pkg-config python3-dev \
    # Add your -dev libraries here
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

################################
FROM dhi.io/python:3.14-debian13-dev AS runtime-deps

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN mkdir -p /usr/lib/x86_64-linux-gnu /usr/lib/aarch64-linux-gnu /mnt/data && \
    chown 65532:65532 /mnt/data && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    # Add runtime libraries here (no -dev packages)
    && rm -rf /var/lib/apt/lists/*

################################
FROM dhi.io/python:3.14-debian13 AS final

# Copy runtime libraries
COPY --from=runtime-deps /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu
COPY --from=runtime-deps /usr/lib/aarch64-linux-gnu /usr/lib/aarch64-linux-gnu

# Copy Python packages (note: /opt/python, not /usr/local)
COPY --from=builder /opt/python/lib/python3.14/site-packages /opt/python/lib/python3.14/site-packages
COPY --from=builder /opt/python/bin /opt/python/bin

# Copy /usr/bin/env for sidecar execution, sleep for default CMD
COPY --from=runtime-deps /usr/bin/env /usr/bin/sleep /usr/bin/

# Copy data directory with correct ownership
COPY --from=runtime-deps /mnt/data /mnt/data

WORKDIR /mnt/data

# Sanitized environment via env -i (required for sidecar runtime env detection)
ENTRYPOINT ["/usr/bin/env", "-i", \
    "PATH=/opt/python/bin:/usr/bin:/bin", \
    "HOME=/tmp", \
    "TMPDIR=/tmp", \
    "PYTHONUNBUFFERED=1"]
CMD ["sleep", "infinity"]
```

## Sidecar Updates

The sidecar (`docker/sidecar/main.py`) uses runtime environment detection, so **no sidecar
code changes are needed** when migrating a new language to DHI.

### How it works

1. Sidecar finds the main container's PID via `/proc` scanning
2. Reads environment from `/proc/<pid>/environ`
3. Executes code using `/usr/bin/env -i` with the runtime-detected environment

### Requirements for this to work

1. **Container must have `/usr/bin/env`** - copy from `-dev` stage
2. **Container must use `env -i` ENTRYPOINT** - so `/proc/<pid>/environ` has the right vars
3. **For interpreted languages** (Python, Node, Go, PHP, R): sidecar uses direct execution
4. **For compiled languages** (Rust, C, Java, etc.): sidecar uses `sh -c` for compile && run

### Testing a migrated image

```bash
# Test the image directly (simulates what sidecar does)
tmpdir=$(mktemp -d) && chmod 777 "$tmpdir"
echo 'print("Hello!")' > "$tmpdir/code.py"

docker run --rm \
    -v "$tmpdir:/mnt/data" \
    -w /mnt/data \
    --entrypoint /usr/bin/env \
    your-image:latest \
    -i PATH=/opt/python/bin:/usr/bin:/bin python code.py

rm -rf "$tmpdir"
```

Or use the test scripts:
```bash
# Quick Docker-only test
./scripts/test-images.sh -l py -l js -l go

# Full Kubernetes test with production security settings
./scripts/test-k8s-sidecar.sh -l py -l js -l go
```

### 13. Missing `sleep` binary for default CMD

**Problem:** Minimal DHI images don't have `sleep`, so `CMD ["sleep", "infinity"]` fails:
```
exec: "sleep": executable file not found in $PATH
```

**Solution:** Copy `sleep` from the `-dev` stage alongside `env`:
```dockerfile
# Copy env for ENTRYPOINT, sleep for default CMD
COPY --from=runtime-deps /usr/bin/env /usr/bin/sleep /usr/bin/
```

**Why `sleep infinity`?** The main container needs to stay alive so the sidecar can:
1. Find it via `/proc` scanning
2. Use `nsenter` to enter its mount namespace
3. Execute code in the container's filesystem context

### 14. Use `kcr-` prefix for local image names

**Problem:** Building images with generic names like `python:latest` or `nodejs:latest`
can conflict with official Docker Hub images and cause confusion.

**Solution:** Use a project-specific prefix for local development:
```bash
# build-images.sh uses PREFIX="kcr" by default
./scripts/build-images.sh python  # builds kcr-python:latest

# When pushing to a registry, use -r flag (overrides prefix)
./scripts/build-images.sh -r ghcr.io/user/kubecoderun python
# builds ghcr.io/user/kubecoderun-python:latest
```

All test scripts (`test-images.sh`, `test-k8s-sidecar.sh`) use the same prefix.

### 15. Testing in Kubernetes requires production security settings

**Problem:** Testing images with `docker run` doesn't validate the full sidecar execution
flow with Kubernetes security contexts (seccomp, capabilities, non-root).

**Solution:** Use `test-k8s-sidecar.sh` which deploys pods with the same security settings
as production:
```bash
# Test in local K8s cluster (defaults to docker-desktop context)
./scripts/test-k8s-sidecar.sh -l py

# Test all languages
./scripts/test-k8s-sidecar.sh

# Keep pods for debugging
./scripts/test-k8s-sidecar.sh -l py --keep-pods -v
```

The script creates pods with:
- `shareProcessNamespace: true` (for nsenter)
- `seccompProfile: RuntimeDefault`
- Non-root user (UID 65532)
- Sidecar capabilities: `SYS_PTRACE`, `SYS_ADMIN`, `SYS_CHROOT`
- `allowPrivilegeEscalation: true` for sidecar (file capabilities)

This catches issues that `docker run` testing misses.

### 16. Version ARGs for complex builds

When a Dockerfile references the version in multiple places (source downloads, paths, etc.),
use ARGs for single-source-of-truth version management:

```dockerfile
# PHP example - version used in wget URL and paths
ARG PHP_VERSION=8.4.17
ARG PHP_MAJOR=8.4
ARG DEBIAN_VERSION=debian13

FROM dhi.io/php:${PHP_VERSION}-${DEBIAN_VERSION}-dev AS builder
ARG PHP_VERSION
ARG PHP_MAJOR

ENV PHP_HOME=/opt/php-${PHP_MAJOR}

# Version used in source download
RUN wget -q "https://www.php.net/distributions/php-${PHP_VERSION}.tar.xz" ...
```

**When to use:** Only when version appears in multiple places beyond the base image tag
(e.g., source URLs, install paths). For simple images where version only appears in the
FROM line, hardcoding is fine.

**Upgrading:**
```bash
docker build --build-arg PHP_VERSION=8.4.18 -f docker/php.Dockerfile .
```

## Registry Authentication

DHI images require authentication:

**GitHub Actions:**
```yaml
- uses: docker/login-action@v3
  with:
    registry: dhi.io
    username: ${{ vars.DHI_USERNAME }}
    password: ${{ secrets.DHI_PASSWORD }}
```

**Local:**
```bash
export DHI_USERNAME=your-username
export DHI_PASSWORD=your-password
echo "$DHI_PASSWORD" | docker login dhi.io -u "$DHI_USERNAME" --password-stdin
```

## Run tests during migration
```bash
just build-images  # All languages
just build-images php

just test-images  # All languages
just test-images -l php

just test-k8s  # All languages
just test-k8s -l php
```

## References

- [DHI Documentation](https://docs.docker.com/dhi/)
- [DHI Usage Guide](https://docs.docker.com/dhi/how-to/use/)
- [DHI Troubleshooting](https://docs.docker.com/dhi/troubleshoot/)
