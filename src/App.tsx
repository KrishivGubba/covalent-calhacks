import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import FloatingAssistant from './components/FloatingAssistant';
import CompletionPopup from './components/CompletionPopup';
import type { Action } from './components/SuggestedActions';
import { enableContextCollection, disableContextCollection, getContextCollectionStatus } from './utils/contextControl';
import { initializeNotifications, setupNotificationActionListener } from './utils/actionNotifications';
import './styles.css';

// Fetch suggested actions from Tauri backend
async function fetchSuggestedActions(): Promise<Action[]> {
  try {
    const actions = await invoke<Action[]>('get_suggested_actions');
    console.log(`📋 Fetched ${actions.length} actions from Tauri`);
    return actions;
  } catch (error) {
    console.error('Failed to fetch actions:', error);
    return [];
  }
}

// Handler functions for start and stop buttons
async function handleStart(): Promise<void> {
  console.log('Start Learning button pressed');
  try {
    // Enable context collection when learning starts
    await enableContextCollection();
    console.log('✅ Context collection enabled - learning active');
  } catch (error) {
    console.error('Failed to enable context collection:', error);
  }
}

async function handleStop(): Promise<void> {
  console.log('Pause Covalent button pressed');
  try {
    // Disable context collection when learning stops
    await disableContextCollection();
    console.log('⏸️  Context collection disabled - learning paused');
  } catch (error) {
    console.error('Failed to disable context collection:', error);
  }
}

function App() {
  const [actions, setActions] = useState<Action[]>([]);
  const [isRunning, setIsRunning] = useState(true);

  // Fetch actions and sync context collection status on component mount
  useEffect(() => {
    const initialize = async () => {
      try {
        // Initialize notification system
        await initializeNotifications();
        await setupNotificationActionListener();
        console.log('✅ Notification system initialized');

        // Load suggested actions
        const fetchedActions = await fetchSuggestedActions();
        setActions(fetchedActions);

        // Sync UI state with actual context collection status
        const contextStatus = await getContextCollectionStatus();
        setIsRunning(contextStatus);
        console.log(`📊 Initial context collection status: ${contextStatus ? 'Running' : 'Stopped'}`);
      } catch (error) {
        console.error('Failed to initialize:', error);
      }
    };

    initialize();

    // Poll for new actions every 3 seconds
    const pollInterval = setInterval(async () => {
      try {
        const fetchedActions = await fetchSuggestedActions();
        // Only update if actions have actually changed
        setActions(prevActions => {
          const hasChanged = JSON.stringify(prevActions) !== JSON.stringify(fetchedActions);
          return hasChanged ? fetchedActions : prevActions;
        });
      } catch (error) {
        console.error('Failed to poll actions:', error);
      }
    }, 3000);

    // Cleanup interval on unmount
    return () => clearInterval(pollInterval);
  }, []);

  const onStart = async () => {
    await handleStart();
    setIsRunning(true);
  };

  const onStop = async () => {
    await handleStop();
    setIsRunning(false);
  };

  return (
    <div style={styles.app}>
      {/* Animated background */}
      <div style={styles.backgroundAnimation}></div>

      {/* Floating Assistant Widget - always rendered to maintain transparency */}
      <FloatingAssistant 
        actions={actions}
        isRunning={isRunning}
        onStart={onStart}
        onStop={onStop}
      />
      
      {/* Tab Completion Popup */}
      <CompletionPopup />
    </div>
  );
}

const styles = {
  app: {
    height: '100vh',
    width: '100vw',
    overflow: 'hidden',
    background: 'transparent',
    position: 'relative' as const,
    WebkitAppRegion: 'no-drag' as const,
  },
  backgroundAnimation: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'transparent',
    pointerEvents: 'none' as const,
  },
};

export default App;
