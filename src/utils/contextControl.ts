/**
 * Context Collection Control Utilities
 * 
 * This module provides functions to control context collection state from the frontend.
 * Use these to pause/resume context collection based on user actions or app state.
 */

import { invoke } from '@tauri-apps/api/core';
import React from 'react';

/**
 * Toggle context collection on/off
 * @returns The new state (true = enabled, false = disabled)
 */
export async function toggleContextCollection(): Promise<boolean> {
  try {
    const newState = await invoke<boolean>('toggle_context_collection');
    console.log(`Context collection ${newState ? 'enabled' : 'disabled'}`);
    return newState;
  } catch (error) {
    console.error('Failed to toggle context collection:', error);
    throw error;
  }
}

/**
 * Enable context collection (unconditional)
 * Use this when user explicitly clicks "Resume" button
 */
export async function enableContextCollection(): Promise<void> {
  try {
    await invoke('enable_context_collection');
    console.log('Context collection enabled');
  } catch (error) {
    console.error('Failed to enable context collection:', error);
    throw error;
  }
}

/**
 * Enable context collection only if user hasn't manually paused
 * Use this when canceling actions or on errors to restore pre-action state
 */
export async function enableContextCollectionIfNotUserPaused(): Promise<void> {
  try {
    await invoke('enable_context_collection_if_not_user_paused');
    console.log('Context collection conditionally enabled (respects user pause)');
  } catch (error) {
    console.error('Failed to conditionally enable context collection:', error);
    throw error;
  }
}

/**
 * Disable context collection
 */
export async function disableContextCollection(): Promise<void> {
  try {
    await invoke('disable_context_collection');
    console.log('Context collection disabled');
  } catch (error) {
    console.error('Failed to disable context collection:', error);
    throw error;
  }
}

/**
 * Get current context collection status
 * @returns true if enabled, false if disabled
 */
export async function getContextCollectionStatus(): Promise<boolean> {
  try {
    const status = await invoke<boolean>('get_context_collection_status');
    return status;
  } catch (error) {
    console.error('Failed to get context collection status:', error);
    throw error;
  }
}

/**
 * Plan an action by UUID - Phase 1 of new action flow
 * @param actionUuid The UUID of the action to plan
 * @param actionOverride Optional override for action parameters
 * @returns Action plan from the Flask server (for user approval/editing)
 */
export async function planAction(
  actionUuid: string,
  actionOverride?: { action_name?: string; action_plan?: string } | null
): Promise<any> {
  try {
    console.log(`Planning action: ${actionUuid}`);
    
    const response = await invoke('plan_action', {
      actionUuid,
      actionOverride: actionOverride || null,
    });
    
    console.log('Action plan received:', response);
    return response;
  } catch (error) {
    console.error('Failed to plan action:', error);
    throw error;
  }
}

/**
 * Execute an approved action - Phase 2 of new action flow
 * @param actionUuid The UUID of the action
 * @param toolName The MCP tool to execute
 * @param parameters The parameters for the tool call
 * @returns Response from the Flask server
 */
export async function executeAction(
  actionUuid: string,
  toolName: string,
  parameters: Record<string, unknown>
): Promise<any> {
  try {
    console.log(`Executing action: ${actionUuid} with tool ${toolName}`);
    
    const response = await invoke('execute_action', {
      actionUuid,
      toolName,
      parameters,
    });
    
    console.log('Action executed successfully:', response);
    return response;
  } catch (error) {
    console.error('Failed to execute action:', error);
    throw error;
  }
}

/**
 * Hook to use context collection state in React components
 */
export function useContextCollectionState() {
  const [isEnabled, setIsEnabled] = React.useState(true);
  const [loading, setLoading] = React.useState(false);

  const checkStatus = async () => {
    try {
      const status = await getContextCollectionStatus();
      setIsEnabled(status);
    } catch (error) {
      console.error('Failed to check status:', error);
    }
  };

  const toggle = async () => {
    setLoading(true);
    try {
      const newState = await toggleContextCollection();
      setIsEnabled(newState);
    } catch (error) {
      console.error('Failed to toggle:', error);
    } finally {
      setLoading(false);
    }
  };

  const enable = async () => {
    setLoading(true);
    try {
      await enableContextCollection();
      setIsEnabled(true);
    } catch (error) {
      console.error('Failed to enable:', error);
    } finally {
      setLoading(false);
    }
  };

  const disable = async () => {
    setLoading(true);
    try {
      await disableContextCollection();
      setIsEnabled(false);
    } catch (error) {
      console.error('Failed to disable:', error);
    } finally {
      setLoading(false);
    }
  };

  // Check status on mount
  React.useEffect(() => {
    checkStatus();
  }, []);

  return {
    isEnabled,
    loading,
    toggle,
    enable,
    disable,
    refresh: checkStatus,
  };
}

