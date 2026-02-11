import React, { useState, useEffect, memo } from 'react';
import { invoke } from '@tauri-apps/api/core';
import type { Action, ActionPlan } from './SuggestedActions';
import { disableContextCollection, enableContextCollection, enableContextCollectionIfNotUserPaused } from '../utils/contextControl';

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
      setPlanningAction(action);
      setPlanError(null);
      setActionPlan(null);
      
      try {
        console.log(`📋 Planning action: ${action.title} (${action.uuid})`);
        
        const plan = await invoke<ActionPlan>('plan_action', {
          actionUuid: action.uuid,
          actionOverride: null,
        });
        
        console.log(`✅ Action plan received:`, plan);
        setActionPlan(plan);
        
        if (plan.proposed_action?.parameters) {
          setEditableParams({ ...plan.proposed_action.parameters });
        }
      } catch (error) {
        console.error(`❌ Action planning failed:`, error);
        setPlanError(String(error));
        setActionStatuses(prev => ({ ...prev, [action.id]: 'idle' }));
        setPlanningAction(null);
        await enableContextCollectionIfNotUserPaused();
      }
    } else if (currentStatus === 'playing') {
      console.log('⏸️  Action is already executing');
    } else if (currentStatus === 'done') {
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
      setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'idle' }));
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

  const renderActionButton = (action: Action) => {
    const status = actionStatuses[action.id] || 'idle';
    
    if (status === 'idle') {
      return (
        <div style={styles.actionButtons}>
          <button 
            style={styles.editButton}
            onClick={(e) => {
              e.stopPropagation();
              openEditModal(action);
            }}
          >
            Edit
          </button>
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
      if (editPersist) {
        await invoke('edit_action', {
          actionUuid: editingAction.uuid,
          actionName: editTitle,
          actionPlan: editPlan,
          persist: editPersist,
        });
      }

      await closeEditModal(false);
      
      // Trigger the action with the edited plan
      const updatedAction = { ...editingAction, title: editTitle, description: editPlan };
      setActionStatuses(prev => ({ ...prev, [editingAction.id]: 'playing' }));
      setPlanningAction(updatedAction);
      setPlanError(null);
      setActionPlan(null);
      
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
              {isRunning ? 'Pause Covalent' : 'Resume Covalent'}
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

      {/* Edit Action Modal */}
      {editingAction && (
        <div style={styles.modalOverlay}>
          <div style={styles.modal}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>Edit Action</h3>
              <button 
                style={styles.modalClose} 
                onClick={() => closeEditModal(true)}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#27272a';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = '#1a1a1a';
                }}
              >
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
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor = '#3f3f46';
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor = '#27272a';
                  }}
                />
              </label>
              <label style={styles.modalLabel}>
                Plan / Description
                <textarea
                  style={styles.modalTextarea}
                  value={editPlan}
                  onChange={(e) => setEditPlan(e.target.value)}
                  rows={5}
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor = '#3f3f46';
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor = '#27272a';
                  }}
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
              <button 
                style={styles.modalCancel} 
                onClick={() => closeEditModal(true)}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#27272a';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = '#1a1a1a';
                }}
              >
                Cancel
              </button>
              <button 
                style={styles.modalRun} 
                onClick={handleRunEditedAction}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = '0.9';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = '1';
                }}
              >
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
              {actionPlan.display?.description && (
                <p style={styles.planDescription}>{actionPlan.display.description}</p>
              )}
              
              {actionPlan.proposed_action?.reasoning && (
                <div style={styles.reasoningBox}>
                  <strong>Reasoning:</strong> {actionPlan.proposed_action.reasoning}
                </div>
              )}

              <div style={styles.paramsSection}>
                <h4 style={styles.paramsSectionTitle}>Parameters</h4>
                {actionPlan.display?.fields ? (
                  actionPlan.display.fields.map((field) => (
                    <label key={field.key} style={styles.modalLabel}>
                      {field.label} {field.required && <span style={{ color: '#ef4444' }}>*</span>}
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
  actionButtons: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  editButton: {
    padding: '0.35rem 0.7rem',
    borderRadius: '999px',
    border: '1px solid rgba(100, 100, 100, 0.4)',
    backgroundColor: 'rgba(120, 120, 120, 0.35)',
    color: '#ffffff',
    fontSize: '0.75rem',
    cursor: 'pointer',
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
  modalOverlay: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    backdropFilter: 'blur(8px)',
    WebkitBackdropFilter: 'blur(8px)',
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
    backgroundColor: '#141414',
    borderRadius: '16px',
    padding: '1.5rem',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
    border: '1px solid #27272a',
    display: 'flex',
    flexDirection: 'column' as const,
  },
  modalHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '1.25rem',
  },
  modalTitle: {
    margin: 0,
    fontSize: '1.35rem',
    fontWeight: 600,
    color: '#ffffff',
    letterSpacing: '-0.01em',
  },
  modalClose: {
    border: 'none',
    backgroundColor: '#1a1a1a',
    color: '#a1a1aa',
    width: '36px',
    height: '36px',
    borderRadius: '10px',
    cursor: 'pointer',
    fontSize: '1rem',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalBody: {
    overflowY: 'auto' as const,
    paddingRight: '0.25rem',
  },
  modalLabel: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
    marginBottom: '1rem',
    fontSize: '0.9rem',
    fontWeight: '500',
    color: '#ffffff',
  },
  modalInput: {
    padding: '10px 14px',
    borderRadius: '8px',
    border: '1px solid #27272a',
    fontSize: '0.9rem',
    backgroundColor: '#111111',
    color: '#ffffff',
    outline: 'none',
    transition: 'border-color 0.2s ease',
  },
  modalTextarea: {
    padding: '10px 14px',
    borderRadius: '8px',
    border: '1px solid #27272a',
    fontSize: '0.9rem',
    resize: 'vertical' as const,
    backgroundColor: '#111111',
    color: '#ffffff',
    minHeight: '120px',
    outline: 'none',
    lineHeight: '1.5',
    fontFamily: 'inherit',
    transition: 'border-color 0.2s ease',
  },
  modalCheckboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.6rem',
    fontSize: '0.9rem',
    color: '#a1a1aa',
    marginBottom: '0.8rem',
    cursor: 'pointer',
  },
  modalActions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '0.75rem',
    marginTop: '1.25rem',
    paddingTop: '1rem',
    borderTop: '1px solid #27272a',
  },
  modalCancel: {
    padding: '10px 20px',
    borderRadius: '8px',
    border: '1px solid #27272a',
    backgroundColor: '#1a1a1a',
    color: '#a1a1aa',
    fontSize: '0.9rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  modalRun: {
    padding: '10px 20px',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#C5F467',
    color: '#0a0a0a',
    fontSize: '0.9rem',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  modalError: {
    color: '#ef4444',
    fontSize: '0.85rem',
    marginTop: '0.5rem',
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
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
    border: '1px solid rgba(59, 130, 246, 0.3)',
    borderRadius: '12px',
    padding: '0.75rem 1rem',
    marginBottom: '1rem',
    fontSize: '0.85rem',
    color: '#1e40af',
  },
  paramsSection: {
    marginTop: '0.5rem',
  },
  paramsSectionTitle: {
    fontSize: '0.95rem',
    fontWeight: '600' as const,
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
    fontWeight: '600' as const,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  executeButton: {
    padding: '0.6rem 1.5rem',
    borderRadius: '999px',
    border: '2px solid rgba(34, 197, 94, 0.6)',
    backgroundColor: 'rgba(34, 197, 94, 0.2)',
    color: '#16a34a',
    fontWeight: '600' as const,
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

export default FloatingAssistant;
