#!/bin/bash

echo "🧪 Testing Qwen Prompts with New Settings"
echo "=========================================="
echo ""

# Test function
test_completion() {
    local input="$1"
    local expected="$2"

    echo -n "Testing: '$input' → "

    result=$(curl -s http://localhost:11434/api/generate -d "{
        \"model\": \"qwen2.5-coder:3b\",
        \"prompt\": \"git status\nnpm run dev\ncd src\n${input}\",
        \"stream\": false,
        \"options\": {
            \"num_predict\": 15,
            \"temperature\": 0.01,
            \"top_p\": 0.2,
            \"top_k\": 5,
            \"stop\": [\"\n\", \" It \", \" This \", \" is \"]
        }
    }" | jq -r '.response' 2>/dev/null)

    # Clean up result
    result=$(echo "$result" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/`//g')

    if [[ -z "$result" ]]; then
        echo "❌ No output"
    elif [[ "$result" == *"It looks"* ]] || [[ "$result" == *"This is"* ]]; then
        echo "❌ Explanation: '$result'"
    elif [[ ${#result} -gt 50 ]]; then
        echo "⚠️  Too long (${#result} chars): '${result:0:50}...'"
    else
        echo "✅ '$result'"
    fi
}

# Test cases
echo "Terminal Commands:"
echo "----------------"
test_completion "git st" "atus"
test_completion "npm run " "dev"
test_completion "npm run tau" "ri dev"
test_completion "cd sr" "c"
test_completion "cargo bu" "ild"
test_completion "ls -l" "a"

echo ""
echo "Code Completions:"
echo "----------------"

# Code test
result=$(curl -s http://localhost:11434/api/generate -d '{
    "model": "qwen2.5-coder:3b",
    "prompt": "function add(a, b) {\n    return a",
    "stream": false,
    "options": {
        "num_predict": 5,
        "temperature": 0.01,
        "top_p": 0.2,
        "stop": ["\n", ";"]
    }
}' | jq -r '.response' 2>/dev/null)

echo "Code: 'return a' → '$(echo $result | xargs)'"

echo ""
echo "Performance:"
echo "----------------"

# Measure latency
start=$(date +%s%N)
curl -s http://localhost:11434/api/generate -d '{
    "model": "qwen2.5-coder:3b",
    "prompt": "git status\nnpm run dev\ncd src\ngit st",
    "stream": false,
    "options": {
        "num_predict": 15,
        "temperature": 0.01,
        "top_p": 0.2,
        "stop": ["\n"]
    }
}' > /dev/null 2>&1
end=$(date +%s%N)

latency=$(( (end - start) / 1000000 ))
echo "Latency: ${latency}ms"

if [ $latency -lt 500 ]; then
    echo "✅ Fast (<500ms)"
elif [ $latency -lt 1000 ]; then
    echo "⚠️  Medium (500-1000ms)"
else
    echo "❌ Slow (>1000ms)"
fi

echo ""
echo "✅ Test complete!"
