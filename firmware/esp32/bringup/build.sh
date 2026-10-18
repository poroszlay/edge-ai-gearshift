#!/usr/bin/env bash
# Run after sourcing ESP-IDF v5.5.1/export.sh.
set -euo pipefail
if [[ $# != 1 || ( $1 != basic && $1 != inference ) ]]; then
  echo "Usage: $0 {basic|inference}" >&2
  exit 2
fi
if [[ $(idf.py --version) != 'ESP-IDF v5.5.1' ]]; then
  echo 'Source the unmodified ESP-IDF v5.5.1 export.sh first.' >&2
  exit 1
fi
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/$1" && pwd)
# Separate generated config and build directory per example. A fresh build
# uses sdkconfig.defaults; keep the generated sdkconfig with run evidence.
idf.py -C "$project_dir" -DIDF_TARGET=esp32 build
