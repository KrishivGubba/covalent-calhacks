#!/bin/bash

echo "🧪 Testing Tab Completion Prediction Pipeline"
echo "=============================================="
echo ""

# Check if Ollama is running
echo "1️⃣  Checking Ollama status..."
if curl -s http://localhost:11434/api/tags --max-time 2 > /dev/null 2>&1; then
    echo "   ✅ Ollama is running"
    MODEL_COUNT=$(curl -s http://localhost:11434/api/tags | jq '.models | length' 2>/dev/null || echo "?")
    echo "   📊 Models available: $MODEL_COUNT"
else
    echo "   ❌ Ollama is not running!"
    echo "   Start it with: ollama serve"
    exit 1
fi

echo ""

# Check if graph.db exists
echo "2️⃣  Checking graph.db..."
GRAPH_DB="../context-engine/graph.db"
if [ -f "$GRAPH_DB" ]; then
    SIZE=$(ls -lh "$GRAPH_DB" | awk '{print $5}')
    echo "   ✅ graph.db exists ($SIZE)"

    # Count nodes in database
    NODE_COUNT=$(sqlite3 "$GRAPH_DB" "SELECT COUNT(*) FROM node_table;" 2>/dev/null || echo "?")
    echo "   📊 Nodes in graph: $NODE_COUNT"
else
    echo "   ⚠️  graph.db not found at $GRAPH_DB"
    echo "   Predictions will use fallback context"
fi

echo ""

# Clear predictions log
echo "3️⃣  Setting up monitoring..."
echo "   📝 Predictions will be logged to /tmp/predictions.log"
> /tmp/predictions.log
echo "   ✅ Log file cleared"

echo ""

# Build the project
echo "4️⃣  Building project..."
BUILD_OUTPUT=$(cargo build 2>&1)
if echo "$BUILD_OUTPUT" | grep -q "error\[E"; then
    echo "   ❌ Build failed!"
    echo "$BUILD_OUTPUT" | tail -20
    exit 1
else
    echo "   ✅ Build successful"
    WARNING_COUNT=$(echo "$BUILD_OUTPUT" | grep -c "warning:" || echo "0")
    echo "   ⚠️  Warnings: $WARNING_COUNT (non-critical)"
fi

echo ""

echo "5️⃣  Test instructions:"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   To test tab completion, run in another terminal:"
echo ""
echo "   Terminal 1: Monitor predictions"
echo "   $ tail -f /tmp/predictions.log"
echo ""
echo "   Terminal 2: Run the app"
echo "   $ cd src-tauri"
echo "   $ cargo run"
echo ""
echo "   or run the Tauri app:"
echo "   $ npm run tauri dev"
echo ""
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "✅ All checks passed! Ready to test predictions."
