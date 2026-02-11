import { useState, useEffect } from 'react';
import { listen } from '@tauri-apps/api/event';
import { invoke } from '@tauri-apps/api/core';

interface Suggestion {
  text: string;
  confidence: number;
  cache_level: string;
}

interface SuggestionEvent {
  payload: Suggestion;
}

function CompletionPopup() {
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [show, setShow] = useState(false);
  
  useEffect(() => {
    // Listen for suggestion events from Rust
    const unlistenPromise = listen('show-completion', (event: SuggestionEvent) => {
      console.log('📬 Received suggestion:', event.payload);
      setSuggestion(event.payload);
      setShow(true);
    });
    
    // Listen for hide events
    const unlistenHidePromise = listen('hide-completion', () => {
      setShow(false);
      setSuggestion(null);
    });
    
    // Global keyboard handler for Cmd+Return
    const handleKey = async (e: KeyboardEvent) => {
      if (e.metaKey && e.key === 'Enter' && show && suggestion) {
        e.preventDefault();
        console.log('✅ Accepting suggestion');
        
        try {
          await invoke('inject_completion_text', { text: suggestion.text });
          setShow(false);
          setSuggestion(null);
        } catch (error) {
          console.error('Failed to inject text:', error);
        }
      }
      
      if (e.key === 'Escape' && show) {
        console.log('❌ Dismissing suggestion');
        setShow(false);
        setSuggestion(null);
      }
    };
    
    window.addEventListener('keydown', handleKey);
    
    return () => {
      unlistenPromise.then(fn => fn());
      unlistenHidePromise.then(fn => fn());
      window.removeEventListener('keydown', handleKey);
    };
  }, [show, suggestion]);
  
  if (!show || !suggestion) {
    return null;
  }
  
  // Determine badge based on cache level
  const getBadge = (level: string) => {
    switch (level) {
      case 'L0':
        return { emoji: '⚡', text: 'Cached (3ms)' };
      case 'L1':
        return { emoji: '💾', text: 'Context (110ms)' };
      case 'L2':
        return { emoji: '🔍', text: 'Graph (130ms)' };
      case 'L3':
        return { emoji: '🆕', text: 'New (155ms)' };
      default:
        return { emoji: '💡', text: 'Suggestion' };
    }
  };
  
  const badge = getBadge(suggestion.cache_level);
  
  return (
    <div style={styles.overlay}>
      <div style={styles.popup}>
        <div style={styles.header}>
          <span style={styles.badge}>
            {badge.emoji} {badge.text}
          </span>
          <span style={styles.confidence}>
            {Math.round((suggestion.confidence || 0) * 100)}% confident
          </span>
        </div>
        
        <div style={styles.text}>
          {suggestion.text}
        </div>
        
        <div style={styles.hint}>
          <kbd style={styles.kbd}>⌥</kbd>+<kbd style={styles.kbd}>Tab</kbd> to accept · <kbd style={styles.kbd}>Esc</kbd> to dismiss
        </div>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 999999,
    backdropFilter: 'blur(4px)',
  },
  popup: {
    backgroundColor: '#1e1e1e',
    border: '1px solid #444',
    borderRadius: '12px',
    padding: '20px',
    minWidth: '400px',
    maxWidth: '600px',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.1)',
    animation: 'slideIn 0.2s ease-out',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  badge: {
    fontSize: '12px',
    color: '#888',
    fontWeight: 600,
  },
  confidence: {
    fontSize: '11px',
    color: '#666',
  },
  text: {
    color: '#fff',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace',
    fontSize: '14px',
    lineHeight: '1.6',
    marginBottom: '16px',
    whiteSpace: 'pre-wrap' as const,
    padding: '12px',
    backgroundColor: '#2a2a2a',
    borderRadius: '6px',
    border: '1px solid #333',
  },
  hint: {
    fontSize: '11px',
    color: '#666',
    textAlign: 'center' as const,
  },
  kbd: {
    backgroundColor: '#333',
    color: '#fff',
    padding: '2px 6px',
    borderRadius: '4px',
    fontSize: '10px',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace',
    border: '1px solid #444',
  },
};

// Add animation keyframes
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;
document.head.appendChild(styleSheet);

export default CompletionPopup;

