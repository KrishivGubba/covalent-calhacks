import React from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';

export type PageType = 'settings' | 'mcp' | 'memory' | 'history' | 'auth';

interface SidebarProps {
  currentPage: PageType;
  onPageChange: (page: PageType) => void;
}

const SettingsIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path>
    <circle cx="12" cy="12" r="3"></circle>
  </svg>
);

const MCPIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
    <line x1="8" y1="21" x2="16" y2="21"></line>
    <line x1="12" y1="17" x2="12" y2="21"></line>
  </svg>
);

const MemoryIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"></circle>
    <circle cx="12" cy="12" r="6"></circle>
    <circle cx="12" cy="12" r="2"></circle>
  </svg>
);

const HistoryIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 3v5h5"></path>
    <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"></path>
    <path d="M12 7v5l4 2"></path>
  </svg>
);

const UserIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
    <circle cx="12" cy="7" r="4"></circle>
  </svg>
);

const Sidebar: React.FC<SidebarProps> = ({ currentPage, onPageChange }) => {
  const menuItems: { id: PageType; label: string; icon: () => React.JSX.Element }[] = [
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
    { id: 'mcp', label: 'Integrations', icon: MCPIcon },
    { id: 'memory', label: 'Memory Graph', icon: MemoryIcon },
    { id: 'history', label: 'History', icon: HistoryIcon },
  ];

  const profileItem = { id: 'auth' as PageType, label: 'Profile', icon: UserIcon };

  const getItemStyle = (id: PageType) => ({
    ...styles.menuItem,
    ...(currentPage === id ? styles.menuItemActive : {}),
  });

  const handleDragMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) getCurrentWindow().startDragging();
  };

  return (
    <div style={styles.sidebar}>
      <div
        onMouseDown={handleDragMouseDown}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '28px',
          cursor: 'default',
        }}
      />
      <div style={styles.logo}>
        <img src="/icon.png" alt="Covalent" style={styles.logoImage} />
        <h2 style={styles.logoText}>Covalent</h2>
      </div>

      <nav style={styles.nav}>
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;
          return (
            <button
              key={item.id}
              style={getItemStyle(item.id)}
              onClick={() => onPageChange(item.id)}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = '#EDE9E2';
                  e.currentTarget.style.color = '#1A1A1A';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.color = '#5A5A5A';
                }
              }}
            >
              <span style={styles.menuIcon}><Icon /></span>
              <span style={styles.menuLabel}>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div style={styles.profileSection}>
        <button
          style={getItemStyle(profileItem.id)}
          onClick={() => onPageChange(profileItem.id)}
          onMouseEnter={(e) => {
            if (currentPage !== profileItem.id) {
              e.currentTarget.style.backgroundColor = '#EDE9E2';
              e.currentTarget.style.color = '#1A1A1A';
            }
          }}
          onMouseLeave={(e) => {
            if (currentPage !== profileItem.id) {
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = '#5A5A5A';
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
    width: '220px',
    height: '100%',
    backgroundColor: '#F4F1EC',
    borderRight: '1px solid #E8E4DC',
    display: 'flex',
    flexDirection: 'column' as const,
    padding: '52px 12px 20px',
    fontFamily: 'DM Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
    position: 'relative' as const,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginBottom: '32px',
    padding: '6px 8px',
  },
  logoImage: {
    width: '28px',
    height: '28px',
    objectFit: 'contain' as const,
  },
  logoText: {
    fontSize: '1.1rem',
    fontWeight: '700',
    color: '#1A1A1A',
    margin: 0,
    letterSpacing: '-0.02em',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '2px',
    flex: 1,
  },
  menuItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 12px',
    backgroundColor: 'transparent',
    border: 'none',
    borderRadius: '10px',
    color: '#5A5A5A',
    fontSize: '0.875rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    textAlign: 'left' as const,
    width: '100%',
    fontFamily: 'inherit',
  },
  menuItemActive: {
    backgroundColor: 'rgba(193, 122, 95, 0.10)',
    color: '#C17A5F',
  },
  menuIcon: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '18px',
    height: '18px',
    flexShrink: 0,
  },
  menuLabel: {
    flex: 1,
  },
  profileSection: {
    marginTop: 'auto',
    paddingTop: '12px',
    borderTop: '1px solid #E8E4DC',
  },
};

export default Sidebar;
