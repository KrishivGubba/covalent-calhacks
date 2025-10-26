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
 * Enable context collection
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
 * Trigger an action by UUID
 * @param actionUuid The UUID of the action to trigger
 * @param actionDescription Description of the action being triggered
 * @returns Response from the Flask server
 */
export async function triggerAction(
  actionUuid: string,
  actionDescription: string
): Promise<any> {
  try {
    console.log(`Triggering action: ${actionDescription} (${actionUuid})`);
    
    // This will automatically disable context collection during execution
    // and re-enable it after 2 seconds
    const response = await invoke('trigger_action', {
      actionUuid,
      actionDescription,
    });
    
    console.log('Action triggered successfully:', response);
    return response;
  } catch (error) {
    console.error('Failed to trigger action:', error);
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

