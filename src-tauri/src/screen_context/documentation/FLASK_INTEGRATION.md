# Flask-Tauri Integration Guide

This document describes the integration between the Tauri app and the Flask API server.

## Overview

The integration consists of:

1. **Flask Server** (`server/app.py`) - A Python Flask server that receives context data and stores it in a graph database
2. **Startup Script** (`server/start_server.sh`) - Shell script to automatically start the Flask server
3. **Flask Process Manager** (`src-tauri/src/lib.rs`) - Rust code that manages the Flask server lifecycle
4. **Context API Client** (`src-tauri/src/screen_context/context_api.rs`) - HTTP client for sending context data to Flask
5. **Enhanced Context Collector** (`src-tauri/src/screen_context/enhanced_context_collector.rs`) - Integration point that sends collected context to Flask

## Architecture

```
Tauri App Start
    ↓
Start Flask Server (via bash script)
    ↓
EnhancedContextCollector collects user context
    ↓
ContextApiClient sends to Flask /screen endpoint
    ↓
Flask stores in graph.db via Tree class
```

## How It Works

### 1. Flask Server Startup

When the Tauri app starts, it automatically:
- Executes `server/start_server.sh`
- The script starts Flask on `http://127.0.0.1:5001`
- Flask server runs in the background
- Logs are written to `server/flask_server.log`

### 2. Context Collection & Sending

After collecting user context (screen, app info, activity, etc.):
- A human-readable description is generated based on context type
- The full context data is serialized to JSON
- Both are sent as POST request to `/screen` endpoint
- This happens asynchronously to not block context collection

### 3. Flask Processing

The Flask server:
- Receives POST request at `/screen` endpoint
- Extracts `description` and `data` fields
- Uses the `Tree` class from `graph.py` to learn and store
- Returns the node UUID of the stored data

## API Endpoints

### POST /screen

Send context data to be stored.

**Request:**
```json
{
  "description": "User developing frontend in VSCode (high activity)",
  "data": "{...serialized RawContext JSON...}"
}
```

**Response:**
```json
{
  "message": "Screen data received",
  "written": "node-uuid-123"
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "covalent-context-engine"
}
```

## Configuration

### Flask Server

- **Host:** 127.0.0.1 (localhost only)
- **Port:** 5001
- **Timeout:** 10 seconds
- **CORS:** Enabled

### Context API Client

Located in `src-tauri/src/screen_context/context_api.rs`:

```rust
const FLASK_API_URL: &str = "http://127.0.0.1:5001";
```

To change the URL, modify this constant.

## Files Modified/Created

### New Files
- `server/start_server.sh` - Flask startup script
- `src-tauri/src/screen_context/context_api.rs` - HTTP client for Flask API
- `FLASK_INTEGRATION.md` - This file

### Modified Files
- `server/app.py` - Added health endpoint, error handling, proper path resolution
- `src-tauri/src/lib.rs` - Added Flask server process management
- `src-tauri/src/screen_context/mod.rs` - Added context_api module exports
- `src-tauri/src/screen_context/enhanced_context_collector.rs` - Added API client integration

## Running the App

### Development Mode

```bash
cd /Users/hem/Downloads/covalent-calhacks
npm run tauri dev
```

The Tauri app will automatically:
1. Start the Flask server
2. Begin collecting context
3. Send context data to Flask API

### Production Mode

```bash
npm run tauri build
```

The built app will include the Flask server startup logic.

## Monitoring

### Check Flask Server Status

```bash
# Check if Flask is running
curl http://127.0.0.1:5001/health

# View Flask logs
tail -f server/flask_server.log
```

### Check Tauri Console

The Tauri app logs will show:
- `✓ Flask server started successfully` - Server started
- `✓ Context sent to Flask API successfully. Node UUID: ...` - Context sent
- `✗ Failed to send context to Flask API: ...` - Error sending context

## Troubleshooting

### Flask Server Won't Start

1. Check Python is installed: `python3 --version`
2. Check required packages: `pip list | grep flask`
3. Check permissions: `ls -la server/start_server.sh`
4. Check logs: `cat server/flask_server.log`

### Context Not Being Sent

1. Check Flask is running: `curl http://127.0.0.1:5001/health`
2. Check Tauri console for error messages
3. Check network connectivity
4. Verify Flask endpoint in `context_api.rs`

### Database Errors

1. Check `context-engine/graph.db` exists
2. Check write permissions on database file
3. Run `python context-engine/init_db.py` to reinitialize

## Development Notes

### Non-Blocking Architecture

Context sending is implemented as a non-blocking operation:
```rust
tokio::spawn(async move {
    // Send to Flask asynchronously
});
```

This ensures context collection isn't delayed by network operations.

### Error Handling

Errors in sending context are logged but don't stop context collection:
- Context collection continues regardless of Flask API status
- Errors are printed to console for debugging
- The app remains functional even if Flask is unavailable

### Context Description Format

The description sent to Flask follows this format:
```
"User {activity} in {app_name} - {window_title} ({activity_level})"
```

Examples:
- "User developing frontend in VSCode - main.rs (high activity)"
- "User browsing web in Chrome - Documentation (medium activity)"
- "User in video meeting in Zoom - Team Meeting (low activity)"

## Future Enhancements

- [ ] Add retry logic for failed API calls
- [ ] Implement request queuing for offline scenarios
- [ ] Add configuration file for API endpoint
- [ ] Implement health check before sending context
- [ ] Add metrics/analytics for API calls
- [ ] Implement batching for multiple context updates

