# Claude API Integration Guide

## Overview

The Tauri app now uses Claude AI to generate natural, context-aware descriptions of user activity. The system runs a synchronous loop every 2 seconds that:

1. **Collects Context** - Gathers app info, DOM data, activity metrics
2. **Analyzes with Claude** - Sends metadata to Claude API for intelligent description generation
3. **Screenshot Fallback** - If text-based analysis fails, sends screenshot to Claude Vision
4. **Sends to Flask** - Stores the generated description and full context data

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Tauri App Start                    │
└───────────────────┬─────────────────────────────────┘
                    ↓
        ┌───────────────────────┐
        │ Start Flask Server     │
        └───────────┬─────────────┘
                    ↓
        ┌───────────────────────┐
        │ Start Context Loop     │
        │ (every 2 seconds)      │
        └───────────┬─────────────┘
                    ↓
        ┌─────────────────────────────────┐
        │ 1. Collect Context               │
        │    - App info                    │
        │    - DOM data (if browser)       │
        │    - Activity metrics            │
        │    - Accessibility data          │
        └───────────┬───────────────────────┘
                    ↓
        ┌─────────────────────────────────┐
        │ 2. Analyze with Claude API       │
        │    - Generate description        │
        │    - Detect workflow stage       │
        │    - Identify key changes        │
        └───────────┬───────────────────────┘
                    ↓
         ┌──────────┴──────────┐
         │  Success?            │
         └────┬───────────┬─────┘
              │ No        │ Yes
              ↓           ↓
    ┌──────────────┐   ┌─────────────────────┐
    │ 3. Screenshot │   │ 4. Send to Flask   │
    │    + Claude    │   │    /screen         │
    │    Vision      │   │    endpoint        │
    └────────┬───────┘   └─────────┬───────────┘
             ↓                     ↓
             └──────────┬──────────┘
                        ↓
            ┌────────────────────────┐
            │ 5. Store in graph.db   │
            └────────────────────────┘
```

## Setup

### 1. Set Claude API Key

You need an Anthropic API key to use Claude. Get one at [https://console.anthropic.com/](https://console.anthropic.com/)

Set the environment variable:

```bash
# Add to your ~/.zshrc or ~/.bashrc
export ANTHROPIC_API_KEY="sk-ant-..."

# Or alternatively:
export CLAUDE_API_KEY="sk-ant-..."

# Reload shell
source ~/.zshrc
```

### 2. Install Dependencies

Already handled in `Cargo.toml`:
- `reqwest` with `json` and `multipart` features
- `base64` for image encoding
- `serde`/`serde_json` for JSON handling

### 3. Run the App

```bash
cd /Users/hem/Downloads/covalent-calhacks
npm run tauri dev
```

## How It Works

### Context Collection Loop

Located in: `src-tauri/src/screen_context/context_loop.rs`

The loop runs **synchronously** - each iteration completes fully before the next begins:

```rust
pub async fn run(&mut self) -> Result<()> {
    while self.running {
        // 1. Collect context
        let raw_context = self.collector.collect_context().await?;
        
        // 2. Analyze with Claude
        let analysis = self.analyzer.analyze_context(&raw_context, None, None).await?;
        
        // 3. Send to Flask
        self.send_to_flask(&analysis).await?;
        
        // Wait 2 seconds before next iteration
        sleep(self.interval).await;
    }
}
```

**Key Features:**
- ✅ No queue buildup - waits for completion
- ✅ Configurable interval (default: 2 seconds)
- ✅ Comprehensive error logging
- ✅ Iteration tracking

### Claude Integration

Located in: `src-tauri/src/screen_context/claude_client.rs`

The client handles all Claude API interactions:

```rust
pub async fn generate_description(&self, system_prompt: &str, user_prompt: &str) -> Result<String>
pub async fn generate_description_with_image(&self, system_prompt: &str, user_prompt: &str, screenshot_base64: &str) -> Result<String>
```

**Features:**
- Uses Claude Sonnet 4 (latest model)
- 60-second timeout
- Automatic error handling
- Image support with base64 encoding

### LLM Analyzer with Claude

Located in: `src-tauri/src/screen_context/llm_analyzer.rs`

The analyzer orchestrates Claude calls:

1. **Text-First Approach**: Tries to generate description from metadata alone
2. **Screenshot Fallback**: If text fails, captures screenshot and sends to Claude Vision
3. **Metadata Building**: Constructs comprehensive context string including:
   - App name, bundle ID, window title
   - Browser data (URL, page title, visible text)
   - IDE data (current file, workspace)
   - Activity metrics
   - Recent changes

### Flask API Integration

Located in: `src-tauri/src/screen_context/context_api.rs`

Sends the complete `ContextAnalysisOutput` to Flask:

```rust
pub async fn send_analysis_output(&self, analysis: &ContextAnalysisOutput) -> Result<ContextResponse>
```

**Sent Data:**
```json
{
  "description": "User is developing a Flask integration in VSCode, editing context_api.rs. High activity level with frequent code changes...",
  "data": "{...full ContextAnalysisOutput JSON...}"
}
```

## Configuration

### Adjust Collection Interval

In `src-tauri/src/lib.rs`:

```rust
// Set interval to 2 seconds (default)
context_loop.set_interval(2);

// Or change to 1 second for more frequent updates
context_loop.set_interval(1);

// Or 5 seconds for less frequent updates
context_loop.set_interval(5);
```

### Change Claude Model

In `src-tauri/src/screen_context/claude_client.rs`:

```rust
const CLAUDE_MODEL: &str = "claude-sonnet-4-20250514"; // Current model

