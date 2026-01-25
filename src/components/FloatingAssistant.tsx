import React, { useState, useEffect, memo } from 'react';
import type { Action } from './SuggestedActions';

interface FloatingAssistantProps {
  actions: Action[];
  isRunning: boolean;
  onStart: () => void;
  onStop: () => void;
}

type ViewState = 'collapsed' | 'prompt' | 'expanded';
type ActionStatus = 'idle' | 'playing' | 'done';

const FloatingAssistant: React.FC<FloatingAssistantProps> = memo(({ 
  actions, 
  isRunning, 
  onStart, 
  onStop 
}) => {
  const [viewState, setViewState] = useState<ViewState>('collapsed');
  const [actionStatuses, setActionStatuses] = useState<Record<string, ActionStatus>>({});
  const [isAnimating, setIsAnimating] = useState(false);
  const [hoveredActionId, setHoveredActionId] = useState<string | null>(null);

  // Simulate action detection - expand to prompt
  useEffect(() => {
    if (actions.length > 0 && viewState === 'collapsed') {
      setTimeout(() => {
        setViewState('prompt');
      }, 2000); // Simulate delay before suggesting help
    }
  }, [actions, viewState]);

  const handleCollapsedClick = () => {
    if (!isAnimating) {
      setViewState('prompt');
    }
  };

  const handleIconClick = () => {
    if (!isAnimating) {
      if (viewState === 'prompt' || viewState === 'expanded') {
        setIsAnimating(true);
        setTimeout(() => {
          setViewState('collapsed');
          setIsAnimating(false);
        }, 100);
      } else {
        handleCollapsedClick();
      }
    }
  };

  const handleAccept = () => {
    setIsAnimating(true);
    setTimeout(() => {
      setViewState('expanded');
      setIsAnimating(false);
    }, 100);
  };

  const handleReject = () => {
    setIsAnimating(true);
    setTimeout(() => {
      setViewState('collapsed');
      setIsAnimating(false);
    }, 100);
  };

  const handleActionClick = async (action: Action) => {
    const currentStatus = actionStatuses[action.id] || 'idle';
    
    if (currentStatus === 'idle') {
      setActionStatuses({ ...actionStatuses, [action.id]: 'playing' });
      
      try {
        const { invoke } = await import('@tauri-apps/api/core');
        console.log(`🎬 Triggering action: ${action.title} (${action.uuid})`);
        
        await invoke('trigger_action', {
          actionUuid: action.uuid,
          actionPrompt: action.action_prompt,
        });
        
        console.log(`✅ Action completed successfully`);
        setActionStatuses(prev => ({ ...prev, [action.id]: 'done' }));
      } catch (error) {
        console.error(`❌ Action failed:`, error);
        setActionStatuses(prev => ({ ...prev, [action.id]: 'idle' }));
      }
    } else if (currentStatus === 'playing') {
      // Can't cancel while playing
      console.log('⏸️  Action is already executing');
    } else if (currentStatus === 'done') {
      setActionStatuses({ ...actionStatuses, [action.id]: 'idle' });
    }
  };

  const renderActionButton = (action: Action) => {
    const status = actionStatuses[action.id] || 'idle';
    
    if (status === 'idle') {
      return (
        <button 
          style={styles.playButton}
          onClick={(e) => {
            e.stopPropagation();
            handleActionClick(action);
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(120, 120, 120, 0.65)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(100, 100, 100, 0.45)';
          }}
        >
          ▶
        </button>
      );
    } else if (status === 'playing') {
      return (
        <button 
          style={styles.loadingButton}
          disabled={true}
        >
          <span style={styles.loadingDots}>
            <span style={styles.dot1}>.</span>
            <span style={styles.dot2}>.</span>
            <span style={styles.dot3}>.</span>
          </span>
        </button>
      );
    } else {
      return (
        <button 
          style={styles.doneButton}
          onClick={(e) => {
            e.stopPropagation();
            handleActionClick(action);
          }}
        >
          ✓
        </button>
      );
    }
  };

  const handleLearningToggle = () => {
    if (isRunning) {
      onStop();
    } else {
      onStart();
    }
  };

  const getContainerStyle = () => {
    const baseStyle = {
      ...styles.container,
      transition: 'width 0.5s cubic-bezier(0.4, 0, 0.2, 1), height 0.5s cubic-bezier(0.4, 0, 0.2, 1), border-radius 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
    };

    if (viewState === 'collapsed') {
      return {
        ...baseStyle,
        width: '60px',
        height: '60px',
        borderRadius: '30px',
      };
    } else if (viewState === 'prompt') {
      return {
        ...baseStyle,
        width: '400px',
        height: '100px',
        borderRadius: '20px',
      };
    } else {
      return {
        ...baseStyle,
        width: '500px',
        height: '400px',
        borderRadius: '24px',
      };
    }
  };

  return (
    <div style={getContainerStyle()}>
        {/* Icon - always visible in corner */}
        <div style={styles.iconContainer}>
          <img 
            src="/icon.png" 
            alt="Covalent" 
            style={styles.icon}
            onClick={handleIconClick}
          />
        </div>

      {/* Prompt State */}
      {viewState === 'prompt' && (
        <div style={styles.promptContent}>
          <span style={styles.promptText}>Want help with this?</span>
          <div style={styles.promptButtons}>
            <button 
              style={styles.acceptButton}
              onClick={handleAccept}
              onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.35)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.25)';
              }}
            >
              ✓
            </button>
            <button 
              style={styles.rejectButton}
              onClick={handleReject}
              onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.35)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.25)';
              }}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Expanded State */}
      {viewState === 'expanded' && (
        <div style={styles.expandedContent}>
          <div style={styles.expandedHeader}>
            <h3 style={styles.expandedTitle}>Suggested Actions</h3>
            <button
              style={{
                ...styles.learningButton,
                ...(isRunning ? styles.stopButton : styles.startButton)
              }}
              onClick={handleLearningToggle}
            >
              {isRunning ? 'Stop Learning' : 'Restart Learning'}
            </button>
          </div>
          <div style={styles.actionsList}>
            {actions.map((action) => {
              const isHovered = hoveredActionId === action.id;
              return (
                <div 
                  key={action.id} 
                  style={{
                    ...styles.actionItem,
                    maxHeight: isHovered ? '300px' : '60px',
                    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                    overflow: 'hidden',
                  }}
                  onMouseEnter={() => setHoveredActionId(action.id)}
                  onMouseLeave={() => setHoveredActionId(null)}
                >
                  <div style={styles.actionText}>
                    <h4 style={styles.actionTitle}>{action.title}</h4>
                    <p style={{
                      ...styles.actionDescription,
                      maxHeight: isHovered ? '200px' : '0px',
                      opacity: isHovered ? 1 : 0,
                      transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                      overflow: 'hidden',
                    }}>
                      {action.description}
                    </p>
                  </div>
                  {renderActionButton(action)}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
});

FloatingAssistant.displayName = 'FloatingAssistant';

const styles = {
  container: {
    position: 'fixed' as const,
    top: '20px',
    left: '20px',
    backgroundColor: 'rgba(66, 66, 66, 0.65)',
    backdropFilter: 'blur(60px) saturate(180%)',
    WebkitBackdropFilter: 'blur(60px) saturate(180%)',
    border: 'none',
    boxShadow: '0 2px 12px rgba(0, 0, 0, 0.02), 0 1px 0 rgba(255, 255, 255, 0.05) inset',
    overflow: 'hidden',
    zIndex: 999,
    outline: 'none',
    willChange: 'transform, opacity',
    transform: 'translateZ(0)',
    WebkitTransform: 'translateZ(0)',
  },
  iconContainer: {
    position: 'absolute' as const,
    top: '10px',
    left: '10px',
    width: '40px',
    height: '40px',
    cursor: 'pointer',
    zIndex: 10,
  },
  icon: {
    width: '100%',
    height: '100%',
    objectFit: 'contain' as const,
  },
  promptContent: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 20px 0 60px',
    height: '100%',
    width: '100%',
  },
  promptText: {
    fontSize: '1rem',
    fontWeight: '600',
    color: 'rgba(255, 255, 255, 0.95)',
    flex: 1,
  },
  promptButtons: {
    display: 'flex',
    gap: '0.75rem',
    marginLeft: 'auto',
  },
  acceptButton: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    border: '2px solid rgba(34, 197, 94, 0.6)',
    backgroundColor: 'rgba(34, 197, 94, 0.25)',
    color: '#16a34a',
    fontSize: '1.2rem',
    fontWeight: 'bold',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rejectButton: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    border: '2px solid rgba(239, 68, 68, 0.6)',
    backgroundColor: 'rgba(239, 68, 68, 0.25)',
    color: '#dc2626',
    fontSize: '1.2rem',
    fontWeight: 'bold',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  expandedContent: {
    display: 'flex',
    flexDirection: 'column' as const,
    padding: '60px 1.5rem 1.5rem',
    height: '100%',
  },
  expandedHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '1rem',
  },
  expandedTitle: {
    fontSize: '1.2rem',
    fontWeight: '600',
    color: 'rgba(255, 255, 255, 0.95)',
    margin: 0,
  },
  learningButton: {
    padding: '0.5rem 1.2rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '16px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    border: 'none',
    color: '#ffffff',
  },
  startButton: {
    backgroundColor: 'rgba(22, 163, 74, 0.45)',
    border: '2px solid rgba(22, 163, 74, 0.8)',
  },
  stopButton: {
    backgroundColor: 'rgba(220, 38, 38, 0.45)',
    border: '2px solid rgba(220, 38, 38, 0.8)',
  },
  actionsList: {
    flex: 1,
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.75rem',
  },
  actionItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '0.75rem',
    padding: '1rem',
    backgroundColor: 'rgba(80, 80, 80, 0.4)',
    backdropFilter: 'blur(40px)',
    WebkitBackdropFilter: 'blur(40px)',
    borderRadius: '16px',
    border: '1px solid rgba(255, 255, 255, 0.15)',
  },
  actionText: {
    flex: 1,
  },
  actionTitle: {
    fontSize: '0.95rem',
    fontWeight: '600',
    color: 'rgba(255, 255, 255, 0.95)',
    margin: '0 0 0.25rem 0',
  },
  actionDescription: {
    fontSize: '0.8rem',
    color: 'rgba(255, 255, 255, 0.75)',
    margin: 0,
    lineHeight: '1.4',
  },
  playButton: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    border: '1px solid rgba(255, 255, 255, 0.3)',
    backgroundColor: 'rgba(100, 100, 100, 0.45)',
    color: '#ffffff',
    fontSize: '0.8rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  loadingButton: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    border: '2px solid rgba(147, 51, 234, 0.4)',
    backgroundColor: 'rgba(147, 51, 234, 0.15)',
    color: '#9333ea',
    fontSize: '1rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  doneButton: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    border: '2px solid rgba(34, 197, 94, 0.6)',
    backgroundColor: 'rgba(34, 197, 94, 0.25)',
    color: '#16a34a',
    fontSize: '1.1rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  loadingDots: {
    display: 'inline-flex',
    gap: '1px',
  },
  dot1: {
    animation: 'dotFade 1.4s infinite',
    animationDelay: '0s',
  },
  dot2: {
    animation: 'dotFade 1.4s infinite',
    animationDelay: '0.2s',
  },
  dot3: {
    animation: 'dotFade 1.4s infinite',
    animationDelay: '0.4s',
  },
};

export default FloatingAssistant;

