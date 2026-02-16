import { 
  isPermissionGranted, 
  requestPermission, 
  sendNotification,
  registerActionTypes,
  onAction
} from '@tauri-apps/plugin-notification';
import { emit } from '@tauri-apps/api/event';
import { invoke } from '@tauri-apps/api/core';

export interface ActionResultPayload {
  success: boolean;
  actionTitle: string;
  errorMessage?: string;
}

export interface PendingPlan {
  actionUuid: string;
  actionTitle: string;
  plan: any;
  editableParamsMap: Record<number, Record<string, unknown>>;
  timestamp: number;
}

// Store pending plans for notification-triggered execution
const pendingPlans = new Map<string, PendingPlan>();

/**
 * Initialize the notification system with action types
 * Should be called once on app startup
 */
export async function initializeNotifications(): Promise<void> {
  try {
    // Request notification permission if needed
    let permitted = await isPermissionGranted();
    if (!permitted) {
      const result = await requestPermission();
      permitted = result === 'granted';
    }

    if (!permitted) {
      console.warn('⚠️ Notification permission not granted');
      return;
    }

    // Register action types for interactive notifications
    await registerActionTypes([
      {
        id: 'covalent-plan',
        actions: [
          {
            id: 'approve',
            title: 'Approve',
            foreground: false, // Execute in background
          },
          {
            id: 'decline',
            title: 'Decline',
            foreground: false,
          },
          {
            id: 'view',
            title: 'View',
            foreground: true, // Bring app to foreground
          },
        ],
      },
      {
        id: 'covalent-status',
        actions: [
          {
            id: 'view',
            title: 'View Details',
            foreground: true,
          },
        ],
      },
    ]);

    console.log('✅ Notification system initialized');
  } catch (error) {
    console.error('Failed to initialize notification system:', error);
  }
}

/**
 * Set up listener for notification action button clicks
 * Should be called once on app startup
 */
export async function setupNotificationActionListener(): Promise<void> {
  try {
    await onAction(async (notification) => {
      console.log('🔔 Notification action received:', notification);
      
      // The notification object has extra data we can use
      const extra = notification.extra as { actionId?: string; actionUuid?: string } | undefined;
      const actionId = extra?.actionId;
      const actionUuid = extra?.actionUuid;
      
      if (!actionId || !actionUuid) {
        console.error('❌ Missing actionId or actionUuid in notification extra data');
        return;
      }
      
      if (actionId === 'approve') {
        // User approved the plan from notification
        await handleApproveFromNotification(actionUuid);
      } else if (actionId === 'decline') {
        // User declined the plan
        await handleDeclineFromNotification(actionUuid);
      } else if (actionId === 'view') {
        // User wants to view in app
        await handleViewFromNotification();
      }
    });
    
    console.log('✅ Notification action listener set up');
  } catch (error) {
    console.error('Failed to set up notification action listener:', error);
  }
}

/**
 * Handle approve action from notification
 */
async function handleApproveFromNotification(actionUuid: string): Promise<void> {
  const pendingPlan = pendingPlans.get(actionUuid);
  
  if (!pendingPlan) {
    console.error('❌ No pending plan found for action UUID:', actionUuid);
    await notifyExecutionStatus('Action', false, 'Plan expired or not found');
    return;
  }
  
  try {
    console.log('🚀 Executing action from notification:', pendingPlan.actionTitle);
    
    // Get proposed actions from plan
    const proposedActions = pendingPlan.plan.proposed_actions || 
                           (pendingPlan.plan.proposed_action ? [pendingPlan.plan.proposed_action] : []);
    
    if (proposedActions.length === 0) {
      throw new Error('No actions to execute');
    }
    
    // Build actions to execute
    const actionsToExecute = proposedActions.map((action: any) => ({
      step_id: action.step_id,
      tool_name: action.tool_name,
      parameters: pendingPlan.editableParamsMap[action.step_id] || action.parameters,
    }));
    
    // Execute the action
    const response = await invoke<any>('execute_action', {
      actionUuid: pendingPlan.actionUuid,
      actions: actionsToExecute,
    });
    
    console.log('✅ Execution completed:', response);
    
    // Send success notification
    if (response.status === 'success') {
      await notifyExecutionStatus(pendingPlan.actionTitle, true);
    } else if (response.summary) {
      const succeeded = response.summary.succeeded || 0;
      const total = response.summary.total || 0;
      if (succeeded === 0) {
        await notifyExecutionStatus(pendingPlan.actionTitle, false, 'All actions failed');
      } else if (succeeded < total) {
        await notifyExecutionStatus(pendingPlan.actionTitle, true, `${succeeded}/${total} succeeded`);
      } else {
        await notifyExecutionStatus(pendingPlan.actionTitle, true);
      }
    } else {
      await notifyExecutionStatus(pendingPlan.actionTitle, false, response.error || 'Unknown error');
    }
    
    // Clean up
    pendingPlans.delete(actionUuid);
    
    // Emit event for UI updates
    await emit('action-completed', {
      success: response.status === 'success',
      actionTitle: pendingPlan.actionTitle,
    } as ActionResultPayload);
    
  } catch (error) {
    console.error('❌ Execution failed:', error);
    await notifyExecutionStatus(pendingPlan.actionTitle, false, String(error));
    pendingPlans.delete(actionUuid);
  }
}

