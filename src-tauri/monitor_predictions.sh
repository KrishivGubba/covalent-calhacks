#!/bin/bash

# Color codes for terminal output
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GRAY='\033[0;90m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Clear screen and show header
clear
echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║          TAB COMPLETION PREDICTION MONITOR                     ║${NC}"
echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GRAY}Log file: /tmp/predictions.log${NC}"
echo -e "${GRAY}Press Ctrl+C to stop monitoring${NC}"
echo ""
echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
echo ""

# Create log file if it doesn't exist
touch /tmp/predictions.log

# Monitor the log file with nice formatting
tail -f /tmp/predictions.log | while read -r line; do
    # Extract timestamp
    if [[ $line =~ \[([0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2})\] ]]; then
        TIMESTAMP="${BASH_REMATCH[1]}"

        # Colorize based on cache level
        if [[ $line =~ L0-exact ]]; then
            ICON="⚡"
            COLOR="${GREEN}"
        elif [[ $line =~ L1-llm ]]; then
            ICON="💨"
            COLOR="${CYAN}"
        elif [[ $line =~ L2-graph ]]; then
            ICON="🔍"
            COLOR="${YELLOW}"
        else
            ICON="📝"
            COLOR="${NC}"
        fi

        # Print formatted line
        echo -e "${GRAY}[${TIMESTAMP}]${NC} ${ICON} ${COLOR}${line#*] }${NC}"
    else
        # Print line as-is if no timestamp
        echo -e "${GRAY}${line}${NC}"
    fi
done
