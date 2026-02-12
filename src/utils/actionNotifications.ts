import { isPermissionGranted, requestPermission, sendNotification } from '@tauri-apps/plugin-notification';
import { emit } from '@tauri-apps/api/event';

export interface ActionResultPayload {
  success: boolean;
  actionTitle: string;
  errorMessage?: string;
}

/**
 * Send OS notification and emit Tauri event when an action completes or fails
 * @param actionTitle - The title of the action that was executed
 * @param success - Whether the action succeeded or failed
 * @param errorMessage - Optional error message if the action failed
 */
export async function notifyActionResult(
  actionTitle: string,
  success: boolean,
  errorMessage?: string
): Promise<void> {
  try {
    // Request notification permission if needed
    let permitted = await isPermissionGranted();
    if (!permitted) {
      const result = await requestPermission();
      permitted = result === 'granted';
    }

    // Send OS notification if permitted
    if (permitted) {
      sendNotification({
        title: success ? 'Action Completed' : 'Action Failed',
        body: success 
          ? `${actionTitle}: Successfully executed. Click to check more details.`
          : `${actionTitle}: Failed. Click for more details.`,
      });
    }

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
