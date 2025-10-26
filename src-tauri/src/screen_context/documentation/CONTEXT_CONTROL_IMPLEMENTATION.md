# Context Collection Control Implementation

## Overview

This document describes the implementation of the context collection control system, which allows you to pause/resume context collection from the frontend, automatically pauses during action execution, and prevents feedback loops.

## What Was Implemented

### 1. **Flask `/trigger_action` Endpoint Integration** ✅
- **File**: `src-tauri/src/screen_context/context_api.rs`
- Added `trigger_action()` method to `ContextApiClient`
- Sends action UUID and description to Flask `/trigger_action` endpoint
- Returns response from Flask server

### 2. **Global Context Collection State** ✅
- **File**: `src-tauri/src/lib.rs`
- Created `ContextState` struct with `Arc<AtomicBool>` for thread-safe state management
- Methods: `enable()`, `disable()`, `toggle()`, `is_enabled()`
- Managed by Tauri app state (accessible from all commands and async tasks)

### 3. **Context Loop Pause Mechanism** ✅
- **File**: `src-tauri/src/screen_context/context_loop.rs`
- Added `context_state` field to `ContextLoop`
- Added `new_with_state()` constructor
- Modified `send_to_flask()` to check state before sending
- Automatically skips sending when collection is disabled

### 4. **Tauri Commands for Frontend Control** ✅
- **File**: `src-tauri/src/lib.rs`
- `toggle_context_collection()` - Toggle on/off
- `enable_context_collection()` - Enable collection
- `disable_context_collection()` - Disable collection
- `get_context_collection_status()` - Get current status
- `trigger_action(uuid, description)` - Trigger an action (auto-pauses during execution)

### 5. **Automatic Pause When Covalent is in Focus** ✅
- **File**: `src-tauri/src/screen_context/context_loop.rs`
- Checks `bundle_id == "com.hem.src-tauri"` or `app_name == "Covalent"`
- Automatically skips context collection when Covalent is focused
- Resumes automatically when user switches away

### 6. **Automatic Pause During Action Execution** ✅
- **File**: `src-tauri/src/lib.rs`
- `trigger_action()` command automatically disables context collection
- Waits 2 seconds after action completes before re-enabling
- Prevents infinite feedback loops from executed actions

## How It Works

### State Flow

```
User Action / Event
    ↓
Toggle Context Collection (Frontend)
    ↓
Tauri Command Updates ContextState
    ↓
Context Loop Checks State Before Sending
    ↓
If Enabled: Send to Flask
If Disabled: Skip (with log message)
```

### Automatic Pause Scenarios

1. **When Covalent App is Focused**
   - Detected in `context_loop.rs` during context collection
   - Prevents self-referential loops
   - Auto-resumes when user switches to another app

2. **During Action Execution**
   - `trigger_action()` command disables before executing
   - 2-second grace period after action completes
   - Prevents feedback from executed actions

3. **Manual User Toggle**
   - Frontend calls `disable_context_collection()`
   - Remains disabled until user re-enables
   - Useful for privacy or resource management

## Frontend Integration

### Using the Utilities

```typescript
import { 
  toggleContextCollection, 
  enableContextCollection,
  disableContextCollection,
  getContextCollectionStatus,
  triggerAction 
} from './utils/contextControl';

// Toggle context collection
const newState = await toggleContextCollection();
console.log(`Context collection is now ${newState ? 'ON' : 'OFF'}`);

// Get current status
const isEnabled = await getContextCollectionStatus();

// Trigger an action (will auto-pause during execution)
await triggerAction(actionUuid, 'Click submit button');
```

### Using the React Hook

```typescript
import { useContextCollectionState } from './utils/contextControl';

function SettingsPanel() {
  const { isEnabled, loading, toggle, enable, disable } = useContextCollectionState();

  return (
    <div>
      <p>Context Collection: {isEnabled ? 'ON' : 'OFF'}</p>
      <button onClick={toggle} disabled={loading}>
        {loading ? 'Updating...' : 'Toggle'}
      </button>
      <button onClick={enable} disabled={loading}>Enable</button>
      <button onClick={disable} disabled={loading}>Disable</button>
    </div>
  );
}
```

### Integration with Action Buttons

Update your `FloatingAssistant.tsx` to trigger actions:

```typescript
import { triggerAction } from '../utils/contextControl';

const handleActionClick = async (action: Action) => {
  try {
    // This will automatically pause context collection during execution
    const response = await triggerAction(action.uuid, action.description);
    console.log('Action executed:', response);
    
    // Update UI to show action was executed
    setActionStatus(action.id, 'done');
  } catch (error) {
    console.error('Failed to execute action:', error);
    setActionStatus(action.id, 'error');
  }
};
```

## API Reference

### Tauri Commands

#### `toggle_context_collection()`
- **Returns**: `boolean` - New state (true = enabled)
- **Description**: Toggles context collection on/off

#### `enable_context_collection()`
- **Returns**: `void`
- **Description**: Enables context collection

#### `disable_context_collection()`
- **Returns**: `void`
- **Description**: Disables context collection

#### `get_context_collection_status()`
- **Returns**: `boolean` - Current state (true = enabled)
- **Description**: Gets current context collection status

#### `trigger_action(action_uuid: string, action_description: string)`
- **Parameters**:
  - `action_uuid`: UUID of the action from Flask/graph.db
  - `action_description`: Human-readable description of the action
