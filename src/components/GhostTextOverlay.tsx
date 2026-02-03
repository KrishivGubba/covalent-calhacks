import { useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';


export function GhostTextOverlay({ text, show }: { text: string, show: boolean }) {
    const overlayRef = useRef<HTMLDivElement>(null);
  
    useEffect(() => {
      if (!show || !text) return;
  
      // Get cursor position from system (via Tauri command)
      updatePosition();
    }, [show, text]);
  
    async function updatePosition() {
      // Call Rust to get current cursor screen position
      const pos = await invoke<{x: number, y: number}>('get_cursor_position');
      
      if (overlayRef.current) {
        overlayRef.current.style.left = `${pos.x}px`;
        overlayRef.current.style.top = `${pos.y}px`;
      }
    }
  
    if (!show) return null;
  
    return (
      <div 
        ref={overlayRef}
        className="ghost-text-overlay"
      >
        <span className="ghost-text">{text}</span>
      </div>
    );
  }
