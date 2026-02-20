import React, { useState, memo, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import type { Action, ActionPlan, ProposedAction, ActionDisplay, ActionResult, ExecutionSummary, ExecutionResponse } from './SuggestedActions';
import { disableContextCollection, enableContextCollectionIfNotUserPaused } from '../utils/contextControl';
import { notifyPlanReady, notifyExecutionStatus } from '../utils/actionNotifications';

interface FloatingAssistantProps {
  actions: Action[];
  isRunning: boolean;
  onStart: () => void;
  onStop: () => void;
}

type ViewState = 'collapsed' | 'expanded';
type ActionStatus = 'idle' | 'playing' | 'done';

const USER_ID_KEY = 'covalent_user_id';

const FloatingAssistant: React.FC<FloatingAssistantProps> = memo(({ 
  actions, 
  isRunning, 
  onStart, 
  onStop 
}) => {
  const [viewState, setViewState] = useState<ViewState>('collapsed');
  const [actionStatuses, setActionStatuses] = useState<Record<string, ActionStatus>>({});
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem(USER_ID_KEY));
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
  const [_editableParams, setEditableParams] = useState<Record<string, unknown>>({});
  const [isExecuting, setIsExecuting] = useState(false);
  // Multi-action support
  const [editableParamsMap, setEditableParamsMap] = useState<Record<number, Record<string, unknown>>>({});
  const [executionResults, setExecutionResults] = useState<ActionResult[] | null>(null);
  const [executionSummary, setExecutionSummary] = useState<ExecutionSummary | null>(null);

  // #region agent log
  useEffect(() => {
    fetch('http://127.0.0.1:7243/ingest/7843b36f-61b5-435e-a971-922268939b8a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'FloatingAssistant.tsx:mount',message:'UPDATED FLOATING ASSISTANT MOUNTED',data:{},timestamp:Date.now(),hypothesisId:'verify'})}).catch(()=>{});
  }, []);
  // #endregion

  useEffect(() => {
    const checkAuth = () => setIsAuthenticated(!!localStorage.getItem(USER_ID_KEY));
    window.addEventListener('storage', checkAuth);
    const interval = setInterval(checkAuth, 5000);
    return () => {
      window.removeEventListener('storage', checkAuth);
      clearInterval(interval);
    };
  }, []);

  // Helper: Get normalized proposed actions array
  const getProposedActions = (plan: ActionPlan): ProposedAction[] => {
    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/7843b36f-61b5-435e-a971-922268939b8a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'FloatingAssistant.tsx:getProposedActions',message:'getProposedActions called',data:{has_proposed_actions:!!plan.proposed_actions,proposed_actions_length:plan.proposed_actions?.length,has_legacy:!!plan.proposed_action,plan_keys:Object.keys(plan)},timestamp:Date.now(),hypothesisId:'H1,H2'})}).catch(()=>{});
    // #endregion
    if (plan.proposed_actions && plan.proposed_actions.length > 0) {
      return plan.proposed_actions;
    }
    if (plan.proposed_action) {
      return [{
        step_id: 1,
        tool_name: plan.proposed_action.tool_name,
        parameters: plan.proposed_action.parameters,
        reasoning: plan.proposed_action.reasoning,
      }];
    }
    return [];
  };

  // Helper: Get display for a step
  const getDisplayForStep = (plan: ActionPlan, stepId: number): ActionDisplay | undefined => {
    if (plan.displays && plan.displays.length > 0) {
      return plan.displays.find(d => d.step_id === stepId) || plan.displays[stepId - 1];
    }
    if (plan.display && stepId === 1) {
      return plan.display;
    }
    return undefined;
  };

  // Per-step param change handler
  const handleStepParamChange = (stepId: number, key: string, value: unknown) => {
    setEditableParamsMap(prev => ({
      ...prev,
      [stepId]: { ...prev[stepId], [key]: value }
    }));
  };

  // Close results modal
  const handleCloseResults = async () => {
    setPlanningAction(null);
    setActionPlan(null);
    setEditableParamsMap({});
    setEditableParams({});
    setExecutionResults(null);
    setExecutionSummary(null);
    await enableContextCollectionIfNotUserPaused();
  };

  const handleIconClick = () => {
    if (!isAnimating) {
      setIsAnimating(true);
      setTimeout(() => {
        // Toggle between collapsed and expanded
        setViewState(viewState === 'collapsed' ? 'expanded' : 'collapsed');
        setIsAnimating(false);
      }, 100);
    }
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
        // #region agent log
        fetch('http://127.0.0.1:7243/ingest/7843b36f-61b5-435e-a971-922268939b8a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'FloatingAssistant.tsx:handleActionClick',message:'Plan received',data:{status:plan.status,proposed_actions:plan.proposed_actions,displays:plan.displays,legacy:plan.proposed_action,keys:Object.keys(plan)},timestamp:Date.now(),hypothesisId:'H1,H2,H5'})}).catch(()=>{});
        // #endregion
        setActionPlan(plan);
        setExecutionResults(null);
        setExecutionSummary(null);
        
        // Initialize editable params for all proposed actions
        const proposedActions = getProposedActions(plan);
        const paramsMap: Record<number, Record<string, unknown>> = {};
        proposedActions.forEach(action => {
          paramsMap[action.step_id] = { ...action.parameters };
        });
        setEditableParamsMap(paramsMap);
        
        // Legacy single params
        if (plan.proposed_action?.parameters) {
          setEditableParams({ ...plan.proposed_action.parameters });
        }
        
        // Send notification if app is not focused
        await notifyPlanReady(action.title, action.uuid, plan, paramsMap);
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
    if (!planningAction || !actionPlan) {
      return;
    }
    
    const proposedActions = getProposedActions(actionPlan);
    if (proposedActions.length === 0) {
      return;
    }
    
    setIsExecuting(true);
    setPlanError(null);
    setExecutionResults(null);
    setExecutionSummary(null);
    
    let hasResults = false;
    
    try {
      console.log(`🚀 Executing ${proposedActions.length} action(s): ${planningAction.title}`);
      
      const actionsToExecute = proposedActions.map(action => ({
        step_id: action.step_id,
        tool_name: action.tool_name,
        parameters: editableParamsMap[action.step_id] || action.parameters,
      }));
      
      // #region agent log
      fetch('http://127.0.0.1:7243/ingest/7843b36f-61b5-435e-a971-922268939b8a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'FloatingAssistant.tsx:handleExecuteAction',message:'Executing actions',data:{count:actionsToExecute.length,actions:actionsToExecute},timestamp:Date.now(),hypothesisId:'execution'})}).catch(()=>{});
      // #endregion
      
      const response = await invoke<ExecutionResponse>('execute_action', {
        actionUuid: planningAction.uuid,
        actions: actionsToExecute,
      });
      
      console.log(`📊 Execution response:`, response);
      
      if (response.results && response.summary) {
        setExecutionResults(response.results);
        setExecutionSummary(response.summary);
        hasResults = true;
        
        if (response.summary.failed === 0) {
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'done' }));
          // Send notification for successful execution
          await notifyExecutionStatus(planningAction.title, true);
        } else if (response.summary.succeeded === 0) {
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'idle' }));
          // Send notification for failed execution
          await notifyExecutionStatus(planningAction.title, false, 'All actions failed');
        } else {
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'done' }));
          // Send notification for partial success
          await notifyExecutionStatus(planningAction.title, true, `${response.summary.succeeded}/${response.summary.total} succeeded`);
        }
      } else {
        if (response.status === 'success') {
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'done' }));
          await notifyExecutionStatus(planningAction.title, true);
        } else {
          setPlanError(response.error || 'Unknown error');
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'idle' }));
        }
      }
    } catch (error) {
      console.error(`❌ Action execution failed:`, error);
      setPlanError(String(error));
      setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'idle' }));
      
      // Send notification for failed execution
      await notifyExecutionStatus(planningAction.title, false, String(error));
    } finally {
      setIsExecuting(false);
      if (!hasResults) {
        setPlanningAction(null);
        setActionPlan(null);
        setEditableParamsMap({});
        setEditableParams({});
      }
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
    setEditableParamsMap({});
    setExecutionResults(null);
    setExecutionSummary(null);
    await enableContextCollectionIfNotUserPaused();
  };

  // const _handleParamChange = (key: string, value: unknown) => {
  //   setEditableParams(prev => ({ ...prev, [key]: value }));
  // };

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
    } else {
      // expanded state
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
            {!isAuthenticated ? (
              <div style={styles.loginPrompt}>
                Please log in from the dashboard to get started.
              </div>
            ) : actions.length === 0 ? (
              <div style={styles.emptyActions}>No actions at the moment</div>
            ) : (
              actions.map((action) => {
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
              })
            )}
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

      {/* Action Plan Confirmation Modal - Multi-action support */}
      {planningAction && actionPlan && !executionResults && (
        <div style={styles.modalOverlay}>
          <div style={styles.planModal}>
            <div style={styles.modalHeader}>
              <h3 style={styles.modalTitle}>
                {getProposedActions(actionPlan).length > 1 
                  ? `Confirm ${getProposedActions(actionPlan).length} Actions`
                  : (getDisplayForStep(actionPlan, 1)?.display_name || getProposedActions(actionPlan)[0]?.tool_name || 'Confirm Action')
                }
              </h3>
              <button 
                style={styles.modalClose} 
                onClick={handleCancelPlan}
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
            <div style={styles.planModalBody}>
              {/* Overall reasoning for multi-action */}
              {actionPlan.overall_reasoning && (
                <div style={styles.reasoningBox}>
                  <strong>Plan:</strong> {actionPlan.overall_reasoning}
                </div>
              )}

              {/* Debug: Show if no actions parsed */}
              {getProposedActions(actionPlan).length === 0 && (
                <div style={styles.reasoningBox}>
                  <strong>Error:</strong> No actions could be parsed from the plan.
                  <details style={{ marginTop: '0.5rem' }}>
                    <summary style={{ cursor: 'pointer' }}>Debug Info</summary>
                    <pre style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', marginTop: '0.5rem' }}>
                      {JSON.stringify({ 
                        status: actionPlan.status,
                        has_proposed_actions: !!actionPlan.proposed_actions,
                        proposed_actions_length: actionPlan.proposed_actions?.length,
                        has_legacy: !!actionPlan.proposed_action,
                      }, null, 2)}
                    </pre>
                  </details>
                </div>
              )}

              {/* Render each action step */}
              {getProposedActions(actionPlan).map((proposedAction, idx) => {
                const display = getDisplayForStep(actionPlan, proposedAction.step_id);
                const stepParams = editableParamsMap[proposedAction.step_id] || proposedAction.parameters;
                const isMultiAction = getProposedActions(actionPlan).length > 1;

                return (
                  <div key={proposedAction.step_id} style={styles.stepCard}>
                    <div style={styles.stepHeader}>
                      <span style={styles.stepNumber}>{idx + 1}</span>
                      <span style={styles.stepTitle}>
                        {display?.display_name || proposedAction.tool_name}
                      </span>
                    </div>

                    {display?.description && (
                      <p style={styles.stepDescription}>{display.description}</p>
                    )}

                    {!isMultiAction && proposedAction.reasoning && (
                      <div style={styles.reasoningBox}>
                        <strong>Plan:</strong> {proposedAction.reasoning}
                      </div>
                    )}

                    <div style={styles.paramsSection}>
                      {display?.fields ? (
                        display.fields.map((field) => (
                          <label key={field.key} style={styles.modalLabel}>
                            {field.label} {field.required && <span style={{ color: '#ef4444' }}>*</span>}
                            {field.widget === 'textarea' || (typeof stepParams[field.key] === 'string' && String(stepParams[field.key]).length > 100) ? (
                              <textarea
                                style={styles.modalTextarea}
                                value={String(stepParams[field.key] ?? field.value ?? '')}
                                onChange={(e) => handleStepParamChange(proposedAction.step_id, field.key, e.target.value)}
                                disabled={!field.editable || isExecuting}
                                rows={4}
                                onFocus={(e) => {
                                  e.currentTarget.style.borderColor = '#3f3f46';
                                }}
                                onBlur={(e) => {
                                  e.currentTarget.style.borderColor = '#27272a';
                                }}
                              />
                            ) : (
                              <input
                                style={styles.modalInput}
                                value={String(stepParams[field.key] ?? field.value ?? '')}
                                onChange={(e) => handleStepParamChange(proposedAction.step_id, field.key, e.target.value)}
                                disabled={!field.editable || isExecuting}
                                onFocus={(e) => {
                                  e.currentTarget.style.borderColor = '#3f3f46';
                                }}
                                onBlur={(e) => {
                                  e.currentTarget.style.borderColor = '#27272a';
                                }}
                              />
                            )}
                          </label>
                        ))
                      ) : (
                        Object.entries(stepParams).map(([key, value]) => (
                          <label key={key} style={styles.modalLabel}>
                            {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                            {typeof value === 'string' && value.length > 100 ? (
                              <textarea
                                style={styles.modalTextarea}
                                value={String(value)}
                                onChange={(e) => handleStepParamChange(proposedAction.step_id, key, e.target.value)}
                                disabled={isExecuting}
                                rows={4}
                                onFocus={(e) => {
                                  e.currentTarget.style.borderColor = '#3f3f46';
                                }}
                                onBlur={(e) => {
                                  e.currentTarget.style.borderColor = '#27272a';
                                }}
                              />
                            ) : (
                              <input
                                style={styles.modalInput}
                                value={String(value ?? '')}
                                onChange={(e) => handleStepParamChange(proposedAction.step_id, key, e.target.value)}
                                disabled={isExecuting}
                                onFocus={(e) => {
                                  e.currentTarget.style.borderColor = '#3f3f46';
                                }}
                                onBlur={(e) => {
                                  e.currentTarget.style.borderColor = '#27272a';
                                }}
                              />
                            )}
                          </label>
                        ))
                      )}
                    </div>
                  </div>
                );
              })}

              {planError && <div style={styles.modalError}>{planError}</div>}
            </div>
            <div style={styles.planModalActions}>
              <button 
                style={styles.exitButton} 
                onClick={handleCancelPlan}
                disabled={isExecuting}
                onMouseEnter={(e) => {
                  if (!isExecuting) e.currentTarget.style.backgroundColor = '#27272a';
                }}
                onMouseLeave={(e) => {
                  if (!isExecuting) e.currentTarget.style.backgroundColor = '#1a1a1a';
                }}
              >
                Exit
              </button>
              <button 
                style={styles.executeButton} 
                onClick={handleExecuteAction}
                disabled={isExecuting}
                onMouseEnter={(e) => {
                  if (!isExecuting) e.currentTarget.style.opacity = '0.9';
                }}
                onMouseLeave={(e) => {
                  if (!isExecuting) e.currentTarget.style.opacity = '1';
                }}
              >
                {isExecuting 
                  ? `Executing ${getProposedActions(actionPlan).length} action(s)...` 
                  : `Execute${getProposedActions(actionPlan).length > 1 ? ` All (${getProposedActions(actionPlan).length})` : ''}`
                }
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Execution Results Modal */}
      {planningAction && executionResults && executionSummary && (
        <div style={styles.modalOverlay}>
          <div style={styles.resultsModal}>
            <div style={styles.modalHeader}>
              <div style={styles.resultsTitleContainer}>
                <span style={{
                  ...styles.resultsTitleIndicator,
                  backgroundColor: executionSummary.failed === 0 
                    ? 'rgba(34, 197, 94, 0.2)' 
                    : executionSummary.succeeded === 0 
                      ? 'rgba(239, 68, 68, 0.2)' 
                      : 'rgba(251, 191, 36, 0.2)',
                  borderColor: executionSummary.failed === 0 
                    ? 'rgba(34, 197, 94, 0.5)' 
                    : executionSummary.succeeded === 0 
                      ? 'rgba(239, 68, 68, 0.5)' 
                      : 'rgba(251, 191, 36, 0.5)',
                  color: executionSummary.failed === 0 
                    ? '#22c55e' 
                    : executionSummary.succeeded === 0 
                      ? '#ef4444' 
                      : '#fbbf24',
                }}>
                  {executionSummary.failed === 0 ? '✓' : executionSummary.succeeded === 0 ? '✕' : '!'}
                </span>
                <h3 style={styles.modalTitle}>
                  {executionSummary.failed === 0 
                    ? 'All Actions Completed'
                    : executionSummary.succeeded === 0
                      ? 'All Actions Failed'
                      : `Partial Success (${executionSummary.succeeded}/${executionSummary.total})`
                  }
                </h3>
              </div>
              <button 
                style={styles.modalClose} 
                onClick={handleCloseResults}
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
            <div style={styles.resultsBody}>
              <div style={styles.summaryBar}>
                <span style={styles.summaryText}>
                  {executionSummary.succeeded} succeeded, {executionSummary.failed} failed
                </span>
              </div>

              {executionResults.map((result, idx) => (
                <div 
                  key={result.step_id} 
                  style={{
                    ...styles.resultCard,
                    borderLeftColor: result.status === 'success' ? '#22c55e' : '#ef4444',
                  }}
                >
                  <div style={styles.resultHeader}>
                    <span style={{
                      ...styles.resultIconBadge,
                      backgroundColor: result.status === 'success' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                      borderColor: result.status === 'success' ? 'rgba(34, 197, 94, 0.5)' : 'rgba(239, 68, 68, 0.5)',
                      color: result.status === 'success' ? '#22c55e' : '#ef4444',
                    }}>
                      {result.status === 'success' ? '✓' : '✕'}
                    </span>
                    <span style={styles.resultTitle}>
                      Step {idx + 1}: {result.tool_name}
                    </span>
                    <span style={{
                      ...styles.resultStatus,
                      color: result.status === 'success' ? '#22c55e' : '#ef4444',
                    }}>
                      {result.status === 'success' ? 'Success' : 'Failed'}
                    </span>
                  </div>
                  {result.error && (
                    <div style={styles.resultError}>
                      {String(result.error)}
                    </div>
                  )}
                  {result.status === 'success' && Boolean(result.result) && (
                    <div style={styles.resultSuccess}>
                      {(() => {
                        const resultStr = typeof result.result === 'string' 
                          ? result.result 
                          : JSON.stringify(result.result, null, 2);
                        return resultStr.length > 200 
                          ? resultStr.substring(0, 200) + '...'
                          : resultStr;
                      })()}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div style={styles.planModalActions}>
              <button 
                style={styles.closeButton} 
                onClick={handleCloseResults}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = '0.9';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = '1';
                }}
              >
                Close
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
  loginPrompt: {
    textAlign: 'center' as const,
    padding: '1.5rem 1rem',
    color: '#ffffff',
    fontSize: '0.9rem',
    fontWeight: '500' as const,
    lineHeight: '1.5',
  },
  emptyActions: {
    textAlign: 'center' as const,
    padding: '1.5rem 1rem',
    color: 'rgba(255, 255, 255, 0.7)',
    fontSize: '0.9rem',
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
    backgroundColor: '#141414',
    borderRadius: '16px',
    padding: '1.5rem',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
    border: '1px solid #27272a',
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
    color: '#a1a1aa',
    marginBottom: '1rem',
    lineHeight: '1.5',
  },
  reasoningBox: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #27272a',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    marginBottom: '1rem',
    fontSize: '0.85rem',
    color: '#ffffff',
    lineHeight: '1.5',
  },
  paramsSection: {
    marginTop: '0.5rem',
  },
  paramsSectionTitle: {
    fontSize: '0.95rem',
    fontWeight: '600' as const,
    color: '#ffffff',
    marginBottom: '0.75rem',
  },
  planModalActions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '0.75rem',
    marginTop: '1rem',
    paddingTop: '1rem',
    borderTop: '1px solid #27272a',
  },
  exitButton: {
    padding: '10px 20px',
    borderRadius: '8px',
    border: '1px solid #27272a',
    backgroundColor: '#1a1a1a',
    color: '#a1a1aa',
    fontWeight: '500' as const,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  executeButton: {
    padding: '10px 20px',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#C5F467',
    color: '#0a0a0a',
    fontWeight: '600' as const,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  loadingModal: {
    backgroundColor: '#141414',
    borderRadius: '16px',
    padding: '2rem 3rem',
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
    border: '1px solid #27272a',
  },
  loadingSpinner: {
    fontSize: '2rem',
    color: '#C5F467',
    marginBottom: '0.5rem',
  },
  loadingText: {
    fontSize: '0.95rem',
    color: '#a1a1aa',
  },
  // Multi-action step card styles
  stepCard: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #27272a',
    borderRadius: '12px',
    padding: '1rem',
    marginBottom: '1rem',
  },
  stepHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    marginBottom: '0.75rem',
  },
  stepNumber: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    backgroundColor: 'rgba(197, 244, 103, 0.15)',
    color: '#C5F467',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '0.85rem',
    fontWeight: '600' as const,
  },
  stepTitle: {
    fontSize: '1rem',
    fontWeight: '600' as const,
    color: '#ffffff',
  },
  stepDescription: {
    fontSize: '0.85rem',
    color: '#a1a1aa',
    marginBottom: '0.75rem',
    lineHeight: '1.5',
  },
  // Results modal styles
  resultsModal: {
    width: '700px',
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
  resultsBody: {
    overflowY: 'auto' as const,
    paddingRight: '0.25rem',
    flex: 1,
  },
  summaryBar: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #27272a',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    marginBottom: '1rem',
    textAlign: 'center' as const,
  },
  summaryText: {
    fontSize: '0.9rem',
    color: '#a1a1aa',
    fontWeight: '500' as const,
  },
  resultCard: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #27272a',
    borderLeftWidth: '4px',
    borderLeftStyle: 'solid' as const,
    borderRadius: '8px',
    padding: '1rem',
    marginBottom: '0.75rem',
  },
  resultHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  resultsTitleContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  resultsTitleIndicator: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    border: '2px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '0.9rem',
    fontWeight: '700' as const,
  },
  resultIconBadge: {
    width: '24px',
    height: '24px',
    borderRadius: '50%',
    border: '1.5px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '0.75rem',
    fontWeight: '700' as const,
    flexShrink: 0,
  },
  resultTitle: {
    flex: 1,
    fontSize: '0.95rem',
    fontWeight: '600' as const,
    color: '#ffffff',
  },
  resultStatus: {
    fontSize: '0.85rem',
    fontWeight: '600' as const,
  },
  resultError: {
    marginTop: '0.75rem',
    padding: '0.75rem',
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    borderRadius: '8px',
    fontSize: '0.85rem',
    color: '#ef4444',
    lineHeight: '1.4',
  },
  resultSuccess: {
    marginTop: '0.75rem',
    padding: '0.75rem',
    backgroundColor: 'rgba(34, 197, 94, 0.15)',
    border: '1px solid rgba(34, 197, 94, 0.3)',
    borderRadius: '8px',
    fontSize: '0.85rem',
    color: '#22c55e',
    lineHeight: '1.4',
    fontFamily: 'monospace',
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
  },
  closeButton: {
    padding: '10px 20px',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#C5F467',
    color: '#0a0a0a',
    fontWeight: '600' as const,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
};

export default FloatingAssistant;
