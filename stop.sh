#!/bin/bash
CUR_PATH=$(dirname $(realpath "$0"))
PID_FILE="$CUR_PATH/pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Service stopped (PID: $PID)"
    else
        echo "Service is not running (stale PID file)"
    fi
    rm -f "$PID_FILE"
else
    echo "PID file not found. Service may not be running."
fi
