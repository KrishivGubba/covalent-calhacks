import { useState, useEffect } from 'react';
import FloatingAssistant from './components/FloatingAssistant';
import type { Action } from './components/SuggestedActions';
import './styles.css';

// API function placeholder to fetch suggested actions
async function fetchSuggestedActions(): Promise<Action[]> {
  // TODO: Replace with actual API call
  // Example: const response = await fetch('/api/actions');
  // return await response.json();
  
  // Mock data for demonstration
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve([
        {
          id: '1',
          title: 'Review Pull Request #123',
          description: 'A new pull request has been submitted for the authentication module. Please review the changes and provide feedback on the implementation.',
        },
        {
          id: '2',
          title: 'Update Dependencies',
          description: 'Several npm packages have new versions available. Consider updating to get the latest security patches and features.',
        },
        {
          id: '3',
          title: 'Fix Linting Issues',
          description: 'There are 5 linting warnings in the codebase. Review and fix these issues to maintain code quality standards.',
        },
      ]);
    }, 1000);
  });
}

// Handler functions for start and stop buttons
function handleStart(): void {
  console.log('Start button pressed');
  // TODO: Implement start logic
  // Example: Start a process, begin monitoring, etc.
}

function handleStop(): void {
  console.log('Stop button pressed');
  // TODO: Implement stop logic
  // Example: Stop a process, pause monitoring, etc.
}

function App() {
  const [actions, setActions] = useState<Action[]>([]);
  const [isRunning, setIsRunning] = useState(true);
  const [loading, setLoading] = useState(true);

  // Fetch actions on component mount
  useEffect(() => {
    const loadActions = async () => {
      try {
        const fetchedActions = await fetchSuggestedActions();
        setActions(fetchedActions);
      } catch (error) {
        console.error('Failed to fetch actions:', error);
      } finally {
        setLoading(false);
      }
    };

    loadActions();
  }, []);

  const onStart = () => {
    handleStart();
    setIsRunning(true);
  };

  const onStop = () => {
    handleStop();
    setIsRunning(false);
  };

  return (
    <div style={styles.app}>
      {/* Animated background */}
      <div style={styles.backgroundAnimation}></div>

      {/* Floating Assistant Widget */}
      {!loading && (
        <FloatingAssistant 
          actions={actions}
          isRunning={isRunning}
          onStart={onStart}
          onStop={onStop}
        />
      )}
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
  },
  backgroundAnimation: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'radial-gradient(circle at 20% 20%, rgba(59, 130, 246, 0.08) 0%, transparent 50%), radial-gradient(circle at 40% 40%, rgba(147, 197, 253, 0.08) 0%, transparent 50%)',
    pointerEvents: 'none' as const,
    animation: 'float 20s ease-in-out infinite',
  },
};

export default App;
