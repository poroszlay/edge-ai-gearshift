#!/usr/bin/env bash
# Source the pinned ESP-IDF export.sh first. Separate config/build per mode.
set -euo pipefail
mode=${1:-benchmark}
if [[ $# -gt 1 || ( $mode != benchmark && $mode != live ) ]]; then
    echo "Usage: $0 [benchmark|live]" >&2
    exit 2
fi
if [[ $(idf.py --version) != 'ESP-IDF v5.5.1' ]]; then
    echo 'Source unmodified ESP-IDF v5.5.1/export.sh first.' >&2
    exit 1
fi
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
build_dir="$project_dir/build/$mode"
defaults="$project_dir/sdkconfig.defaults"
if [[ $mode == live ]]; then defaults+=";$project_dir/sdkconfig.live"; fi
idf.py -C "$project_dir" -B "$build_dir" -DIDF_TARGET=esp32 \
    -DSDKCONFIG="$build_dir/sdkconfig" -DSDKCONFIG_DEFAULTS="$defaults" build
python -m esp_idf_size --format json -o "$build_dir/size.json" \
    "$build_dir/gearshift_measurement.map"
