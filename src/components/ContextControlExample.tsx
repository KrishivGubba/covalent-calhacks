/**
 * Example: Context Control Integration
 * 
 * This file shows how to integrate context collection control into your existing components.
 * Copy the relevant parts into your FloatingAssistant.tsx or other components.
 */

import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

// Example 1: Simple Toggle Button Component
export const ContextToggleButton: React.FC = () => {
  const [isEnabled, setIsEnabled] = useState(true);
  const [loading, setLoading] = useState(false);

  // Check initial status on mount
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const status = await invoke<boolean>('get_context_collection_status');
        setIsEnabled(status);
      } catch (error) {
        console.error('Failed to get status:', error);
      }
    };
    checkStatus();
  }, []);

  const handleToggle = async () => {
    setLoading(true);
    try {
      const newState = await invoke<boolean>('toggle_context_collection');
      setIsEnabled(newState);
    } catch (error) {
      console.error('Failed to toggle:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleToggle}
      disabled={loading}
      style={{
        padding: '8px 16px',
        backgroundColor: isEnabled ? '#4CAF50' : '#f44336',
        color: 'white',
        border: 'none',
        borderRadius: '4px',
        cursor: loading ? 'not-allowed' : 'pointer',
        opacity: loading ? 0.6 : 1,
      }}
    >
      {loading ? '⏳' : isEnabled ? '🟢' : '🔴'} 
      {' '}
      Context Collection {isEnabled ? 'ON' : 'OFF'}
    </button>
  );
};

// Example 2: Integration with Action Buttons
interface Action {
  id: string;
  uuid: string;
  title: string;
  description: string;  // Contains full context for execution
}

export const ActionButtonWithAutoSuspend: React.FC<{ action: Action }> = ({ action }) => {
  const [status, setStatus] = useState<'idle' | 'executing' | 'done' | 'error'>('idle');

  const handleActionClick = async () => {
    setStatus('executing');
    
    try {
      // New flow: 
      // 1. Call plan_action to get action plan
      // 2. User approves/edits the plan
      // 3. Call execute_action to execute
      const response = await invoke('plan_action', {
        actionUuid: action.uuid,
        actionOverride: null,
      });
      
      console.log('Action plan received:', response);
      // In real usage, you would show a confirmation modal here
      // For this example, we just mark as done
      setStatus('done');
      
      // Reset to idle after 2 seconds
      setTimeout(() => setStatus('idle'), 2000);
    } catch (error) {
      console.error('Failed to plan action:', error);
      setStatus('error');
      
      // Reset to idle after 3 seconds on error
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  const getButtonStyle = () => {
    const baseStyle = {
      padding: '8px 16px',
      border: 'none',
      borderRadius: '4px',
      cursor: 'pointer',
      transition: 'all 0.2s',
    };

    switch (status) {
      case 'executing':
        return { ...baseStyle, backgroundColor: '#FFA500', color: 'white', cursor: 'not-allowed' };
      case 'done':
        return { ...baseStyle, backgroundColor: '#4CAF50', color: 'white' };
      case 'error':
        return { ...baseStyle, backgroundColor: '#f44336', color: 'white' };
      default:
        return { ...baseStyle, backgroundColor: '#2196F3', color: 'white' };
    }
  };

  const getButtonText = () => {
    switch (status) {
      case 'executing':
        return '⚙️ Executing...';
      case 'done':
        return '✅ Done';
      case 'error':
        return '❌ Error';
      default:
        return '▶️ Run Action';
    }
  };

  return (
    <div style={{ marginBottom: '8px' }}>
      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{action.title}</div>
      <div style={{ fontSize: '12px', color: '#666', marginBottom: '8px' }}>
        {action.description}
      </div>
      <button
        onClick={handleActionClick}
        disabled={status === 'executing'}
        style={getButtonStyle()}
      >
        {getButtonText()}
      </button>
    </div>
  );
};

// Example 3: Status Indicator
export const ContextCollectionIndicator: React.FC = () => {
  const [isEnabled, setIsEnabled] = useState(true);

  useEffect(() => {
    const checkStatus = async () => {
      const status = await invoke<boolean>('get_context_collection_status');
      setIsEnabled(status);
    };

    // Check status every 5 seconds
    checkStatus();
    const interval = setInterval(checkStatus, 5000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        padding: '8px 12px',
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        color: 'white',
        borderRadius: '20px',
        fontSize: '12px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        zIndex: 9999,
      }}
    >
      <span style={{ fontSize: '16px' }}>{isEnabled ? '🟢' : '🔴'}</span>
      <span>Context: {isEnabled ? 'Active' : 'Paused'}</span>
    </div>
  );
};

// Example 4: Full Integration Example
export const FloatingAssistantWithContextControl: React.FC = () => {
  const [actions] = useState<Action[]>([
    {
      id: '1',
      uuid: 'action-uuid-1',
      title: 'Click Submit',
      description: 'Click the submit button to complete the form submission',
    },
    {
      id: '2',
      uuid: 'action-uuid-2',
      title: 'Fill Name Field',
      description: 'Enter "John Doe" into the name input field',
    },
  ]);

  return (
    <div
      style={{
        position: 'fixed',
        top: '100px',
        right: '20px',
        width: '300px',
        backgroundColor: 'white',
        borderRadius: '12px',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
        padding: '16px',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      {/* Header with context control */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
        }}
      >
        <h3 style={{ margin: 0, fontSize: '18px' }}>Suggested Actions</h3>
        <ContextToggleButton />
      </div>

      {/* Actions List */}
      <div>
        {actions.map((action) => (
          <ActionButtonWithAutoSuspend key={action.id} action={action} />
        ))}
      </div>

      {/* Status Indicator */}
      <ContextCollectionIndicator />
    </div>
  );
};

/**
 * HOW TO USE IN YOUR EXISTING FloatingAssistant.tsx:
 * 
 * 1. Add the toggle button to your header:
 * 
 *    import { ContextToggleButton } from './ContextControlExample';
 * 
 *    // In your render:
 *    <header>
 *      <h3>Covalent Assistant</h3>
 *      <ContextToggleButton />
 *    </header>
 * 
 * 2. Update your action click handler:
 * 
 *    import { invoke } from '@tauri-apps/api/core';
 * 
 *    const handleActionClick = async (action: Action) => {
 *      try {
 *        setActionStatuses({ ...actionStatuses, [action.id]: 'playing' });
 *        
 *        // Step 1: Plan the action (shows confirmation modal)
 *        const plan = await invoke('plan_action', {
 *          actionUuid: action.uuid,
 *          actionOverride: null,
 *        });
 *        
 *        // Step 2: Execute after user confirmation
 *        await invoke('execute_action', {
 *          actionUuid: action.uuid,
 *          toolName: plan.proposed_action.tool_name,
 *          parameters: plan.proposed_action.parameters,
 *        });
 *        
 *        setActionStatuses({ ...actionStatuses, [action.id]: 'done' });
 *      } catch (error) {
 *        console.error('Action failed:', error);
 *        setActionStatuses({ ...actionStatuses, [action.id]: 'idle' });
 *      }
 *    };
 * 
 * 3. Add status indicator (optional):
 * 
 *    import { ContextCollectionIndicator } from './ContextControlExample';
 * 
 *    // At the end of your App component:
 *    <ContextCollectionIndicator />
 */

