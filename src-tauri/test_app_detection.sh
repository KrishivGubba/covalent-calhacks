#!/bin/bash

# Test script to quickly verify app detection improvements
echo "🔍 Testing App Detection Improvements"
echo "======================================"

export COVALENT_DEBUG=1

echo "Current apps running:"
osascript -e 'tell application "System Events" to get bundle identifier of every application process whose background only is false' | tr ',' '\n' | head -10

echo ""
echo "Running quick detection test..."

# Run the monitor for 30 seconds and capture output
timeout 30s ./target/debug/context_monitor 2>&1 | grep -E "(🐛 App Debug|📱 App|🎯 Context|Bundle ID)" || echo "No debug output found"

echo ""
echo "Test complete!"