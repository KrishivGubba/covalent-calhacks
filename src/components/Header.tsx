import React from 'react';

interface HeaderProps {
  onProfileClick: () => void;
  onLinkMCPsClick: () => void;
}

const Header: React.FC<HeaderProps> = ({ onProfileClick, onLinkMCPsClick }) => {
  return (
    <header style={styles.header}>
      <div style={styles.logo}>
        <span style={styles.logoText}>AutoFlow</span>
      </div>
      <div style={styles.buttonContainer}>
        <button 
          style={styles.profileButton} 
          onClick={onProfileClick}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.35)';
            e.currentTarget.style.transform = 'translateY(-1px)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.15)';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          Profile
        </button>
        <button 
          style={styles.linkButton} 
          onClick={onLinkMCPsClick}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.35)';
            e.currentTarget.style.transform = 'translateY(-1px)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.2)';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          Link MCPs
        </button>
      </div>
    </header>
  );
};

const styles = {
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '1.25rem 2rem',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    backdropFilter: 'blur(30px)',
    borderBottom: '1px solid rgba(255, 255, 255, 0.3)',
    boxShadow: '0 4px 24px rgba(31, 38, 135, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.5)',
    position: 'relative' as const,
    zIndex: 10,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
  },
  logoText: {
    fontSize: '1.4rem',
    fontWeight: '700',
    color: '#1e293b',
    letterSpacing: '-0.02em',
  },
  buttonContainer: {
    display: 'flex',
    gap: '0.75rem',
  },
  profileButton: {
    padding: '0.625rem 1.5rem',
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    color: '#334155',
    border: '1px solid rgba(255, 255, 255, 0.4)',
    borderRadius: '12px',
    cursor: 'pointer',
    fontSize: '0.95rem',
    fontWeight: '600',
    transition: 'all 0.2s ease',
    backdropFilter: 'blur(20px)',
    boxShadow: '0 2px 12px rgba(31, 38, 135, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.6)',
  },
  linkButton: {
    padding: '0.625rem 1.5rem',
    backgroundColor: 'rgba(59, 130, 246, 0.2)',
    color: '#1e40af',
    border: '1px solid rgba(59, 130, 246, 0.3)',
    borderRadius: '12px',
    cursor: 'pointer',
    fontSize: '0.95rem',
    fontWeight: '600',
    transition: 'all 0.2s ease',
    backdropFilter: 'blur(20px)',
    boxShadow: '0 4px 16px rgba(59, 130, 246, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.6)',
  },
};

export default Header;
