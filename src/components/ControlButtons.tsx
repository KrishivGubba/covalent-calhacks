import React from 'react';

interface ControlButtonsProps {
  onStart: () => void;
  onStop: () => void;
  isRunning: boolean;
}

const ControlButtons: React.FC<ControlButtonsProps> = ({ onStart, onStop, isRunning }) => {
  const handleClick = () => {
    if (isRunning) {
      onStop();
    } else {
      onStart();
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.controlsWrapper}>
        {isRunning && (
          <div style={styles.statusIndicator}>
            <div style={styles.statusDot}></div>
            <span style={styles.statusText}>learning</span>
          </div>
        )}
        <button 
          style={{
            ...styles.button, 
            ...(isRunning ? styles.stopButton : styles.startButton)
          }} 
          onClick={handleClick}
          onMouseEnter={(e) => {
            if (isRunning) {
              e.currentTarget.style.backgroundColor = 'rgba(220, 38, 38, 0.55)';
            } else {
              e.currentTarget.style.backgroundColor = 'rgba(22, 163, 74, 0.55)';
            }
            e.currentTarget.style.transform = 'translateY(-2px)';
          }}
          onMouseLeave={(e) => {
            if (isRunning) {
              e.currentTarget.style.backgroundColor = 'rgba(220, 38, 38, 0.45)';
            } else {
              e.currentTarget.style.backgroundColor = 'rgba(22, 163, 74, 0.45)';
            }
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          {isRunning ? 'Stop Learning' : 'Restart Learning'}
        </button>
      </div>
    </div>
  );
};

const styles = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    padding: '1.5rem 2rem',
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    backdropFilter: 'blur(40px) saturate(180%)',
    WebkitBackdropFilter: 'blur(40px) saturate(180%)',
    borderTop: '1px solid rgba(255, 255, 255, 0.4)',
    boxShadow: '0 -4px 24px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.7)',
    position: 'relative' as const,
    zIndex: 10,
  },
  controlsWrapper: {
    display: 'flex',
    gap: '1.5rem',
    justifyContent: 'center',
    alignItems: 'center',
    width: '100%',
    maxWidth: '600px',
  },
  statusIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.625rem 1rem',
    backgroundColor: 'rgba(34, 197, 94, 0.15)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    borderRadius: '16px',
    border: '1px solid rgba(34, 197, 94, 0.3)',
    boxShadow: '0 2px 12px rgba(34, 197, 94, 0.2)',
  },
  statusDot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    backgroundColor: '#22c55e',
    boxShadow: '0 0 10px rgba(34, 197, 94, 0.6)',
    animation: 'pulse 2s ease-in-out infinite',
  },
  statusText: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#22c55e',
    textShadow: '0 1px 2px rgba(0, 0, 0, 0.1)',
  },
  button: {
    padding: '0.875rem 3rem',
    fontSize: '1rem',
    fontWeight: '600',
    borderRadius: '20px',
    cursor: 'pointer',
    transition: 'all 0.3s ease',
    backdropFilter: 'blur(30px) saturate(180%)',
    WebkitBackdropFilter: 'blur(30px) saturate(180%)',
    textShadow: '0 1px 2px rgba(0, 0, 0, 0.1)',
    border: 'none',
  },
  startButton: {
    backgroundColor: 'rgba(22, 163, 74, 0.45)',
    color: '#ffffff',
    border: '2px solid rgba(22, 163, 74, 0.8)',
    boxShadow: '0 4px 20px rgba(22, 163, 74, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.7)',
  },
  stopButton: {
    backgroundColor: 'rgba(220, 38, 38, 0.45)',
    color: '#ffffff',
    border: '2px solid rgba(220, 38, 38, 0.8)',
    boxShadow: '0 4px 20px rgba(220, 38, 38, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.7)',
  },
};

export default ControlButtons;
