#!/usr/bin/env bash
# One reset, one identified UART run. Source ESP-IDF export.sh first.
set -euo pipefail
if [[ $# != 3 || ( $1 != live && $1 != benchmark && $1 != quality ) ]]; then
    echo "Usage: $0 {live|benchmark|quality} OUTPUT_DIRECTORY WINDOWS.jsonl" >&2
    exit 2
fi
run_mode=$1
output_directory=$2
input_path=$3
serial_port=${GEARSHIFT_PORT:-/dev/ttyUSB0}
if [[ -e $output_directory ]]; then
    echo 'Output directory already exists; never overwrite run evidence.' >&2
    exit 1
fi
mkdir -p -- "$output_directory"
model_id=$(python3 -c 'import json; print(json.load(open("models/mlp-v2/freeze.json"))["model_id"])')
# The identified ESP32-D0WD-V3 / 4 MiB target is documented with build evidence.
# read_mac resets the panel; allow boot to finish before opening the protocol.
python -m esptool --chip esp32 --port "$serial_port" read_mac > "$output_directory/reset.log" 2>&1
python3 -c 'import time; time.sleep(1)'
options=(--mode "$run_mode")
if [[ $run_mode == quality ]]; then
    options=(--mode benchmark --quality)
fi
python3 -m gearshift.client --serial "$serial_port" --baud 921600 --timeout 120 \
    --model-id "$model_id" "${options[@]}" --input "$input_path" \
    --capture-prefix "$output_directory/wire" --output "$output_directory/events.jsonl" \
    > "$output_directory/client.log" 2>&1
