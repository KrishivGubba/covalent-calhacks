import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { disableContextCollection, enableContextCollectionIfNotUserPaused } from '../utils/contextControl';
import { notifyPlanReady, notifyExecutionStatus } from '../utils/actionNotifications';

const USER_ID_KEY = 'covalent_user_id';

export interface Action {
  id: string;
  uuid: string;           // Action UUID from database
  title: string;          // action_name from backend
  description: string;    // action_plan from backend (contains full context for execution)
  node_uuid?: string;     // Optional: node this action belongs to
  node_metadata?: string; // Optional: metadata of the node
}

// Single proposed action from planning
export interface ProposedAction {
  step_id: number;
  tool_name: string;
  parameters: Record<string, unknown>;
  reasoning?: string;
}

// Display schema for a single action
export interface ActionDisplay {
  step_id?: number;
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
}

// Execution result for a single action
export interface ActionResult {
  step_id: number;
  tool_name: string;
  status: 'success' | 'error';
  result?: unknown;
  error?: string;
}

// Execution summary
export interface ExecutionSummary {
  total: number;
  succeeded: number;
  failed: number;
}

// Action plan returned from /plan_action endpoint (multi-action support)
export interface ActionPlan {
  status: string;
  action_text: string;
  context_data: string;
  // New multi-action format
  proposed_actions?: ProposedAction[];
  displays?: ActionDisplay[];
  is_multi_action?: boolean;
  overall_reasoning?: string;
  // Legacy single-action format (backward compat)
  proposed_action?: {
    tool_name: string;
    parameters: Record<string, unknown>;
    reasoning?: string;
  };
  display?: ActionDisplay;
  research?: {
    resources_read: string[];
    context_gathered: string;
  };
  // Error info
  error?: string;
}

// Execution response from /execute_action endpoint
export interface ExecutionResponse {
  status: 'success' | 'partial' | 'error';
  // Multi-action response
  results?: ActionResult[];
  summary?: ExecutionSummary;
  // Single-action response (legacy)
  result?: unknown;
  error?: string;
  duration_ms?: number;
}

interface SuggestedActionsProps {
  actions: Action[];
}

type ActionStatus = 'idle' | 'playing' | 'done' | 'error';

