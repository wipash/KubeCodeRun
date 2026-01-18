#!/usr/bin/env bash
# Test code execution in all KubeCodeRun Docker images
#
# Usage: ./scripts/test-images.sh [OPTIONS]
#
# Options:
#   -t, --tag TAG        Image tag to test (default: latest)
#   -r, --registry REG   Registry prefix (e.g., aronmuon/kubecoderun)
#   -l, --language LANG  Test only specified language (can repeat)
#   -v, --verbose        Show full output from each test
#   -h, --help           Show this help message

set -euo pipefail

# Defaults
TAG="latest"
REGISTRY=""
VERBOSE=false
SPECIFIC_LANGS=()

# Expected output for all tests
EXPECTED_OUTPUT="Hello, KubeCodeRun!"

# Test code for each language
declare -A TEST_CODE
TEST_CODE[py]='print("Hello, KubeCodeRun!")'
TEST_CODE[js]='console.log("Hello, KubeCodeRun!");'
TEST_CODE[ts]='console.log("Hello, KubeCodeRun!");'
TEST_CODE[go]='package main

import "fmt"

func main() {
    fmt.Println("Hello, KubeCodeRun!")
}'
TEST_CODE[java]='public class Code {
    public static void main(String[] args) {
        System.out.println("Hello, KubeCodeRun!");
    }
}'
TEST_CODE[c]='#include <stdio.h>

int main() {
    printf("Hello, KubeCodeRun!\n");
    return 0;
}'
TEST_CODE[cpp]='#include <iostream>

int main() {
    std::cout << "Hello, KubeCodeRun!" << std::endl;
    return 0;
}'
TEST_CODE[php]='<?php
echo "Hello, KubeCodeRun!\n";'
TEST_CODE[rs]='fn main() {
    println!("Hello, KubeCodeRun!");
}'
TEST_CODE[r]='cat("Hello, KubeCodeRun!\n")'
TEST_CODE[f90]='program hello
    print *, "Hello, KubeCodeRun!"
end program hello'
TEST_CODE[d]='import std.stdio;

void main() {
    writeln("Hello, KubeCodeRun!");
}'

# Language configurations
# Format: lang_code:image_name:execution_command
# All languages now use stdin - code is piped in and written to file inside container
# This is how the sidecar works
declare -A LANG_CONFIG
LANG_CONFIG[py]="python:python3 -"
LANG_CONFIG[js]="nodejs:node"
LANG_CONFIG[ts]="nodejs:cat > code.ts && tsc code.ts --outDir . --module commonjs --target ES2019 && node code.js"
LANG_CONFIG[go]="go:cat > code.go && go build -o code code.go && ./code"
LANG_CONFIG[java]="java:cat > Code.java && javac Code.java && java Code"
LANG_CONFIG[c]="c-cpp:cat > code.c && gcc -o code code.c && ./code"
LANG_CONFIG[cpp]="c-cpp:cat > code.cpp && g++ -o code code.cpp && ./code"
LANG_CONFIG[php]="php:php"
LANG_CONFIG[rs]="rust:cat > code.rs && rustc code.rs -o code && ./code"
LANG_CONFIG[r]="r:Rscript /dev/stdin"
LANG_CONFIG[f90]="fortran:cat > code.f90 && gfortran -o code code.f90 && ./code"
LANG_CONFIG[d]="d:cat > code.d && ldc2 code.d -of=code && ./code"

# Language display names
declare -A LANG_NAMES
LANG_NAMES[py]="Python"
LANG_NAMES[js]="JavaScript"
LANG_NAMES[ts]="TypeScript"
LANG_NAMES[go]="Go"
LANG_NAMES[java]="Java"
LANG_NAMES[c]="C"
LANG_NAMES[cpp]="C++"
LANG_NAMES[php]="PHP"
LANG_NAMES[rs]="Rust"
LANG_NAMES[r]="R"
LANG_NAMES[f90]="Fortran"
LANG_NAMES[d]="D"