// Or use a different model:
// const CLAUDE_MODEL: &str = "claude-3-5-sonnet-20241022";
```

### Adjust Max Tokens

In `claude_client.rs`:

```rust
let request = ClaudeRequest {
    model: CLAUDE_MODEL.to_string(),
    max_tokens: 1024, // Increase for longer descriptions
    messages,
};
```

## Output Format

### ContextAnalysisOutput

The complete analysis sent to Flask:

```rust
pub struct ContextAnalysisOutput {
    pub app_name: String,
    pub description: String,        // Claude-generated, max 200 words
    pub context_type: ContextType,
    pub confidence: f32,
    pub time_elapsed_seconds: u64,
    pub session_duration_seconds: u64,
    pub activity_level: String,
    pub changes_detected: bool,
    pub key_changes: Vec<String>,
    pub workflow_stage: String,
    pub interaction_pattern: String,
    pub automation_opportunities: Vec<String>,
    pub timestamp: DateTime<Utc>,
    pub metadata: AnalysisMetadata,
}
```

### Example Description

Claude-generated description example:

```
User is actively developing a Flask API integration in VSCode. Currently editing
the context_api.rs file which handles sending context data to the Flask server.
The user appears to be in the implementation phase, having recently added error
handling and response parsing logic. High activity level with frequent code
modifications and test runs. The workflow suggests they are iterating quickly
on the API client implementation.
```

## Monitoring

### Console Output

When running, you'll see:

```
🚀 Starting synchronous context collection loop (interval: 2s)

━━━ Iteration 1 ━━━
  📊 Collecting context...
  🤖 Analyzing with Claude...
  📤 Sending to Flask API...
  ✓ App: VSCode
  ✓ Description: User is developing a Flask integration...
  ✓ Flask response: Screen data received (UUID: abc-123)
✅ Iteration 1 completed in 3.2s

━━━ Iteration 2 ━━━
  ...
```

### Error Handling

Errors are logged but don't stop the loop:

```
⚠️  Claude description failed: API timeout, using fallback
⚠️  Text-based Claude failed: rate limit, trying with screenshot...
✗  Flask API error: Connection refused
```

### Flask Logs

Check Flask server logs:

```bash
tail -f server/flask_server.log
```

## Troubleshooting

### Claude API Issues

**Problem**: "Claude client not available"
```
⚠️  Warning: Claude API key not found. Set ANTHROPIC_API_KEY or CLAUDE_API_KEY environment variable.
```

**Solution**:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Restart the app
```

---

**Problem**: "Claude API returned error status 429: rate limit"

**Solution**: Claude has rate limits. Either:
- Wait a few seconds (loop will retry next iteration)
- Increase the interval: `context_loop.set_interval(5)`
- Upgrade your Claude API plan

---

**Problem**: "Failed to capture screenshot"

**Solution**: 
- Check screen recording permissions: System Settings → Privacy & Security → Screen Recording
- Enable for your terminal/IDE

### Flask Connection Issues

**Problem**: "Flask API error: Connection refused"

**Solution**:
```bash
# Check if Flask is running
curl http://127.0.0.1:5001/health

# If not, check logs
cat server/flask_server.log

# Restart Flask manually
cd server
python3 app.py
```

### Performance Issues

**Problem**: Loop running too slowly

**Causes**:
- Claude API latency (1-3 seconds)
- Screenshot capture (if fallback is triggered)
- Heavy context collection

**Solutions**:
- Increase interval to reduce frequency
- Check network connectivity
- Monitor Claude API response times

## Testing

### Manual Test

1. Start the app:
```bash
npm run tauri dev
```

2. Check console output for successful iterations

3. Verify Flask is receiving data:
```bash
# Check Flask health
curl http://127.0.0.1:5001/health

# Check database
sqlite3 context-engine/graph.db "SELECT COUNT(*) FROM nodes;"
```

### Test Claude Directly

Create a test script:

```rust
#[tokio::test]
async fn test_claude_description() {
    let client = ClaudeClient::new().unwrap();
    
    let result = client.generate_description(
        "Generate a concise description",
        "User is working in VSCode, editing Rust code"
    ).await;
    
    assert!(result.is_ok());
    println!("Description: {}", result.unwrap());
}
```

## Best Practices

1. **API Key Security**: Never commit API keys to git
2. **Error Handling**: Always check logs for Claude/Flask errors
3. **Rate Limiting**: Respect Claude API rate limits
4. **Interval Tuning**: Adjust based on your use case
   - Fast iteration: 1 second
   - Normal use: 2 seconds
   - Background monitoring: 5-10 seconds

## Cost Considerations

Claude API pricing (as of 2025):
- **Text input**: ~$3 per million tokens
- **Text output**: ~$15 per million tokens  
- **Image input**: ~$3.75 per 1000 images

**Estimated costs** (2-second interval):
- Text-only: ~$0.10-0.20 per hour
- With screenshots: ~$0.50-1.00 per hour

**Cost optimization**:
- Increase interval to reduce calls
- Use text-first approach (screenshot only as fallback)
- Monitor token usage in Claude console

## Files Reference

| File | Purpose |
|------|---------|
| `context_loop.rs` | Main synchronous collection loop |
| `claude_client.rs` | Claude API client |
| `llm_analyzer.rs` | Context analysis with Claude |
| `context_api.rs` | Flask API integration |
| `enhanced_context_collector.rs` | Context collection |
| `lib.rs` | Tauri app setup and loop startup |

## Next Steps

- [ ] Add retry logic for failed Claude API calls
- [ ] Implement request queuing for offline scenarios  
- [ ] Add metrics/analytics for Claude usage
- [ ] Create dashboard for monitoring context collection
- [ ] Add ability to pause/resume loop via UI
- [ ] Implement intelligent interval adjustment based on activity

