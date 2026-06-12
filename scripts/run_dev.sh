#!/usr/bin/env sh
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR" || exit 1
export PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
python -m ncepu_cloud_client.main
