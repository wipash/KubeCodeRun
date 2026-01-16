# syntax=docker/dockerfile:1.4
# Node.js execution environment with BuildKit optimizations.
FROM node:25-alpine

ARG BUILD_DATE
ARG VERSION
ARG VCS_REF

LABEL org.opencontainers.image.title="Code Interpreter Node.js Environment" \
      org.opencontainers.image.description="Secure execution environment for JavaScript/TypeScript code" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}"

# Install common build tools
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    git

# Copy package list
COPY requirements/nodejs.txt /tmp/nodejs.txt

# Install packages with cache mount
RUN --mount=type=cache,target=/root/.npm \
    grep -vE '^(#|$)' /tmp/nodejs.txt | xargs npm install -g

# Clean up
RUN rm -f /tmp/nodejs.txt

# Create non-root user with UID/GID 1000 to match Kubernetes security context
# Handle case where UID/GID 1000 already exists in base image (e.g., 'node' user)
RUN getent group 1000 >/dev/null || addgroup -g 1000 -S codeuser; \
    getent passwd 1000 >/dev/null || adduser -S codeuser -u 1000 -G "$(getent group 1000 | cut -d: -f1)"

# Set working directory
WORKDIR /mnt/data

# Ensure ownership of working directory
RUN chown -R 1000:1000 /mnt/data

# Switch to non-root user (use UID to work regardless of username)
USER 1000

# Set environment variables
ENV NODE_ENV=sandbox \
    NODE_PATH=/usr/local/lib/node_modules

# Default command with sanitized environment
ENTRYPOINT ["/usr/bin/env","-i","PATH=/usr/local/bin:/usr/bin:/bin","HOME=/tmp","TMPDIR=/tmp","NODE_ENV=sandbox","NODE_PATH=/usr/local/lib/node_modules"]
CMD ["node"]
