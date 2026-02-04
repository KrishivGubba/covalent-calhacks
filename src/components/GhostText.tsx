import { useState, useEffect } from 'react';
import { listen } from '@tauri-apps/api/event';

interface GhostTextProps {
  text: string;
  confidence: number;
}

interface GhostTextEvent {
  payload: GhostTextProps;
}

function GhostText() {
  const [ghostText, setGhostText] = useState<GhostTextProps | null>(null);
  const [show, setShow] = useState(false);
  
  useEffect(() => {
    // Listen for ghost text events from Rust
    const unlistenPromise = listen('show-ghost-text', (event: GhostTextEvent) => {
      console.log('👻 Received ghost text:', event.payload);
      setGhostText(event.payload);
      setShow(true);
    });
    
    // Listen for hide events
    const unlistenHidePromise = listen('hide-ghost-text', () => {
      setShow(false);
      setGhostText(null);
    });
    
    return () => {
      unlistenPromise.then(fn => fn());
      unlistenHidePromise.then(fn => fn());
    };
  }, []);
  
  if (!show || !ghostText) {
    return null;
  }
  
  return (
    <div style={styles.container}>
      <span style={styles.ghostText}>
        {ghostText.text}
      </span>
    </div>
  );
}

const styles = {
  container: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    pointerEvents: 'none' as const,
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'flex-start',
    padding: '4px',
  },
  ghostText: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    fontSize: '13px',
    color: 'rgba(150, 150, 150, 0.8)',
    whiteSpace: 'pre' as const,
    textShadow: '0 0 1px rgba(0, 0, 0, 0.3)',
    letterSpacing: '0.01em',
  },
};

export default GhostText;

