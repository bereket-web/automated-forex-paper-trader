#!/usr/bin/env bash
set -euo pipefail
fx-paper ingest
fx-paper simulate --model histgb
