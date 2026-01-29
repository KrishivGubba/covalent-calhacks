import React, { useState } from 'react';
import Sidebar, { PageType } from './components/Sidebar';
import AuthPage from './pages/AuthPage';
import SettingsPage from './pages/SettingsPage';
import MCPPage from './pages/MCPPage';
import MemoryPage from './pages/MemoryPage';
import HistoryPage from './pages/HistoryPage';

const Dashboard: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<PageType>('settings');

  const renderPage = () => {
    switch (currentPage) {
      case 'settings':
        return <SettingsPage />;
      case 'mcp':
        return <MCPPage />;
      case 'memory':
        return <MemoryPage />;
      case 'history':
        return <HistoryPage />;
      case 'auth':
        return <AuthPage />;
      default:
        return <SettingsPage />;
    }
  };

  return (
    <div style={styles.dashboard}>
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
    backgroundColor: '#0A0A12',
    overflow: 'hidden',
  },
  main: {
    flex: 1,
    overflowY: 'auto' as const,
    backgroundColor: '#0A0A12',
  },
};

export default Dashboard;