const SuggestedActions: React.FC<SuggestedActionsProps> = ({ actions }) => {
  // #region agent log
  React.useEffect(() => {
    fetch('http://127.0.0.1:7243/ingest/7843b36f-61b5-435e-a971-922268939b8a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'SuggestedActions.tsx:mount',message:'NEW MULTI-ACTION COMPONENT MOUNTED v2',data:{hasExecutionResults:typeof useState !== 'undefined'},timestamp:Date.now(),hypothesisId:'H4'})}).catch(()=>{});
  }, []);
  // #endregion
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem(USER_ID_KEY));

  useEffect(() => {
    const checkAuth = () => setIsAuthenticated(!!localStorage.getItem(USER_ID_KEY));
    window.addEventListener('storage', checkAuth);
    const interval = setInterval(checkAuth, 5000);
    return () => {
      window.removeEventListener('storage', checkAuth);
      clearInterval(interval);
    };
  }, []);

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
  // Multi-action: editable params per step_id
  const [editableParamsMap, setEditableParamsMap] = useState<Record<number, Record<string, unknown>>>({});
  const [isExecuting, setIsExecuting] = useState(false);
  // Execution results for display
  const [executionResults, setExecutionResults] = useState<ActionResult[] | null>(null);
  const [executionSummary, setExecutionSummary] = useState<ExecutionSummary | null>(null);
  
  // Legacy: single editableParams for backward compat
  const [_editableParams, setEditableParams] = useState<Record<string, unknown>>({});
  
  // Helper: Get normalized proposed actions array
  const getProposedActions = (plan: ActionPlan): ProposedAction[] => {
    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/7843b36f-61b5-435e-a971-922268939b8a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'SuggestedActions.tsx:getProposedActions',message:'getProposedActions called',data:{has_proposed_actions:!!plan.proposed_actions,proposed_actions_length:plan.proposed_actions?.length,has_legacy:!!plan.proposed_action,plan_keys:Object.keys(plan)},timestamp:Date.now(),hypothesisId:'H1,H2'})}).catch(()=>{});
    // #endregion
    if (plan.proposed_actions && plan.proposed_actions.length > 0) {
      return plan.proposed_actions;
    }
    // Legacy single-action format
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
  
  // Helper: Get the raw variable text for display (e.g., "{{$1.id}}" -> "$1.id")
  const getVariableDisplay = (value: string): { isVar: boolean; displayText: string; stepNum?: number; field?: string } => {
    const match = value.match(/^\{\{\$(\d+)\.(\w+)\}\}$/);
    if (match) {
      return {
        isVar: true,
        displayText: `From Step ${match[1]}: ${match[2]}`,
        stepNum: parseInt(match[1]),
        field: match[2],
      };
    }
    return { isVar: false, displayText: value };
  };

  // Helper: Get display for a step
  const getDisplayForStep = (plan: ActionPlan, stepId: number): ActionDisplay | undefined => {
    if (plan.displays && plan.displays.length > 0) {
      return plan.displays.find(d => d.step_id === stepId) || plan.displays[stepId - 1];
    }
    // Legacy single display
    if (plan.display && stepId === 1) {
      return plan.display;
    }
    return undefined;
  };

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
        console.log(`   - status: ${plan.status}`);
        console.log(`   - proposed_actions: ${plan.proposed_actions ? JSON.stringify(plan.proposed_actions) : 'undefined'}`);
        console.log(`   - displays: ${plan.displays ? JSON.stringify(plan.displays) : 'undefined'}`);
        console.log(`   - legacy proposed_action: ${plan.proposed_action ? JSON.stringify(plan.proposed_action) : 'undefined'}`);
        // #region agent log
        fetch('http://127.0.0.1:7243/ingest/7843b36f-61b5-435e-a971-922268939b8a',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'SuggestedActions.tsx:handleActionClick',message:'Plan received from Tauri',data:{status:plan.status,proposed_actions:plan.proposed_actions,displays:plan.displays,legacy_proposed_action:plan.proposed_action,all_keys:Object.keys(plan)},timestamp:Date.now(),hypothesisId:'H1,H2,H5'})}).catch(()=>{});
        // #endregion

        if (plan.status === 'error') {
          // Flask or MCP returned a structured error — show it in the error modal.
          setPlanError(plan.error || 'Planning failed');
          setActionStatuses(prev => ({ ...prev, [action.id]: 'idle' }));
          await enableContextCollectionIfNotUserPaused();
          return;
        }

        setActionPlan(plan);
        setExecutionResults(null);
        setExecutionSummary(null);
        
        // Initialize editable params for all proposed actions
        const proposedActions = getProposedActions(plan);
        console.log(`   - parsed proposedActions (${proposedActions.length}):`, proposedActions);
        const paramsMap: Record<number, Record<string, unknown>> = {};
        proposedActions.forEach(action => {
          paramsMap[action.step_id] = { ...action.parameters };
        });
        setEditableParamsMap(paramsMap);
        
        // Legacy: also set single editableParams for backward compat
        if (plan.proposed_action?.parameters) {
          setEditableParams({ ...plan.proposed_action.parameters });
        }
        
        // Send notification if app is not focused
        await notifyPlanReady(action.title, action.uuid, plan, paramsMap);
        
        // Keep status as 'playing' until user confirms or cancels
      } catch (error) {
        // Network-level failure (Flask server down, connection refused, etc.)
        console.error(`❌ Action planning failed:`, error);
        setPlanError(String(error));
        setActionStatuses(prev => ({ ...prev, [action.id]: 'idle' }));
        // Keep planningAction set so the error is visible in the loading/error modal.
        await enableContextCollectionIfNotUserPaused();
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
    
    // Track if we have results to show (for finally block)
    let hasResults = false;
    
    try {
      console.log(`🚀 Executing ${proposedActions.length} action(s): ${planningAction.title}`);
      
      // Build actions array with user-edited parameters
      const actionsToExecute = proposedActions.map(action => ({
        step_id: action.step_id,
        tool_name: action.tool_name,
        parameters: editableParamsMap[action.step_id] || action.parameters,
      }));
      
      console.log(`   Actions:`, actionsToExecute);
      
      const response = await invoke<ExecutionResponse>('execute_action', {
        actionUuid: planningAction.uuid,
        actions: actionsToExecute,
      });
      
      console.log(`📊 Execution response:`, response);
      
      // Handle multi-action response
      if (response.results && response.summary) {
        setExecutionResults(response.results);
        setExecutionSummary(response.summary);
        hasResults = true;
        
        if (response.summary.failed === 0) {
          console.log(`✅ All ${response.summary.total} actions executed successfully`);
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'done' }));
          // Send notification for successful execution
          await notifyExecutionStatus(planningAction.title, true);
        } else if (response.summary.succeeded === 0) {
          console.log(`❌ All ${response.summary.total} actions failed`);
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'error' }));
          // Send notification for failed execution
          await notifyExecutionStatus(planningAction.title, false, 'All actions failed');
        } else {
          console.log(`⚠️ Partial success: ${response.summary.succeeded}/${response.summary.total} succeeded`);
          // Mark as done with partial success (user can see details)
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'done' }));
          // Send notification for partial success
          await notifyExecutionStatus(planningAction.title, true, `${response.summary.succeeded}/${response.summary.total} succeeded`);
        }
      } else {
        // Legacy single-action response - no results modal, just close
        if (response.status === 'success') {
          console.log(`✅ Action executed successfully`);
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'done' }));
          await notifyExecutionStatus(planningAction.title, true);
        } else {
          console.error(`❌ Action failed:`, response.error);
          setPlanError(response.error || 'Unknown error');
          setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'error' }));
        }
      }
    } catch (error) {
      console.error(`❌ Action execution failed:`, error);
      setPlanError(String(error));
      setActionStatuses(prev => ({ ...prev, [planningAction.id]: 'error' }));
      
      // Send notification for failed execution
      await notifyExecutionStatus(planningAction.title, false, String(error));
    } finally {
      setIsExecuting(false);
      // Don't clear the modal if we have results to show
      if (!hasResults) {
        setPlanningAction(null);
        setActionPlan(null);
        setEditableParamsMap({});
        setEditableParams({});
      }
    }
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

  // Per-step param change handler for multi-action
  const handleStepParamChange = (stepId: number, key: string, value: unknown) => {
    setEditableParamsMap(prev => ({
      ...prev,
      [stepId]: {
        ...prev[stepId],
        [key]: value,
      }
    }));
  };

  // // Legacy: single action param change
  // const _handleParamChange = (key: string, value: unknown) => {
  //   setEditableParams(prev => ({ ...prev, [key]: value }));
  //   // Also update the map for step 1 (backward compat)
  //   handleStepParamChange(1, key, value);
  // };

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
      setExecutionResults(null);
      setExecutionSummary(null);
      
      // Initialize editable params for all proposed actions
      const proposedActions = getProposedActions(plan);
      const paramsMap: Record<number, Record<string, unknown>> = {};
      proposedActions.forEach(action => {
        paramsMap[action.step_id] = { ...action.parameters };
      });
      setEditableParamsMap(paramsMap);
      
      // Legacy
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
        {!isAuthenticated ? (
          <p style={styles.emptyState}>Please log in from the dashboard to get started.</p>
        ) : actions.length === 0 ? (
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

              {/* Debug: Show raw data if no actions parsed */}
              {getProposedActions(actionPlan).length === 0 && (
                <div style={styles.reasoningBox}>
                  <strong>Error:</strong> No actions could be parsed from the plan. 
                  {actionPlan.error && <span> {actionPlan.error}</span>}
                  <details style={{ marginTop: '0.5rem' }}>
                    <summary style={{ cursor: 'pointer' }}>Debug Info</summary>
                    <pre style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', marginTop: '0.5rem' }}>
                      {JSON.stringify({ 
                        status: actionPlan.status,
                        has_proposed_actions: !!actionPlan.proposed_actions,
                        proposed_actions_length: actionPlan.proposed_actions?.length,
                        has_legacy_proposed_action: !!actionPlan.proposed_action,
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
                    {/* Step header */}
                    <div style={styles.stepHeader}>
                      <span style={styles.stepNumber}>{idx + 1}</span>
                      <span style={styles.stepTitle}>
                        {display?.display_name || proposedAction.tool_name}
                      </span>
                    </div>

                    {/* Step description */}
                    {display?.description && (
                      <p style={styles.stepDescription}>{display.description}</p>
                    )}

                    {/* Step reasoning (if single action and has reasoning) */}
                    {!isMultiAction && proposedAction.reasoning && (
                      <div style={styles.reasoningBox}>
                        <strong>Plan:</strong> {proposedAction.reasoning}
                      </div>
                    )}

                    {/* Editable parameters for this step */}
                    <div style={styles.paramsSection}>
                      {display?.fields ? (
                        display.fields.map((field) => {
                          const rawValue = String(stepParams[field.key] ?? field.value ?? '');
                          const varInfo = getVariableDisplay(rawValue);
                          
                          return (
                            <label key={field.key} style={styles.modalLabel}>
                              {field.label} {field.required && <span style={{ color: '#ef4444' }}>*</span>}
                              {varInfo.isVar ? (
                                // Variable reference - show as non-editable with special styling
                                <div style={styles.variableRefContainer}>
                                  <span style={styles.variableRefBadge}>
                                    ↩ {varInfo.displayText}
                                  </span>
                                  <span style={styles.variableRefHint}>
                                    (resolved at execution time)
                                  </span>
                                </div>
                              ) : field.widget === 'textarea' || rawValue.length > 100 ? (
                                <textarea
                                  style={styles.modalTextarea}
                                  value={rawValue}
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
                                  value={rawValue}
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
                          );
                        })
                      ) : (
                        // Fallback: render all parameters as editable fields
                        Object.entries(stepParams).map(([key, value]) => {
                          const rawValue = String(value ?? '');
                          const varInfo = getVariableDisplay(rawValue);
                          
                          return (
                            <label key={key} style={styles.modalLabel}>
                              {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                              {varInfo.isVar ? (
                                // Variable reference - show as non-editable with special styling
                                <div style={styles.variableRefContainer}>
                                  <span style={styles.variableRefBadge}>
                                    ↩ {varInfo.displayText}
                                  </span>
                                  <span style={styles.variableRefHint}>
                                    (resolved at execution time)
                                  </span>
                                </div>
                              ) : rawValue.length > 100 ? (
                                <textarea
                                  style={styles.modalTextarea}
                                  value={rawValue}
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
                                  value={rawValue}
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
                          );
                        })
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
              {/* Summary bar */}
              <div style={styles.summaryBar}>
                <span style={styles.summaryText}>
                  {executionSummary.succeeded} succeeded, {executionSummary.failed} failed
                </span>
              </div>

              {/* Individual results */}
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

      {/* Loading / planning-error state */}
      {planningAction && !actionPlan && (
        <div style={styles.modalOverlay}>
          <div style={styles.loadingModal}>
            {planError ? (
              <>
                <div style={{ fontSize: '1.5rem', color: '#f87171', marginBottom: '0.75rem' }}>✕</div>
                <p style={{ ...styles.loadingText, color: 'rgba(248, 113, 113, 0.95)', textAlign: 'center' as const, maxWidth: '320px' }}>
                  {planError}
                </p>
                <button
                  onClick={() => { setPlanningAction(null); setPlanError(null); }}
                  style={{ marginTop: '1.25rem', padding: '8px 20px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.2)', backgroundColor: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.72)', fontSize: '0.9rem', cursor: 'pointer' }}
                >
                  Dismiss
                </button>
              </>
            ) : (
              <>
                <div style={styles.loadingSpinner}>
                  <span style={styles.dot1}>.</span>
                  <span style={styles.dot2}>.</span>
                  <span style={styles.dot3}>.</span>
                </div>
                <p style={styles.loadingText}>Planning action...</p>
              </>
            )}
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
    fontWeight: '600',
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
  variableRefContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 14px',
    borderRadius: '8px',
    border: '1px dashed #3b82f6',
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
  },
  variableRefBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '4px 10px',
    borderRadius: '6px',
    backgroundColor: 'rgba(59, 130, 246, 0.2)',
    color: '#60a5fa',
    fontSize: '0.85rem',
    fontWeight: '500' as const,
  },
  variableRefHint: {
    color: '#6b7280',
    fontSize: '0.8rem',
    fontStyle: 'italic' as const,
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
    fontWeight: '600',
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
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  executeButton: {
    padding: '10px 20px',
    borderRadius: '8px',
    border: 'none',
    backgroundColor: '#C5F467',
    color: '#0a0a0a',
    fontWeight: '600',
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
    fontWeight: '600',
  },
  stepTitle: {
    fontSize: '1rem',
    fontWeight: '600',
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
    fontWeight: '500',
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
    fontWeight: '700',
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
    fontWeight: '700',
    flexShrink: 0,
  },
  resultTitle: {
    flex: 1,
    fontSize: '0.95rem',
    fontWeight: '600',
    color: '#ffffff',
  },
  resultStatus: {
    fontSize: '0.85rem',
    fontWeight: '600',
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
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
};

export default SuggestedActions;
