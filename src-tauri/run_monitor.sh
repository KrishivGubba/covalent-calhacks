#!/bin/bash

# Covalent Context Monitor Runner
# This script runs the context monitoring binary

echo "🚀 Starting Covalent Context Monitor..."
echo "Make sure you have the required permissions:"
echo "  - Screen Recording (System Preferences > Security & Privacy > Screen Recording)"
echo "  - Accessibility (System Preferences > Security & Privacy > Accessibility)"
echo ""

# Check if we're in the right directory
if [ ! -f "Cargo.toml" ]; then
    echo "❌ Error: Please run this script from the src-tauri directory"
    exit 1
fi

# Build and run the monitor
echo "🔨 Building the context monitor..."
cargo build --bin context_monitor

if [ $? -eq 0 ]; then
    echo "✅ Build successful! Starting monitor..."
    echo ""
    
    # Set debug mode if requested
    if [ "$1" = "--debug" ]; then
        echo "🐛 Debug mode enabled - JSON output will be shown"
        export COVALENT_DEBUG=1
    fi
    
    # Run the monitor
    cargo run --bin context_monitor
else
    echo "❌ Build failed! Please check the errors above."
    exit 1
fi