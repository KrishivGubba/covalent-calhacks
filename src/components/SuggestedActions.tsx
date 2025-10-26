import React, { useState } from 'react';

export interface Action {
  id: string;
  title: string;
  description: string;
}

interface SuggestedActionsProps {
  actions: Action[];
}

type ActionStatus = 'idle' | 'playing' | 'done';

const SuggestedActions: React.FC<SuggestedActionsProps> = ({ actions }) => {
  const [actionStatuses, setActionStatuses] = useState<Record<string, ActionStatus>>({});

  const handleActionClick = (actionId: string) => {
    const currentStatus = actionStatuses[actionId] || 'idle';
    
    if (currentStatus === 'idle') {
      // Start playing
      setActionStatuses({ ...actionStatuses, [actionId]: 'playing' });
      // Simulate completion after 3 seconds
      setTimeout(() => {
        setActionStatuses(prev => ({ ...prev, [actionId]: 'done' }));
      }, 3000);
    } else if (currentStatus === 'playing') {
      // Pause/reset
      setActionStatuses({ ...actionStatuses, [actionId]: 'idle' });
    } else if (currentStatus === 'done') {
      // Reset from done state
      setActionStatuses({ ...actionStatuses, [actionId]: 'idle' });
    }
  };

  const renderActionButton = (actionId: string) => {
    const status = actionStatuses[actionId] || 'idle';
    
    if (status === 'idle') {
      return (
        <button 
          style={styles.playButton}
          onClick={() => handleActionClick(actionId)}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(59, 130, 246, 0.25)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(59, 130, 246, 0.15)';
          }}
        >
          ▶
        </button>
      );
    } else if (status === 'playing') {
      return (
        <button 
          style={styles.loadingButton}
          onClick={() => handleActionClick(actionId)}
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
          onClick={() => handleActionClick(actionId)}
        >
          ✓
        </button>
      );
    }
  };

  return (
    <div style={styles.container}>
      <h2 style={styles.heading}>Looks like you could use some help with...</h2>
      <div style={styles.actionsContainer}>
        {actions.length === 0 ? (
          <p style={styles.emptyState}>No actions at the moment</p>
        ) : (
          actions.map((action) => (
            <div 
              key={action.id} 
              style={styles.actionCard}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.35)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.18)';
              }}
            >
              <div style={styles.actionContent}>
                <div style={styles.actionText}>
                  <h3 style={styles.actionTitle}>{action.title}</h3>
                  <p style={styles.actionDescription}>{action.description}</p>
                </div>
                {renderActionButton(action.id)}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

const styles = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    padding: '2rem',
    overflow: 'hidden',
  },
  heading: {
    fontSize: '1.75rem',
    fontWeight: '600',
    marginBottom: '1.5rem',
    color: '#000000',
    textAlign: 'center' as const,
    letterSpacing: '-0.02em',
    textShadow: '0 1px 2px rgba(255, 255, 255, 0.3)',
  },
  actionsContainer: {
    flex: 1,
    overflowY: 'auto' as const,
    borderRadius: '32px',
    padding: '1.5rem',
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
    backdropFilter: 'blur(40px) saturate(180%)',
    WebkitBackdropFilter: 'blur(40px) saturate(180%)',
    border: '1px solid rgba(255, 255, 255, 0.3)',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.6)',
  },
  actionCard: {
    padding: '1.25rem 1.5rem',
    marginBottom: '1rem',
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
    backdropFilter: 'blur(30px) saturate(180%)',
    WebkitBackdropFilter: 'blur(30px) saturate(180%)',
    borderRadius: '20px',
    border: '1px solid rgba(255, 255, 255, 0.4)',
    boxShadow: '0 4px 24px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.7)',
    transition: 'all 0.3s ease',
  },
  actionContent: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
  },
  actionText: {
    flex: 1,
  },
  actionTitle: {
    fontSize: '1.1rem',
    fontWeight: '600',
    marginBottom: '0.5rem',
    color: '#000000',
    textShadow: '0 1px 2px rgba(255, 255, 255, 0.3)',
  },
  actionDescription: {
    fontSize: '0.95rem',
    color: '#1e293b',
    lineHeight: '1.6',
    margin: 0,
    textShadow: '0 1px 2px rgba(255, 255, 255, 0.2)',
  },
  playButton: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    border: '2px solid rgba(59, 130, 246, 0.4)',
    backgroundColor: 'rgba(59, 130, 246, 0.15)',
    color: '#3b82f6',
    fontSize: '0.9rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    flexShrink: 0,
  },
  loadingButton: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    border: '2px solid rgba(147, 51, 234, 0.4)',
    backgroundColor: 'rgba(147, 51, 234, 0.15)',
    color: '#9333ea',
    fontSize: '1.2rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    flexShrink: 0,
  },
  doneButton: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    border: '2px solid rgba(34, 197, 94, 0.5)',
    backgroundColor: 'rgba(34, 197, 94, 0.2)',
    color: '#22c55e',
    fontSize: '1.3rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
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
  emptyState: {
    textAlign: 'center' as const,
    color: '#334155',
    fontSize: '1rem',
    padding: '3rem',
    textShadow: '0 1px 2px rgba(255, 255, 255, 0.2)',
  },
};

export default SuggestedActions;