/**
 * Handle decline action from notification
 */
async function handleDeclineFromNotification(actionUuid: string): Promise<void> {
  console.log('❌ User declined action from notification:', actionUuid);
  pendingPlans.delete(actionUuid);
  // No notification needed for decline
}

/**
 * Handle view action from notification
 */
async function handleViewFromNotification(): Promise<void> {
  try {
    await invoke('open_main_window');
    console.log('✅ Opened main window');
  } catch (error) {
    console.error('Failed to open main window:', error);
  }
}

/**
 * Check if we should send a notification (i.e., app is not focused)
 */
export async function shouldSendNotification(): Promise<boolean> {
  try {
    const isFocused = await invoke<boolean>('is_covalent_focused');
    return !isFocused;
  } catch (error) {
    console.error('Failed to check if Covalent is focused:', error);
    // Default to not sending notification if we can't determine focus
    return false;
  }
}

/**
 * Send notification when a plan is ready for approval
 * Only sends if app is not focused
 */
export async function notifyPlanReady(
  actionTitle: string,
  actionUuid: string,
  plan: any,
  editableParamsMap: Record<number, Record<string, unknown>>
): Promise<void> {
  try {
    // Check if we should send notification
    const shouldNotify = await shouldSendNotification();
    if (!shouldNotify) {
      console.log('⏭️ Skipping notification - Covalent is focused');
      return;
    }
    
    // Request notification permission if needed
    let permitted = await isPermissionGranted();
    if (!permitted) {
      const result = await requestPermission();
      permitted = result === 'granted';
    }

    if (!permitted) {
      console.warn('⚠️ Notification permission not granted');
      return;
    }
    
    // Store the pending plan
    pendingPlans.set(actionUuid, {
      actionUuid,
      actionTitle,
      plan,
      editableParamsMap,
      timestamp: Date.now(),
    });
    
    // Clean up old pending plans (older than 1 hour)
    const oneHourAgo = Date.now() - 60 * 60 * 1000;
    for (const [uuid, pendingPlan] of pendingPlans.entries()) {
      if (pendingPlan.timestamp < oneHourAgo) {
        pendingPlans.delete(uuid);
      }
    }
    
    // Get plan summary
    const proposedActions = plan.proposed_actions || 
                           (plan.proposed_action ? [plan.proposed_action] : []);
    const actionCount = proposedActions.length;
    const actionSummary = actionCount === 1 
      ? proposedActions[0].tool_name 
      : `${actionCount} actions`;
    
    // Generate a numeric ID for the notification
    const notificationId = Math.floor(Math.random() * 2147483647);
    
    // Send OS notification with action buttons
    sendNotification({
      id: notificationId,
      title: `Plan Ready: ${actionTitle}`,
      body: `Covalent has planned ${actionSummary}. Approve to execute or view for details.`,
      actionTypeId: 'covalent-plan',
      extra: {
        actionId: 'plan',
        actionUuid: actionUuid,
      },
    });
    
    console.log('📬 Plan notification sent:', actionTitle);
  } catch (error) {
    console.error('Failed to send plan notification:', error);
  }
}

/**
 * Send notification for action execution status
 * Only sends if app is not focused
 */
export async function notifyExecutionStatus(
  actionTitle: string,
  success: boolean,
  message?: string
): Promise<void> {
  try {
    // Check if we should send notification
    const shouldNotify = await shouldSendNotification();
    if (!shouldNotify) {
      console.log('⏭️ Skipping notification - Covalent is focused');
      return;
    }
    
    // Request notification permission if needed
    let permitted = await isPermissionGranted();
    if (!permitted) {
      const result = await requestPermission();
      permitted = result === 'granted';
    }

    if (!permitted) {
      return;
    }

    // Generate a numeric ID for the notification
    const notificationId = Math.floor(Math.random() * 2147483647);
    
    // Send OS notification
    sendNotification({
      id: notificationId,
      title: success ? 'Action Completed' : 'Action Failed',
      body: message 
        ? `${actionTitle}: ${message}`
        : success 
          ? `${actionTitle}: Successfully executed`
          : `${actionTitle}: Failed`,
      actionTypeId: 'covalent-status',
      extra: {
        actionId: 'status',
      },
    });
    
    console.log('📬 Status notification sent:', actionTitle, success ? '✅' : '❌');
  } catch (error) {
    console.error('Failed to send execution status notification:', error);
  }
}

/**
 * Legacy function for backward compatibility
 * Send OS notification and emit Tauri event when an action completes or fails
 */
export async function notifyActionResult(
  actionTitle: string,
  success: boolean,
  errorMessage?: string
): Promise<void> {
  try {
    await notifyExecutionStatus(actionTitle, success, errorMessage);

    // Emit event for dashboard to handle navigation
    await emit('action-completed', { 
      success, 
      actionTitle, 
      errorMessage 
    } as ActionResultPayload);
  } catch (error) {
    console.error('Failed to send action notification:', error);
  }
}

/**
 * Get number of pending plans (for debugging)
 */
export function getPendingPlansCount(): number {
  return pendingPlans.size;
}

/**
 * Clear all pending plans (for cleanup)
 */
export function clearPendingPlans(): void {
  pendingPlans.clear();
}
