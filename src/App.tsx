import { useState, useEffect } from 'react';
import Header from './components/Header';
import SuggestedActions from './components/SuggestedActions';
import ControlButtons from './components/ControlButtons';
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
  const [isRunning, setIsRunning] = useState(false);
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

  const handleProfileClick = () => {
    console.log('Profile button clicked');
    // TODO: Implement profile navigation or modal
  };

  const handleLinkMCPsClick = () => {
    console.log('Link MCPs button clicked');
    // TODO: Implement MCP linking functionality
  };

  return (
    <div style={styles.app}>
      {/* Animated background */}
      <div style={styles.backgroundAnimation}></div>
      
      <Header 
        onProfileClick={handleProfileClick}
        onLinkMCPsClick={handleLinkMCPsClick}
      />
      <div style={styles.mainContent}>
        {loading ? (
          <div style={styles.loading}>
            <div style={styles.loadingSpinner}></div>
            <span style={styles.loadingText}>Loading...</span>
          </div>
        ) : (
          <SuggestedActions actions={actions} />
        )}
      </div>
      <ControlButtons 
        onStart={onStart}
        onStop={onStop}
        isRunning={isRunning}
      />
    </div>
  );
}

const styles = {
  app: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100vh',
    width: '100vw',
    overflow: 'hidden',
    background: 'linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 50%, #fae8ff 100%)',
    position: 'relative' as const,
  },
  backgroundAnimation: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'radial-gradient(circle at 20% 50%, rgba(147, 197, 253, 0.3) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(232, 121, 249, 0.3) 0%, transparent 50%)',
    pointerEvents: 'none' as const,
    animation: 'float 20s ease-in-out infinite',
  },
  mainContent: {
    flex: 1,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column' as const,
    position: 'relative' as const,
    zIndex: 1,
  },
  loading: {
    display: 'flex',
    flexDirection: 'column' as const,
    justifyContent: 'center',
    alignItems: 'center',
    flex: 1,
    gap: '1rem',
  },
  loadingSpinner: {
    width: '40px',
    height: '40px',
    border: '3px solid rgba(148, 163, 184, 0.1)',
    borderTop: '3px solid #60a5fa',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  loadingText: {
    fontSize: '1rem',
    color: '#64748b',
    fontWeight: '500',
  },
};

export default App;
