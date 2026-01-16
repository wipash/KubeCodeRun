# syntax=docker/dockerfile:1.4
# Go execution environment with BuildKit optimizations.
FROM golang:1.23-alpine

ARG BUILD_DATE
ARG VERSION
ARG VCS_REF

LABEL org.opencontainers.image.title="Code Interpreter Go Environment" \
      org.opencontainers.image.description="Secure execution environment for Go code" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}"

# Install common tools
RUN apk add --no-cache \
    git \
    make \
    gcc \
    musl-dev

# Copy go.mod for pre-downloading
COPY requirements/go.mod /tmp/gosetup/go.mod

# Pre-download common Go packages with cache mount
RUN --mount=type=cache,target=/go/pkg/mod \
    cd /tmp/gosetup && \
    go mod download && \
    rm -rf /tmp/gosetup

# Create non-root user with UID/GID 1000 to match Kubernetes security context
RUN addgroup -g 1000 -S codeuser && \
    adduser -S codeuser -u 1000 -G codeuser

# Set working directory
WORKDIR /mnt/data

# Ensure ownership of working directory
RUN chown codeuser:codeuser /mnt/data

# Switch to non-root user
USER codeuser

# Set environment variables
ENV GO111MODULE=on \
    GOPROXY=https://proxy.golang.org,direct \
    GOSUMDB=sum.golang.org

# Default command with sanitized environment
ENTRYPOINT ["/usr/bin/env","-i","PATH=/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin","HOME=/tmp","TMPDIR=/tmp","GO111MODULE=on","GOPROXY=https://proxy.golang.org,direct","GOSUMDB=sum.golang.org","GOCACHE=/mnt/data/go-build"]
CMD ["go"]
