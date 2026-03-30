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
  
  // Track current page in a ref so handlePageChange can check without causing re-renders
  const currentPageRef = useRef<PageType>('settings');

  // Handle page changes with special handling for history tab
  // Only increment refresh key when navigating TO history FROM a different page
  const handlePageChange = useCallback((page: PageType) => {
    if (page === 'history' && currentPageRef.current !== 'history') {
      // Only force remount when coming from a different page
      setHistoryRefreshKey(prev => prev + 1);
    }
    currentPageRef.current = page;
    setCurrentPage(page);
  }, []);

  // Check auth status on mount and notify backend
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

  // Listen for action completion events and auto-navigate to history
  useEffect(() => {
    const unlistenPromise = listen<ActionResultPayload>('action-completed', (event) => {
      console.log('📬 Action completed event received:', event.payload);
      // Only navigate if not already on history page
      // HistoryPage has its own listener to refresh data when already viewing it
      if (currentPageRef.current !== 'history') {
        setHistoryRefreshKey(prev => prev + 1);
        currentPageRef.current = 'history';
        setCurrentPage('history');
      }
      // If already on history, do nothing - HistoryPage's listener handles refresh
    });
    
    return () => {
      unlistenPromise.then(fn => fn());
    };
  }, []);

  // Callback for when auth state changes (login/logout)
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
        // Key forces re-mount to ensure fresh data fetch each time
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
