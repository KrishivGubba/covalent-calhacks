import React from 'react';

export type PageType = 'settings' | 'mcp' | 'memory' | 'history' | 'auth';

interface SidebarProps {
  currentPage: PageType;
  onPageChange: (page: PageType) => void;
}

// SVG Icon Components
const SettingsIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"></circle>
    <path d="M12 1v6m0 6v6m0-6h6m-6 0H6m12.36-7.36l-4.24 4.24m0 5.66l4.24 4.24M6.64 6.64l4.24 4.24m0 5.66l-4.24 4.24"></path>
  </svg>
);

const MCPIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 9l6 6 6-6"></path>
    <path d="M6 15l6 6 6-6"></path>
  </svg>
);

const MemoryIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"></circle>
    <circle cx="12" cy="12" r="6"></circle>
    <circle cx="12" cy="12" r="2"></circle>
  </svg>
);

const HistoryIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 3v5h5"></path>
    <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"></path>
    <path d="M12 7v5l4 2"></path>
  </svg>
);

const UserIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
    <circle cx="12" cy="7" r="4"></circle>
  </svg>
);

const Sidebar: React.FC<SidebarProps> = ({ currentPage, onPageChange }) => {
  const menuItems: { id: PageType; label: string; icon: () => JSX.Element }[] = [
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
    { id: 'mcp', label: 'Integrations', icon: MCPIcon },
    { id: 'memory', label: 'Memory Graph', icon: MemoryIcon },
    { id: 'history', label: 'History', icon: HistoryIcon },
  ];

  const profileItem = { id: 'auth' as PageType, label: 'Profile', icon: UserIcon };

  return (
    <div style={styles.sidebar}>
      <div style={styles.logo}>
        <img src="/icon.png" alt="Covalent" style={styles.logoImage} />
        <h2 style={styles.logoText}>Covalent</h2>
      </div>
      
      <nav style={styles.nav}>
        {menuItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              style={{
                ...styles.menuItem,
                ...(currentPage === item.id ? styles.menuItemActive : {}),
              }}
              onClick={() => onPageChange(item.id)}
              onMouseEnter={(e) => {
                if (currentPage !== item.id) {
                  e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
                }
              }}
              onMouseLeave={(e) => {
                if (currentPage !== item.id) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
            >
              <span style={styles.menuIcon}><Icon /></span>
              <span style={styles.menuLabel}>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Profile at the bottom */}
      <div style={styles.profileSection}>
        <button
          style={{
            ...styles.menuItem,
            ...(currentPage === profileItem.id ? styles.menuItemActive : {}),
          }}
          onClick={() => onPageChange(profileItem.id)}
          onMouseEnter={(e) => {
            if (currentPage !== profileItem.id) {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
            }
          }}
          onMouseLeave={(e) => {
            if (currentPage !== profileItem.id) {
              e.currentTarget.style.backgroundColor = 'transparent';
            }
          }}
        >
          <span style={styles.menuIcon}><UserIcon /></span>
          <span style={styles.menuLabel}>{profileItem.label}</span>
        </button>
      </div>
    </div>
  );
};

const styles = {
  sidebar: {
    width: '250px',
    height: '100%',
    backgroundColor: '#0F0F1A',
    borderRight: '1px solid rgba(255, 255, 255, 0.08)',
    display: 'flex',
    flexDirection: 'column' as const,
    padding: '24px 16px',
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '40px',
    padding: '8px',
  },
  logoImage: {
    width: '32px',
    height: '32px',
    objectFit: 'contain' as const,
  },
  logoText: {
    fontSize: '1.4rem',
    fontWeight: '600',
    color: '#FFFFFF',
    margin: 0,
    letterSpacing: '-0.02em',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '4px',
    flex: 1,
  },
  menuItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px 16px',
    backgroundColor: 'transparent',
    border: 'none',
    borderRadius: '10px',
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: '0.9rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    textAlign: 'left' as const,
    width: '100%',
  },
  menuItemActive: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    color: '#FFFFFF',
    borderLeft: '3px solid #6366F1',
  },
  menuIcon: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '20px',
    height: '20px',
  },
  menuLabel: {
    flex: 1,
  },
  profileSection: {
    marginTop: 'auto',
    paddingTop: '16px',
    borderTop: '1px solid rgba(255, 255, 255, 0.08)',
  },
};

export default Sidebar;
