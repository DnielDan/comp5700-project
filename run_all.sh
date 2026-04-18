#!/usr/bin/env bash
set -e

# Runs the pipeline on all 9 required input combinations.
# Usage:        ./run_all.sh
# With binary:  USE_BINARY=1 ./run_all.sh

if [ "${USE_BINARY:-0}" = "1" ]; then
    CMD="./dist/comp5700-pipeline"
else
    CMD="python main.py"
fi

pairs=(
    "inputs/cis-r1.pdf inputs/cis-r1.pdf"
    "inputs/cis-r1.pdf inputs/cis-r2.pdf"
    "inputs/cis-r1.pdf inputs/cis-r3.pdf"
    "inputs/cis-r1.pdf inputs/cis-r4.pdf"
    "inputs/cis-r2.pdf inputs/cis-r2.pdf"
    "inputs/cis-r2.pdf inputs/cis-r3.pdf"
    "inputs/cis-r2.pdf inputs/cis-r4.pdf"
    "inputs/cis-r3.pdf inputs/cis-r3.pdf"
    "inputs/cis-r3.pdf inputs/cis-r4.pdf"
)

for p in "${pairs[@]}"; do
    echo "=== $p ==="
    $CMD $p
done