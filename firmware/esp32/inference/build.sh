#!/usr/bin/env bash
set -euo pipefail
if [[ $(idf.py --version) != 'ESP-IDF v5.5.1' ]]; then
    echo 'Source ESP-IDF v5.5.1/export.sh first.' >&2
    exit 1
fi
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
idf.py -C "$project_dir" -DIDF_TARGET=esp32 reconfigure build
