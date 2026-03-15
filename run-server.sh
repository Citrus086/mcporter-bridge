#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"
cd "$SCRIPT_DIR"
"$SCRIPT_DIR/.venv/bin/python3" -m mcporter_bridge
