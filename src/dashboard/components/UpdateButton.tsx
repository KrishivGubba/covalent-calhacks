import React, { useState, useEffect } from 'react';
import { check, Update } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';
import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from '@tauri-apps/plugin-notification';

interface UpdateButtonProps {
  checkInterval?: number;
}

const UpdateButton: React.FC<UpdateButtonProps> = ({
  checkInterval = 30 * 60 * 1000
}) => {
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [updateInfo, setUpdateInfo] = useState<Update | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const sendUpdateNotification = async (version: string) => {
    try {
      let permissionGranted = await isPermissionGranted();
      if (!permissionGranted) {
        const permission = await requestPermission();
        permissionGranted = permission === 'granted';
      }
      if (permissionGranted) {
        sendNotification({
          title: 'Covalent Update Available',
          body: `Version ${version} is ready to install. Click the update button in the dashboard to install.`,
        });
      }
    } catch (e) {
      console.error('Failed to send notification:', e);
    }
  };

  const checkForUpdates = async (silent = false) => {
    if (isChecking) return;

    setIsChecking(true);
    setError(null);

    try {
      const token = sessionStorage.getItem('auth0_access_token');
      const update = await check({
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (update) {
        setUpdateAvailable(true);
        setUpdateInfo(update);
        if (!silent) {
          await sendUpdateNotification(update.version);
        }
      } else {
        setUpdateAvailable(false);
        setUpdateInfo(null);
      }
    } catch (e) {
      console.error('Failed to check for updates:', e);
      if (!silent) {
        setError('Failed to check for updates');
      }
    } finally {
      setIsChecking(false);
    }
  };

  const downloadAndInstall = async () => {
    if (!updateInfo || isDownloading) return;

    setIsDownloading(true);
    setError(null);

    try {
      let downloaded = 0;
      let contentLength = 0;

      await updateInfo.downloadAndInstall((event) => {
        switch (event.event) {
          case 'Started':
            contentLength = event.data.contentLength ?? 0;
            break;
          case 'Progress':
            downloaded += event.data.chunkLength;
            if (contentLength > 0) {
              setDownloadProgress(Math.round((downloaded / contentLength) * 100));
            }
            break;
          case 'Finished':
            setDownloadProgress(100);
            break;
        }
      });

      await relaunch();
    } catch (e) {
      console.error('Failed to download/install update:', e);
      setError('Failed to install update');
      setIsDownloading(false);
    }
  };

  useEffect(() => {
    checkForUpdates(true);

    const interval = setInterval(() => {
      checkForUpdates(true);
    }, checkInterval);

    return () => clearInterval(interval);
  }, [checkInterval]);

  if (!updateAvailable && !isChecking && !error) {
    return null;
  }

  return (
    <div style={styles.container}>
      {error && (
        <button
          style={{ ...styles.button, ...styles.errorButton }}
          onClick={() => checkForUpdates(false)}
          title={error}
        >
          <span style={styles.icon}>!</span>
          Retry
        </button>
      )}

      {isChecking && (
        <div style={{ ...styles.button, ...styles.checkingButton }}>
          <span style={styles.spinner}></span>
          Checking...
        </div>
      )}

      {updateAvailable && !isDownloading && !isChecking && !error && (
        <button
          style={styles.button}
          onClick={downloadAndInstall}
          title={`Update to v${updateInfo?.version}`}
        >
          <span style={styles.icon}>↓</span>
          Update v{updateInfo?.version}
        </button>
      )}

      {isDownloading && (
        <div style={{ ...styles.button, ...styles.downloadingButton }}>
          <div style={{ ...styles.progressBar, width: `${downloadProgress}%` }} />
          <span style={styles.progressText}>{downloadProgress}%</span>
        </div>
      )}
    </div>
  );
};

const styles: { [key: string]: React.CSSProperties } = {
  container: {
    position: 'fixed',
    top: 16,
    right: 16,
    zIndex: 9999,
    WebkitAppRegion: 'no-drag',
  } as React.CSSProperties,
  button: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 16px',
    backgroundColor: '#1A1A1A',
    color: '#FFFFFF',
    border: 'none',
    borderRadius: 100,
    fontSize: 12,
    fontWeight: 600,
    fontFamily: 'DM Sans, -apple-system, BlinkMacSystemFont, sans-serif',
    cursor: 'pointer',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.12)',
    transition: 'all 0.2s ease',
    position: 'relative',
    overflow: 'hidden',
  },
  errorButton: {
    backgroundColor: '#ef4444',
    boxShadow: '0 4px 12px rgba(239, 68, 68, 0.25)',
  },
  checkingButton: {
    backgroundColor: '#9A9A96',
    cursor: 'default',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
  },
  downloadingButton: {
    backgroundColor: '#F4F1EC',
    border: '1px solid #E8E4DC',
    color: '#1A1A1A',
    cursor: 'default',
    minWidth: 100,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.06)',
  },
  icon: {
    fontSize: 13,
    fontWeight: 'bold',
  },
  spinner: {
    width: 13,
    height: 13,
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: 'white',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  progressBar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: 'rgba(193, 122, 95, 0.25)',
    transition: 'width 0.3s ease',
    zIndex: 0,
  },
  progressText: {
    position: 'relative',
    zIndex: 1,
    color: '#1A1A1A',
  },
};

// Spinner keyframes
const styleSheet = document.createElement('style');
styleSheet.textContent = `@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`;
document.head.appendChild(styleSheet);

export default UpdateButton;
