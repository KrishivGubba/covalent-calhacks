import React, { useState, useEffect } from 'react';
import Sidebar, { PageType } from './components/Sidebar';
import UpdateButton from './components/UpdateButton';
import AuthPage from './pages/AuthPage';
import SettingsPage from './pages/SettingsPage';
import MCPPage from './pages/MCPPage';
import MemoryPage from './pages/MemoryPage';
import HistoryPage from './pages/HistoryPage';

// Must match the key used in AuthPage.tsx
const USER_ID_KEY = 'covalent_user_id';

const Dashboard: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<PageType>('settings');
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Check auth status on mount
  useEffect(() => {
    const userId = localStorage.getItem(USER_ID_KEY);
    setIsAuthenticated(!!userId);
  }, []);

  // Callback for when auth state changes (login/logout)
  const handleAuthChange = (authenticated: boolean) => {
    setIsAuthenticated(authenticated);
  };

  const renderPage = () => {
    switch (currentPage) {
      case 'settings':
        return <SettingsPage />;
      case 'mcp':
        return <MCPPage isAuthenticated={isAuthenticated} />;
      case 'memory':
        return <MemoryPage />;
      case 'history':
        return <HistoryPage />;
      case 'auth':
        return <AuthPage onAuthChange={handleAuthChange} />;
      default:
        return <SettingsPage />;
    }
  };

  return (
    <div style={styles.dashboard}>
      <UpdateButton checkInterval={30 * 60 * 1000} />
      <Sidebar currentPage={currentPage} onPageChange={setCurrentPage} />
      <main style={styles.main}>
        {renderPage()}
      </main>
    </div>
  );
};

const styles = {
  dashboard: {
    display: 'flex',
    height: '100vh',
    width: '100vw',
    backgroundColor: '#0a0a0a',
    overflow: 'hidden',
    fontFamily: 'DM Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
  },
  main: {
    flex: 1,
    overflowY: 'auto' as const,
    backgroundColor: '#0a0a0a',
  },
};

export default Dashboard;
