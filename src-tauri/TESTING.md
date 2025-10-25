# 🧪 Testing Covalent Context Engine

## Quick Test Setup

### 1. Run the Context Monitor

```bash
# From the src-tauri directory
./run_monitor.sh

# Or with debug JSON output
./run_monitor.sh --debug

# Or run directly with cargo
cargo run --bin context_monitor
```

### 2. What It Does

The monitor will:
- **📊 Analyze your screen every 20 seconds**
- **🔍 Detect what app you're using**
- **📝 Describe what you're doing**
- **🔄 Track changes in your workflow**
- **🤖 Suggest automation opportunities**

### 3. Sample Output

```
🔍 Covalent Context Monitor - Starting...
✅ All components initialized successfully

🔧 System Readiness Check:
  ✅ Accessibility Permission: Available
  ✅ Screen Recording Permission: Available
  ❌ Browser Integration: Not Available
  ✅ OCR Engine: Available
  ✅ Overall Status: Ready

🚀 Starting context monitoring (every 20 seconds)...
================================================================================

📊 Analysis #1 - 14:32:15
------------------------------------------------------------
📱 App: Visual Studio Code
🎯 Context: Development(Frontend)
🎲 Confidence: 75.0%
⏱️  Session: 0m 20s
⚡ Activity: Medium
🎬 Stage: Active Coding
🖱️  Pattern: Steady fast typing

📝 What's happening:
   User is working in Visual Studio Code (Development) focusing on: src/main.rs. 
   Moderate activity level with steady fast typing indicating active development work.

🤖 Automation Ideas:
   💡 High typing volume - text expansion or snippets could help

🔧 Technical Details:
   Data Sources: App Detection, Activity Monitoring
   Processing: 45ms
   Focus Areas: Visual Studio Code
```

### 4. Testing Different Scenarios

Try these activities to see how the system responds:

#### 🌐 **Browser Testing**
1. Open Chrome with `--remote-debugging-port=9222`
2. Navigate between websites
3. Fill out forms
4. Scroll pages

#### 💻 **Development Testing**
1. Open your IDE
2. Switch between files
3. Debug code
4. Write documentation

#### 📧 **Communication Testing**
1. Open Slack/Teams
2. Compose messages
3. Join video calls

#### 📊 **Data Work Testing**
1. Open spreadsheets
2. Create charts
3. Analyze data

### 5. Browser Integration Setup

For full DOM analysis, run Chrome with debugging:

```bash
# Close all Chrome instances first, then run:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Or add this flag to your Chrome shortcut
```

### 6. Permissions Setup

#### macOS Permissions Required:
1. **System Preferences → Security & Privacy → Privacy**
2. **Screen Recording**: Add Terminal (or your terminal app)
3. **Accessibility**: Add Terminal (or your terminal app)

### 7. Debugging

#### Enable Debug Mode:
```bash
export COVALENT_DEBUG=1
cargo run --bin context_monitor
```

This will show:
- Full JSON output for each analysis
- Detailed error messages
- Performance metrics

#### Common Issues:
- **"No frontmost application found"**: Permissions issue
- **"Chrome DevTools returned status"**: Chrome not running with debug port
- **"OCR engine not available"**: Tesseract not installed

### 8. Performance Notes

- **CPU Usage**: ~2-5% every 20 seconds
- **Memory**: ~50-100MB for the monitor process
- **Permissions**: Only reads screen metadata, no sensitive data
- **Privacy**: No screenshots stored, only analysis results

### 9. Sample Test Plan

1. **Baseline Test**: Let it run while you normally work
2. **App Switching Test**: Rapidly switch between different apps
3. **Browser Test**: Navigate websites, fill forms
4. **Idle Test**: Step away from computer
5. **Intensive Work Test**: Heavy coding/design work

The system should accurately detect context changes and provide relevant insights for each scenario.

## Expected Results

- ✅ Accurate app detection
- ✅ Context type classification
- ✅ Activity level monitoring
- ✅ Change detection
- ✅ Workflow stage identification
- ✅ Automation suggestions

Ready to test! 🚀