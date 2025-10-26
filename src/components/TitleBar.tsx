import React from 'react';

interface TitleBarProps {
  onProfileClick: () => void;
  onLinkMCPsClick: () => void;
  isRunning: boolean;
}

const TitleBar: React.FC<TitleBarProps> = ({ onProfileClick, onLinkMCPsClick, isRunning }) => {
  return (
    <div style={styles.titleBar} data-tauri-drag-region>
      <div style={styles.leftSection}>
        <span style={styles.appName}>Covalent</span>
        {isRunning && (
          <div style={styles.statusIndicator}>
            <div style={styles.statusDot}></div>
            <span style={styles.statusText}>learning</span>
          </div>
        )}
      </div>
      <div style={styles.rightSection}>
        <button 
          style={styles.menuButton} 
          onClick={onProfileClick}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.15)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
        >
          Profile
        </button>
        <button 
          style={styles.menuButton} 
          onClick={onLinkMCPsClick}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.15)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
        >
          Link MCPs
        </button>
      </div>
    </div>
  );
};

const styles = {
  titleBar: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    height: '40px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0 1rem',
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    backdropFilter: 'blur(20px) saturate(180%)',
    WebkitBackdropFilter: 'blur(20px) saturate(180%)',
    borderBottom: '1px solid rgba(255, 255, 255, 0.2)',
    zIndex: 1000,
  },
  leftSection: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
  },
  appName: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#000000',
    textShadow: '0 1px 2px rgba(255, 255, 255, 0.3)',
  },
  statusIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    padding: '0.3rem 0.6rem',
    backgroundColor: 'rgba(34, 197, 94, 0.12)',
    borderRadius: '12px',
    border: '1px solid rgba(34, 197, 94, 0.25)',
  },
  statusDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    backgroundColor: '#22c55e',
    boxShadow: '0 0 8px rgba(34, 197, 94, 0.5)',
    animation: 'pulse 2s ease-in-out infinite',
  },
  statusText: {
    fontSize: '0.7rem',
    fontWeight: '600',
    color: '#22c55e',
  },
  rightSection: {
    display: 'flex',
    gap: '0.5rem',
  },
  menuButton: {
    padding: '0.4rem 0.8rem',
    fontSize: '0.8rem',
    fontWeight: '500',
    color: '#000000',
    backgroundColor: 'transparent',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    textShadow: '0 1px 2px rgba(255, 255, 255, 0.2)',
  },
};

export default TitleBar;

