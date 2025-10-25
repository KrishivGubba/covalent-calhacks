import React from 'react';

export interface Action {
  id: string;
  title: string;
  description: string;
}

interface SuggestedActionsProps {
  actions: Action[];
}

const SuggestedActions: React.FC<SuggestedActionsProps> = ({ actions }) => {
  return (
    <div style={styles.container}>
      <h2 style={styles.heading}>Suggested Actions</h2>
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
                e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.15)';
              }}
            >
              <h3 style={styles.actionTitle}>{action.title}</h3>
              <p style={styles.actionDescription}>{action.description}</p>
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
    color: '#1e293b',
    textAlign: 'center' as const,
    letterSpacing: '-0.02em',
  },
  actionsContainer: {
    flex: 1,
    overflowY: 'auto' as const,
    borderRadius: '24px',
    padding: '1.5rem',
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    backdropFilter: 'blur(30px)',
    border: '1px solid rgba(255, 255, 255, 0.3)',
    boxShadow: '0 8px 32px rgba(31, 38, 135, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.5)',
  },
  actionCard: {
    padding: '1.25rem 1.5rem',
    marginBottom: '1rem',
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    backdropFilter: 'blur(20px)',
    borderRadius: '16px',
    border: '1px solid rgba(255, 255, 255, 0.4)',
    boxShadow: '0 4px 24px rgba(31, 38, 135, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.6)',
    transition: 'all 0.3s ease',
    cursor: 'pointer',
  },
  actionTitle: {
    fontSize: '1.1rem',
    fontWeight: '600',
    marginBottom: '0.5rem',
    color: '#1e293b',
  },
  actionDescription: {
    fontSize: '0.95rem',
    color: '#475569',
    lineHeight: '1.6',
    margin: 0,
  },
  emptyState: {
    textAlign: 'center' as const,
    color: '#64748b',
    fontSize: '1rem',
    padding: '3rem',
  },
};

export default SuggestedActions;
