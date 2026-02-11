import React, { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { disableContextCollection, enableContextCollection, enableContextCollectionIfNotUserPaused } from '../utils/contextControl';

export interface Action {
  id: string;
  uuid: string;           // Action UUID from database
  title: string;          // action_name from backend
  description: string;    // action_plan from backend (contains full context for execution)
  node_uuid?: string;     // Optional: node this action belongs to
  node_metadata?: string; // Optional: metadata of the node
}

// Action plan returned from /plan_action endpoint
export interface ActionPlan {
  status: string;
  action_text: string;
  context_data: string;
  proposed_action?: {
    tool_name: string;
    parameters: Record<string, unknown>;
    reasoning?: string;
  };
  display?: {
    display_name: string;
    description: string;
    fields: Array<{
      key: string;
      label: string;
      source: string;
      editable: boolean;
      widget: string;
      required: boolean;
      value: unknown;
    }>;
    has_schema: boolean;
  };
  research?: {
    resources_read: string[];
    context_gathered: string;
  };
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
  const [editPersist, setEditPersist] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  
  // New action plan confirmation state
  const [planningAction, setPlanningAction] = useState<Action | null>(null);
  const [actionPlan, setActionPlan] = useState<ActionPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [editableParams, setEditableParams] = useState<Record<string, unknown>>({});
  const [isExecuting, setIsExecuting] = useState(false);

  const handleActionClick = async (action: Action) => {
    const currentStatus = actionStatuses[action.id] || 'idle';
    
    if (currentStatus === 'idle') {
      // Start planning - call plan_action to get the action plan
      setActionStatuses({ ...actionStatuses, [action.id]: 'playing' });
      setPlanningAction(action);
      setPlanError(null);
      setActionPlan(null);
      
      try {
        console.log(`📋 Planning action: ${action.title} (${action.uuid})`);
        
        // Call the Tauri command to plan the action
        const plan = await invoke<ActionPlan>('plan_action', {
          actionUuid: action.uuid,
          actionOverride: null,
        });
        
        console.log(`✅ Action plan received:`, plan);
        setActionPlan(plan);
        
        // Initialize editable params from the plan
        if (plan.proposed_action?.parameters) {
          setEditableParams({ ...plan.proposed_action.parameters });
        }
        
        // Keep status as 'playing' until user confirms or cancels
      } catch (error) {
        console.error(`❌ Action planning failed:`, error);
        setPlanError(String(error));
        setActionStatuses(prev => ({ ...prev, [action.id]: 'error' }));
        setPlanningAction(null);
        
        // Re-enable context collection on error (only if not user-paused)
        await enableContextCollectionIfNotUserPaused();
        
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

  const handleExecuteAction = async () => {
    if (!planningAction || !actionPlan?.proposed_action) {
      return;
    }
    
    setIsExecuting(true);
    setPlanError(null);
    
    try {
      console.log(`🚀 Executing action: ${planningAction.title}`);
      console.log(`   Tool: ${actionPlan.proposed_action.tool_name}`);
      console.log(`   Parameters:`, editableParams);
      
      await invoke('execute_action', {
        actionUuid: planningAction.uuid,
        toolName: actionPlan.proposed_action.tool_name,
        parameters: editableParams,
      });
      
      console.log(`✅ Action executed successfully`);
      setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'done' }));
    } catch (error) {
      console.error(`❌ Action execution failed:`, error);
      setPlanError(String(error));
      setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'error' }));
    } finally {
      setIsExecuting(false);
      setPlanningAction(null);
      setActionPlan(null);
      setEditableParams({});
    }
  };

  const handleCancelPlan = async () => {
    if (planningAction) {
      setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'idle' }));
    }
    setPlanningAction(null);
    setActionPlan(null);
    setPlanError(null);
    setEditableParams({});
    await enableContextCollectionIfNotUserPaused();
  };

  const handleParamChange = (key: string, value: unknown) => {
    setEditableParams(prev => ({ ...prev, [key]: value }));
  };

  const openEditModal = async (action: Action) => {
    setEditingAction(action);
    setEditTitle(action.title);
    setEditPlan(action.description);
    setEditPersist(false);
    setEditError(null);
    await disableContextCollection();
  };

  const closeEditModal = async (shouldResume: boolean) => {
    setEditingAction(null);
    setEditError(null);
    if (shouldResume) {
      await enableContextCollectionIfNotUserPaused();
    }
  };

  const handleRunEditedAction = async () => {
    if (!editingAction) {
      return;
    }
    if (!editPlan.trim()) {
      setEditError('Plan is required.');
      return;
    }

    try {
      // Save the edit if persist is enabled
      if (editPersist) {
        await invoke('edit_action', {
          actionUuid: editingAction.uuid,
          actionName: editTitle,
          actionPlan: editPlan,
          persist: editPersist,
        });
      }

      // Close the edit modal and open the plan flow
      await closeEditModal(false);
      
      // Trigger the action with the edited plan
      const updatedAction = { ...editingAction, title: editTitle, description: editPlan };
      setActionStatuses(prev => ({ ...prev, [editingAction.id]: 'playing' }));
      setPlanningAction(updatedAction);
      setPlanError(null);
      setActionPlan(null);
      
      // Plan the action with override
      const plan = await invoke<ActionPlan>('plan_action', {
        actionUuid: editingAction.uuid,
        actionOverride: {
          action_name: editTitle,
          action_plan: editPlan,
        },
      });
      
      setActionPlan(plan);
      if (plan.proposed_action?.parameters) {
        setEditableParams({ ...plan.proposed_action.parameters });
      }
    } catch (error) {
      console.error('Failed to run edited action:', error);
      setEditError('Failed to run edited action. Please try again.');
      await enableContextCollectionIfNotUserPaused();
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

      {/* Edit Action Modal */}
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

      {/* Action Plan Confirmation Modal */}
      {planningAction && actionPlan && (
        <div style={styles.modalOverlay}>
          <div style={styles.planModal}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>
                {actionPlan.display?.display_name || actionPlan.proposed_action?.tool_name || 'Confirm Action'}
              </h3>
              <button style={styles.modalClose} onClick={handleCancelPlan}>
                ✕
              </button>
            </div>
            <div style={styles.planModalBody}>
              {/* Tool description */}
              {actionPlan.display?.description && (
                <p style={styles.planDescription}>{actionPlan.display.description}</p>
              )}
              
              {/* Reasoning from the agent */}
              {actionPlan.proposed_action?.reasoning && (
                <div style={styles.reasoningBox}>
                  <strong>Action Plan:</strong> {actionPlan.proposed_action.reasoning}
                </div>
              )}

              {/* Editable parameters */}
              <div style={styles.paramsSection}>
                <h4 style={styles.paramsSectionTitle}>Parameters</h4>
                {actionPlan.display?.fields ? (
                  actionPlan.display.fields.map((field) => (
                    <label key={field.key} style={styles.modalLabel}>
                      {field.label} {field.required && <span style={{ color: '#ef4444' }}></span>}
                      {field.widget === 'textarea' || (typeof editableParams[field.key] === 'string' && String(editableParams[field.key]).length > 100) ? (
                        <textarea
                          style={styles.modalTextarea}
                          value={String(editableParams[field.key] ?? field.value ?? '')}
                          onChange={(e) => handleParamChange(field.key, e.target.value)}
                          disabled={!field.editable}
                          rows={4}
                        />
                      ) : (
                        <input
                          style={styles.modalInput}
                          value={String(editableParams[field.key] ?? field.value ?? '')}
                          onChange={(e) => handleParamChange(field.key, e.target.value)}
                          disabled={!field.editable}
                        />
                      )}
                    </label>
                  ))
                ) : (
                  // Fallback: render all parameters as editable fields
                  Object.entries(editableParams).map(([key, value]) => (
                    <label key={key} style={styles.modalLabel}>
                      {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      {typeof value === 'string' && value.length > 100 ? (
                        <textarea
                          style={styles.modalTextarea}
                          value={String(value)}
                          onChange={(e) => handleParamChange(key, e.target.value)}
                          rows={4}
                        />
                      ) : (
                        <input
                          style={styles.modalInput}
                          value={String(value ?? '')}
                          onChange={(e) => handleParamChange(key, e.target.value)}
                        />
                      )}
                    </label>
                  ))
                )}
              </div>

              {planError && <div style={styles.modalError}>{planError}</div>}
            </div>
            <div style={styles.planModalActions}>
              <button 
                style={styles.exitButton} 
                onClick={handleCancelPlan}
                disabled={isExecuting}
              >
                Exit
              </button>
              <button 
                style={styles.executeButton} 
                onClick={handleExecuteAction}
                disabled={isExecuting}
              >
                {isExecuting ? 'Executing...' : 'Execute'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Loading state while planning */}
      {planningAction && !actionPlan && !planError && (
        <div style={styles.modalOverlay}>
          <div style={styles.loadingModal}>
            <div style={styles.loadingSpinner}>
              <span style={styles.dot1}>.</span>
              <span style={styles.dot2}>.</span>
              <span style={styles.dot3}>.</span>
            </div>
            <p style={styles.loadingText}>Planning action...</p>
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
  // Action Plan Confirmation Modal styles
  planModal: {
    width: '700px',
    maxWidth: '94vw',
    maxHeight: '85vh',
    backgroundColor: 'rgba(255, 255, 255, 0.85)',
    borderRadius: '24px',
    padding: '1.25rem 1.25rem 1rem',
    boxShadow: '0 30px 80px rgba(15, 23, 42, 0.35)',
    border: '1px solid rgba(255, 255, 255, 0.6)',
    backdropFilter: 'blur(28px) saturate(160%)',
    WebkitBackdropFilter: 'blur(28px) saturate(160%)',
    display: 'flex',
    flexDirection: 'column' as const,
  },
  planModalBody: {
    overflowY: 'auto' as const,
    paddingRight: '0.25rem',
    flex: 1,
  },
  planDescription: {
    fontSize: '0.9rem',
    color: '#475569',
    marginBottom: '1rem',
    lineHeight: '1.5',
  },
  reasoningBox: {
    backgroundColor: 'rgba(255, 255, 255, 0.3)',
    border: '1px solid rgba(255, 255, 255, 0.4)',
    borderRadius: '12px',
    padding: '0.75rem 1rem',
    marginBottom: '1rem',
    fontSize: '0.85rem',
    color: '#0f172a',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
  },
  paramsSection: {
    marginTop: '0.5rem',
  },
  paramsSectionTitle: {
    fontSize: '0.95rem',
    fontWeight: '600',
    color: '#0f172a',
    marginBottom: '0.75rem',
  },
  planModalActions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '0.75rem',
    marginTop: '1rem',
    paddingTop: '0.75rem',
    borderTop: '1px solid rgba(148, 163, 184, 0.25)',
  },
  exitButton: {
    padding: '0.6rem 1.5rem',
    borderRadius: '999px',
    border: '2px solid rgba(239, 68, 68, 0.6)',
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    color: '#dc2626',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  executeButton: {
    padding: '0.6rem 1.5rem',
    borderRadius: '999px',
    border: '2px solid rgba(34, 197, 94, 0.6)',
    backgroundColor: 'rgba(34, 197, 94, 0.2)',
    color: '#16a34a',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  loadingModal: {
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
    borderRadius: '20px',
    padding: '2rem 3rem',
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 20px 60px rgba(15, 23, 42, 0.25)',
    border: '1px solid rgba(255, 255, 255, 0.6)',
    backdropFilter: 'blur(28px)',
    WebkitBackdropFilter: 'blur(28px)',
  },
  loadingSpinner: {
    fontSize: '2rem',
    color: '#9333ea',
    marginBottom: '0.5rem',
  },
  loadingText: {
    fontSize: '0.95rem',
    color: '#475569',
  },
};

export default SuggestedActions;
