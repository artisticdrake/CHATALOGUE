#!/bin/bash

# Get absolute path of this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Add src/ to PYTHONPATH so the 'chatalogue' package resolves
export PYTHONPATH="$SCRIPT_DIR/src"

# Run the GUI module
python3 -m chatalogue.chat_window
