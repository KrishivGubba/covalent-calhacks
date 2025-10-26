import React, { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

export interface Action {
  id: string;
  uuid: string;  // Action UUID from database
  title: string;
  description: string;
  node_uuid?: string;  // Optional: node this action belongs to
  node_metadata?: string;  // Optional: metadata of the node
}

interface SuggestedActionsProps {
  actions: Action[];
}

type ActionStatus = 'idle' | 'playing' | 'done' | 'error';

const SuggestedActions: React.FC<SuggestedActionsProps> = ({ actions }) => {
  const [actionStatuses, setActionStatuses] = useState<Record<string, ActionStatus>>({});

  const handleActionClick = async (action: Action) => {
    const currentStatus = actionStatuses[action.id] || 'idle';
    
    if (currentStatus === 'idle') {
      // Start playing - trigger the action via Tauri
      setActionStatuses({ ...actionStatuses, [action.id]: 'playing' });
      
      try {
        console.log(`🎬 Triggering action: ${action.description} (${action.uuid})`);
        
        // Call the Tauri command to trigger the action
        await invoke('trigger_action', {
          actionUuid: action.uuid,
          actionDescription: action.description,
        });
        
        console.log(`✅ Action completed successfully`);
        setActionStatuses(prev => ({ ...prev, [action.id]: 'done' }));
      } catch (error) {
        console.error(`❌ Action failed:`, error);
        setActionStatuses(prev => ({ ...prev, [action.id]: 'error' }));
        
        // Reset to idle after 3 seconds on error
        setTimeout(() => {
          setActionStatuses(prev => ({ ...prev, [action.id]: 'idle' }));
        }, 3000);
      }
    } else if (currentStatus === 'playing') {
      // Can't pause/reset while playing
      console.log('⏸️  Action is already executing');
    } else if (currentStatus === 'done' || currentStatus === 'error') {
      // Reset from done/error state
      setActionStatuses({ ...actionStatuses, [action.id]: 'idle' });
    }
  };

  const renderActionButton = (action: Action) => {
    const status = actionStatuses[action.id] || 'idle';
    
    if (status === 'idle') {
      return (
        <button 
          style={styles.playButton}
          onClick={() => handleActionClick(action)}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(255, 255, 255, 0.35)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(255, 255, 255, 0.25)';
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
    } else if (status === 'done') {
      return (
        <button 
          style={styles.doneButton}
          onClick={() => handleActionClick(action)}
        >
          ✓
        </button>
      );
    } else {
      // error state
      return (
        <button 
          style={styles.errorButton}
          onClick={() => handleActionClick(action)}
        >
          ✗
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
                {renderActionButton(action)}
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
    border: '2px solid rgba(100, 100, 100, 0.4)',
    backgroundColor: 'rgba(255, 255, 255, 0.25)',
    color: '#000000',
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
  errorButton: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    border: '2px solid rgba(239, 68, 68, 0.5)',
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    color: '#ef4444',
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
