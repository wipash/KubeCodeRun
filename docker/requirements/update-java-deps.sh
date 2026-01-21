#!/usr/bin/env bash
# Update SHA-256 checksums for Java dependencies
# Usage: ./scripts/update-java-deps.sh
#
# This script reads requirements/java-deps.txt, fetches current checksums
# from Maven Central, and updates the file in place.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS_FILE="$SCRIPT_DIR/java-deps.txt"

if [[ ! -f "$DEPS_FILE" ]]; then
    echo "Error: $DEPS_FILE not found."
    exit 1
fi

echo "Updating Java dependency checksums..."

# Create temp file for output
TEMP_FILE=$(mktemp)
trap 'rm -f "$TEMP_FILE"' EXIT

while IFS= read -r line; do
    # Preserve comments and blank lines
    if [[ "$line" =~ ^# ]] || [[ -z "$line" ]]; then
        echo "$line" >> "$TEMP_FILE"
        continue
    fi

    # Parse URL (first field)
    url=$(echo "$line" | awk '{print $1}')
    filename=$(basename "$url")

    # Try to get SHA256 from Maven Central's .sha256 file
    sha=$(curl -sfL "${url}.sha256" 2>/dev/null | awk '{print $1}' || true)

    # If .sha256 file doesn't exist or is invalid, compute from JAR
    if [[ -z "$sha" ]] || [[ ${#sha} -ne 64 ]]; then
        echo "  Computing checksum for $filename..."
        sha=$(curl -sfL "$url" | sha256sum | awk '{print $1}')
    else
        echo "  Fetched checksum for $filename"
    fi

    echo "$url $sha" >> "$TEMP_FILE"
done < "$DEPS_FILE"

# Replace original file
mv "$TEMP_FILE" "$DEPS_FILE"
trap - EXIT

echo "Done. Updated $DEPS_FILE"
