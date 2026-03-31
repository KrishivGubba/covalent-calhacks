import React, { useState, useEffect, useCallback, useRef } from 'react';
import { listen } from '@tauri-apps/api/event';
import { invoke } from '@tauri-apps/api/core';
import Sidebar, { PageType } from './components/Sidebar';
import UpdateButton from './components/UpdateButton';
import AuthPage from './pages/AuthPage';
import SettingsPage from './pages/SettingsPage';
import MCPPage from './pages/MCPPage';
import MemoryPage from './pages/MemoryPage';
import HistoryPage from './pages/HistoryPage';
import type { ActionResultPayload } from '../utils/actionNotifications';
import { loadAuthStatus } from '../shared/authService';

const Dashboard: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<PageType>('settings');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const currentPageRef = useRef<PageType>('settings');

  const handlePageChange = useCallback((page: PageType) => {
    if (page === 'history' && currentPageRef.current !== 'history') {
      setHistoryRefreshKey(prev => prev + 1);
    }
    currentPageRef.current = page;
    setCurrentPage(page);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const syncAuth = async () => {
      try {
        const status = await loadAuthStatus();
        if (cancelled) return;
        setIsAuthenticated(status.authenticated);
        invoke('notify_auth_change', { authenticated: status.authenticated }).catch((err) =>
          console.error('Failed to notify initial auth state:', err)
        );
      } catch {
        if (cancelled) return;
        setIsAuthenticated(false);
        invoke('notify_auth_change', { authenticated: false }).catch((err) =>
          console.error('Failed to notify initial auth state:', err)
        );
      }
    };

    void syncAuth();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const unlistenPromise = listen<ActionResultPayload>('action-completed', (event) => {
      console.log('📬 Action completed event received:', event.payload);
      if (currentPageRef.current !== 'history') {
        setHistoryRefreshKey(prev => prev + 1);
        currentPageRef.current = 'history';
        setCurrentPage('history');
      }
    });

    return () => {
      unlistenPromise.then(fn => fn());
    };
  }, []);

  const handleAuthChange = (authenticated: boolean) => {
    setIsAuthenticated(authenticated);
    invoke('notify_auth_change', { authenticated }).catch((err) =>
      console.error('Failed to notify auth change:', err)
    );
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
        return <HistoryPage key={`history-${historyRefreshKey}`} />;
      case 'auth':
        return <AuthPage onAuthChange={handleAuthChange} />;
      default:
        return <SettingsPage />;
    }
  };

  return (
    <div style={styles.dashboard}>
      <UpdateButton checkInterval={30 * 60 * 1000} />
      <Sidebar currentPage={currentPage} onPageChange={handlePageChange} />
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
    backgroundColor: '#FAFAF8',
    overflow: 'hidden',
    fontFamily: 'DM Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
  },
  main: {
    flex: 1,
    overflowY: 'auto' as const,
    backgroundColor: '#FAFAF8',
  },
};

export default Dashboard;
