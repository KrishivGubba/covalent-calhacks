import React from 'react';

interface ControlButtonsProps {
  onStart: () => void;
  onStop: () => void;
  isRunning: boolean;
}

const ControlButtons: React.FC<ControlButtonsProps> = ({ onStart, onStop, isRunning }) => {
  return (
    <div style={styles.container}>
      <button 
        style={{
          ...styles.button, 
          ...styles.startButton,
          ...(isRunning ? styles.disabledButton : {})
        }} 
        onClick={onStart}
        disabled={isRunning}
        onMouseEnter={(e) => {
          if (!isRunning) {
            e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.35)';
            e.currentTarget.style.transform = 'translateY(-2px)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isRunning) {
            e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.2)';
            e.currentTarget.style.transform = 'translateY(0)';
          }
        }}
      >
        Start
      </button>
      <button 
        style={{
          ...styles.button, 
          ...styles.stopButton,
          ...(!isRunning ? styles.disabledButton : {})
        }} 
        onClick={onStop}
        disabled={!isRunning}
        onMouseEnter={(e) => {
          if (isRunning) {
            e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.25)';
            e.currentTarget.style.transform = 'translateY(-2px)';
          }
        }}
        onMouseLeave={(e) => {
          if (isRunning) {
            e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.15)';
            e.currentTarget.style.transform = 'translateY(0)';
          }
        }}
      >
        Stop
      </button>
    </div>
  );
};

const styles = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    gap: '1rem',
    padding: '1.5rem 2rem',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    backdropFilter: 'blur(30px)',
    borderTop: '1px solid rgba(255, 255, 255, 0.3)',
    boxShadow: '0 -4px 24px rgba(31, 38, 135, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.5)',
    position: 'relative' as const,
    zIndex: 10,
  },
  button: {
    padding: '0.875rem 3rem',
    fontSize: '1rem',
    fontWeight: '600',
    borderRadius: '14px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    backdropFilter: 'blur(20px)',
  },
  startButton: {
    backgroundColor: 'rgba(34, 197, 94, 0.2)',
    color: '#15803d',
    border: '1px solid rgba(34, 197, 94, 0.3)',
    boxShadow: '0 4px 16px rgba(34, 197, 94, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.6)',
  },
  stopButton: {
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    color: '#dc2626',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    boxShadow: '0 4px 16px rgba(239, 68, 68, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.6)',
  },
  disabledButton: {
    opacity: 0.4,
    cursor: 'not-allowed',
    pointerEvents: 'none' as const,
  },
};

export default ControlButtons;