- **Returns**: `JSON` - Response from Flask server
- **Description**: Triggers an action (auto-pauses context collection during execution)

### Flask Endpoint

#### `POST /trigger_action`
**Request:**
```json
{
  "action_uuid": "uuid-string",
  "action": "description"
}
```

**Response:**
```json
{
  "message": "Action triggered",
  "success": true
}
```

## Console Logging

The system provides detailed console logs:

- 🟢 `Context collection ENABLED` - Collection enabled
- 🔴 `Context collection DISABLED` - Collection disabled
- ⏸️ `Context collection is disabled - skipping Flask send` - Skipped send
- 🔵 `Covalent app is in focus - temporarily pausing` - Auto-pause for Covalent
- 🎬 `Triggering action: ...` - Action execution started

## Testing

### Manual Testing

1. **Start the app:**
   ```bash
   npm run tauri dev
   ```

2. **Test toggle from browser console:**
   ```javascript
   // In browser dev tools console
   await window.__TAURI__.invoke('toggle_context_collection');
   await window.__TAURI__.invoke('get_context_collection_status');
   ```

3. **Test automatic pause:**
   - Focus on the Covalent window
   - Check console logs - should see "Covalent app is in focus"
   - Switch to another app - context collection resumes

4. **Test action trigger:**
   ```javascript
   await window.__TAURI__.invoke('trigger_action', {
     actionUuid: 'some-uuid',
     actionDescription: 'Test action'
   });
   // Check console - should see disable → execute → wait → enable
   ```

### Expected Console Output

```
🔄 Initializing context loop...
✓ Context loop initialized successfully, starting loop...

━━━ Iteration 1 ━━━
  📊 Collecting context...
  🔵 Covalent app is in focus - temporarily pausing context collection
  ⏸️  Skipping context collection while Covalent is focused

━━━ Iteration 2 ━━━
  📊 Collecting context...
  📋 Raw Context Data: {...}
  🤖 Analyzing with Claude...
  📤 Sending to Flask API...
  ✓ Flask response: Context processed successfully (UUID: ...)
```

## Files Modified/Created

### Modified Files
- ✅ `src-tauri/src/lib.rs` - Added ContextState, commands, state management
- ✅ `src-tauri/src/screen_context/context_api.rs` - Added trigger_action method
- ✅ `src-tauri/src/screen_context/context_loop.rs` - Added state checking and Covalent detection

### Created Files
- ✅ `src/utils/contextControl.ts` - Frontend utilities and React hook
- ✅ `CONTEXT_CONTROL_IMPLEMENTATION.md` - This documentation

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │  • Toggle Button                                 │   │
│  │  • Action Buttons                                │   │
│  │  • useContextCollectionState Hook                │   │
│  └─────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────┘
                        │ Tauri Commands
                        ↓
┌─────────────────────────────────────────────────────────┐
│                 Tauri Rust Backend                       │
│  ┌─────────────────────────────────────────────────┐   │
│  │  ContextState (Arc<AtomicBool>)                  │   │
│  │   • is_enabled: bool                             │   │
│  │   • enable(), disable(), toggle()                │   │
│  └─────────────────────────────────────────────────┘   │
│                        ↓                                 │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Context Loop                                    │   │
│  │   • Checks ContextState before sending           │   │
│  │   • Detects if Covalent is focused               │   │
│  │   • Skips send if disabled or self-focused       │   │
│  └─────────────────────────────────────────────────┘   │
│                        ↓                                 │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Context API Client                              │   │
│  │   • send_analysis_output()                       │   │
│  │   • trigger_action()                             │   │
│  └─────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP Requests
                        ↓
┌─────────────────────────────────────────────────────────┐
│                Flask Server (Python)                     │
│  • POST /screen - Receives context                      │
│  • POST /trigger_action - Executes action                │
│  • GET /health - Health check                           │
└─────────────────────────────────────────────────────────┘
```

## Future Enhancements

1. **Persist State**: Save enabled/disabled state to disk
2. **Time-based Auto-pause**: Pause during certain hours
3. **App-specific Rules**: Pause for specific apps beyond Covalent
4. **Frontend UI**: Add toggle switch to settings panel
5. **Status Indicator**: Visual indicator showing collection status
6. **Action Queue**: Queue actions while collection is paused

## Troubleshooting

### Context collection not pausing
- Check console logs for state changes
- Verify `get_context_collection_status()` returns expected value
- Ensure ContextState is properly managed in app state

### Actions not triggering
- Verify Flask server is running (`curl http://127.0.0.1:5001/health`)
- Check Flask logs: `tail -f server/flask_server.log`
- Ensure action UUID exists in graph.db

### Infinite feedback loops
- Verify automatic pause during action execution is working
- Check 2-second delay after action completion
- Consider increasing delay if actions take longer

## Summary

This implementation provides:
- ✅ Thread-safe, atomic state management for context collection
- ✅ Frontend control via Tauri commands
- ✅ Automatic pause when Covalent is in focus
- ✅ Automatic pause during action execution
- ✅ Integration with Flask `/trigger_action` endpoint
- ✅ React utilities and hooks for easy frontend integration
- ✅ Comprehensive logging for debugging

The system prevents infinite feedback loops while maintaining full user control over context collection behavior.

