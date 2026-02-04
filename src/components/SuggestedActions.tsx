import React, { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { disableContextCollection, enableContextCollection } from '../utils/contextControl';

export interface Action {
  id: string;
  uuid: string;           // Action UUID from database
  title: string;          // action_name from backend
  description: string;    // action_plan from backend
  action_prompt: string;  // action_prompt from backend (sent when triggering)
  node_uuid?: string;     // Optional: node this action belongs to
  node_metadata?: string; // Optional: metadata of the node
}

interface SuggestedActionsProps {
  actions: Action[];
}

type ActionStatus = 'idle' | 'playing' | 'done' | 'error';

const SuggestedActions: React.FC<SuggestedActionsProps> = ({ actions }) => {
  const [actionStatuses, setActionStatuses] = useState<Record<string, ActionStatus>>({});
  const [editingAction, setEditingAction] = useState<Action | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editPlan, setEditPlan] = useState('');
  const [editPrompt, setEditPrompt] = useState('');
  const [editPersist, setEditPersist] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const handleActionClick = async (action: Action) => {
    const currentStatus = actionStatuses[action.id] || 'idle';
    
    if (currentStatus === 'idle') {
      // Start playing - trigger the action via Tauri
      setActionStatuses({ ...actionStatuses, [action.id]: 'playing' });
      
      try {
        console.log(`🎬 Triggering action: ${action.title} (${action.uuid})`);
        
        // Call the Tauri command to trigger the action with action_prompt
        await invoke('trigger_action', {
          actionUuid: action.uuid,
          actionPrompt: action.action_prompt,
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

  const openEditModal = async (action: Action) => {
    setEditingAction(action);
    setEditTitle(action.title);
    setEditPlan(action.description);
    setEditPrompt(action.action_prompt);
    setEditPersist(false);
    setEditError(null);
    await disableContextCollection();
  };

  const closeEditModal = async (shouldResume: boolean) => {
    setEditingAction(null);
    setEditError(null);
    if (shouldResume) {
      await enableContextCollection();
    }
  };

  const handleRunEditedAction = async () => {
    if (!editingAction) {
      return;
    }
    if (!editPrompt.trim()) {
      setEditError('Prompt is required.');
      return;
    }

    try {
      await invoke('edit_action', {
        actionUuid: editingAction.uuid,
        actionName: editTitle,
        actionPlan: editPlan,
        actionPrompt: editPrompt,
        persist: editPersist,
      });

      await invoke('trigger_action_with_override', {
        actionUuid: editingAction.uuid,
        actionName: editTitle,
        actionPlan: editPlan,
        actionPrompt: editPrompt,
      });

      await closeEditModal(false);
    } catch (error) {
      console.error('Failed to run edited action:', error);
      setEditError('Failed to run edited action. Please try again.');
    }
  };

  const renderActionButton = (action: Action) => {
    const status = actionStatuses[action.id] || 'idle';
    
    if (status === 'idle') {
      return (
        <div style={styles.actionButtons}>
          <button 
            style={styles.editButton}
            onClick={() => openEditModal(action)}
          >
            Edit
          </button>
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
        </div>
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

      {editingAction && (
        <div style={styles.modalOverlay}>
          <div style={styles.modal}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>Edit Action</h3>
              <button style={styles.modalClose} onClick={() => closeEditModal(true)}>
                ✕
              </button>
            </div>
            <div style={styles.modalBody}>
              <label style={styles.modalLabel}>
                Title
                <input
                  style={styles.modalInput}
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </label>
              <label style={styles.modalLabel}>
                Plan / Description
                <textarea
                  style={styles.modalTextarea}
                  value={editPlan}
                  onChange={(e) => setEditPlan(e.target.value)}
                  rows={3}
                />
              </label>
              <label style={styles.modalLabel}>
                Prompt
                <textarea
                  style={styles.modalTextarea}
                  value={editPrompt}
                  onChange={(e) => setEditPrompt(e.target.value)}
                  rows={5}
                />
              </label>
              <label style={styles.modalCheckboxLabel}>
                <input
                  type="checkbox"
                  checked={editPersist}
                  onChange={(e) => setEditPersist(e.target.checked)}
                />
                Save changes to future recommendations
              </label>
              {editError && <div style={styles.modalError}>{editError}</div>}
            </div>
            <div style={styles.modalActions}>
              <button style={styles.modalCancel} onClick={() => closeEditModal(true)}>
                Cancel
              </button>
              <button style={styles.modalRun} onClick={handleRunEditedAction}>
                Run now
              </button>
            </div>
          </div>
        </div>
      )}
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
  actionButtons: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  editButton: {
    padding: '0.4rem 0.75rem',
    borderRadius: '999px',
    border: '1px solid rgba(100, 100, 100, 0.4)',
    backgroundColor: 'rgba(255, 255, 255, 0.25)',
    color: '#000000',
    fontSize: '0.8rem',
    cursor: 'pointer',
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
  modalOverlay: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(15, 23, 42, 0.35)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    padding: '1.5rem',
  },
  modal: {
    width: '640px',
    maxWidth: '94vw',
    maxHeight: '85vh',
    backgroundColor: 'rgba(255, 255, 255, 0.75)',
    borderRadius: '24px',
    padding: '1.25rem 1.25rem 1rem',
    boxShadow: '0 30px 80px rgba(15, 23, 42, 0.35)',
    border: '1px solid rgba(255, 255, 255, 0.6)',
    backdropFilter: 'blur(28px) saturate(160%)',
    WebkitBackdropFilter: 'blur(28px) saturate(160%)',
    display: 'flex',
    flexDirection: 'column' as const,
  },
  modalHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '0.75rem',
  },
  modalTitle: {
    margin: 0,
    fontSize: '1.35rem',
    fontWeight: '600',
    color: '#0f172a',
  },
  modalClose: {
    border: 'none',
    backgroundColor: 'rgba(15, 23, 42, 0.08)',
    color: '#0f172a',
    width: '32px',
    height: '32px',
    borderRadius: '12px',
    cursor: 'pointer',
    fontSize: '0.9rem',
  },
  modalBody: {
    overflowY: 'auto' as const,
    paddingRight: '0.25rem',
  },
  modalLabel: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.4rem',
    marginBottom: '0.8rem',
    fontSize: '0.85rem',
    color: '#0f172a',
  },
  modalInput: {
    padding: '0.5rem 0.6rem',
    borderRadius: '12px',
    border: '1px solid rgba(148, 163, 184, 0.5)',
    fontSize: '0.9rem',
    backgroundColor: 'rgba(255, 255, 255, 0.7)',
  },
  modalTextarea: {
    padding: '0.5rem 0.6rem',
    borderRadius: '12px',
    border: '1px solid rgba(148, 163, 184, 0.5)',
    fontSize: '0.9rem',
    resize: 'vertical' as const,
    backgroundColor: 'rgba(255, 255, 255, 0.7)',
    minHeight: '90px',
  },
  modalCheckboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: '0.85rem',
    color: '#0f172a',
    marginBottom: '0.8rem',
  },
  modalActions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '0.75rem',
    marginTop: '0.8rem',
    paddingTop: '0.5rem',
    borderTop: '1px solid rgba(148, 163, 184, 0.25)',
  },
  modalCancel: {
    padding: '0.5rem 0.9rem',
    borderRadius: '999px',
    border: '1px solid rgba(148, 163, 184, 0.6)',
    backgroundColor: 'rgba(255, 255, 255, 0.7)',
    cursor: 'pointer',
  },
  modalRun: {
    padding: '0.5rem 0.9rem',
    borderRadius: '999px',
    border: '1px solid rgba(15, 23, 42, 0.25)',
    backgroundColor: 'rgba(15, 23, 42, 0.9)',
    color: '#f8fafc',
    cursor: 'pointer',
  },
  modalError: {
    color: '#b91c1c',
    fontSize: '0.85rem',
  },
};

export default SuggestedActions;