usage() {
    head -n 12 "$0" | tail -n 10 | sed 's/^# //'
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--tag)
                TAG="$2"
                shift 2
                ;;
            -r|--registry)
                REGISTRY="$2"
                shift 2
                ;;
            -l|--language)
                SPECIFIC_LANGS+=("$2")
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

get_full_image_name() {
    local image_name="$1"
    if [[ -n "$REGISTRY" ]]; then
        echo "${REGISTRY}-${image_name}:${TAG}"
    else
        echo "${image_name}:${TAG}"
    fi
}

test_language() {
    local lang="$1"
    local config="${LANG_CONFIG[$lang]}"
    local name="${LANG_NAMES[$lang]}"
    local code="${TEST_CODE[$lang]}"

    # Parse config (format: image_name:exec_cmd)
    IFS=':' read -r image_name exec_cmd <<< "$config"
    local full_image
    full_image=$(get_full_image_name "$image_name")

    printf "%-12s %-20s " "[$lang]" "$name"

    # Check if image exists
    if ! docker image inspect "$full_image" &>/dev/null; then
        echo "SKIP (image not found: $full_image)"
        return 2
    fi

    local output
    local exit_code=0

    # Execute via stdin - code is piped in and written to file inside container
    # This is how the sidecar works
    output=$(echo "$code" | docker run --rm -i \
        -w /mnt/data \
        "$full_image" \
        sh -c "$exec_cmd" 2>&1) || exit_code=$?

    # Normalize output (trim whitespace, handle Fortran's leading space)
    local normalized_output
    normalized_output=$(echo "$output" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | head -1)

    if [[ $exit_code -ne 0 ]]; then
        echo "FAIL (exit code: $exit_code)"
        if [[ "$VERBOSE" == true ]]; then
            echo "  Output: $output"
        fi
        return 1
    elif [[ "$normalized_output" != "$EXPECTED_OUTPUT" ]]; then
        echo "FAIL (output mismatch)"
        if [[ "$VERBOSE" == true ]]; then
            echo "  Expected: '$EXPECTED_OUTPUT'"
            echo "  Got:      '$normalized_output'"
        fi
        return 1
    else
        echo "PASS"
        if [[ "$VERBOSE" == true ]]; then
            echo "  Output: $normalized_output"
        fi
        return 0
    fi
}

main() {
    parse_args "$@"

    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║          KubeCodeRun Docker Image Tester                 ║"
    echo "╠══════════════════════════════════════════════════════════╣"
    echo "║  Tag:      ${TAG}"
    if [[ -n "$REGISTRY" ]]; then
        echo "║  Registry: ${REGISTRY}"
    fi
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    # Determine which languages to test
    local langs_to_test
    if [[ ${#SPECIFIC_LANGS[@]} -gt 0 ]]; then
        langs_to_test=("${SPECIFIC_LANGS[@]}")
    else
        langs_to_test=(py js ts go java c cpp php rs r f90 d)
    fi

    local passed=0
    local failed=0
    local skipped=0
    local failed_langs=()

    echo "Running tests..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for lang in "${langs_to_test[@]}"; do
        if [[ -z "${LANG_CONFIG[$lang]:-}" ]]; then
            echo "Unknown language: $lang"
            continue
        fi

        local result=0
        test_language "$lang" || result=$?

        case $result in
            0) passed=$((passed + 1)) ;;
            1) failed=$((failed + 1)); failed_langs+=("$lang") ;;
            2) skipped=$((skipped + 1)) ;;
        esac
    done

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Summary
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║                     Test Summary                         ║"
    echo "╠══════════════════════════════════════════════════════════╣"
    echo "║  Passed:   ${passed}"
    echo "║  Failed:   ${failed}"
    echo "║  Skipped:  ${skipped}"
    echo "╚══════════════════════════════════════════════════════════╝"

    if [[ ${#failed_langs[@]} -gt 0 ]]; then
        echo ""
        echo "Failed languages:"
        for lang in "${failed_langs[@]}"; do
            echo "  - $lang (${LANG_NAMES[$lang]})"
        done
        exit 1
    fi

    if [[ $passed -gt 0 ]]; then
        echo ""
        echo "All tested images executed code successfully!"
    fi
}

main "$@"
