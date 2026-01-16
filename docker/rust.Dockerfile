# syntax=docker/dockerfile:1.4
# Rust execution environment with BuildKit optimizations
FROM rust:1.92-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a temporary project to pre-compile and cache crates
WORKDIR /tmp/rust-cache

# Copy Cargo.toml for crate caching
COPY requirements/rust-Cargo.toml Cargo.toml

# Create minimal src/main.rs (cargo init would fail since Cargo.toml exists)
RUN mkdir -p src && echo 'fn main() {}' > src/main.rs

# Fetch crate dependencies into cache
# cargo fetch downloads dependencies without compiling, which is faster and
# more reliable for cache warming (no system library dependencies needed)
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    cargo fetch

# Clean up the temporary project but keep the cargo cache
WORKDIR /
RUN rm -rf /tmp/rust-cache

# Create non-root user with UID/GID 1000 to match Kubernetes security context
RUN groupadd -g 1000 codeuser && \
    useradd -r -u 1000 -g codeuser codeuser

# Set working directory and ensure ownership
WORKDIR /mnt/data
RUN chown -R codeuser:codeuser /mnt/data

# Switch to non-root user
USER codeuser

# Set environment variables
ENV CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:$PATH

# Default command with sanitized environment
ENTRYPOINT ["/usr/bin/env","-i","PATH=/usr/local/cargo/bin:/usr/local/bin:/usr/bin:/bin","HOME=/tmp","TMPDIR=/tmp","CARGO_HOME=/usr/local/cargo","RUSTUP_HOME=/usr/local/rustup"]
CMD ["rustc", "--version"]
