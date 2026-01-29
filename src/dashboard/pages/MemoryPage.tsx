import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';

interface GraphNode {
  id: string;
  label: string;
  metadata: string;
}

interface GraphEdge {
  from: string;
  to: string;
}

interface MemoryGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const MemoryPage: React.FC = () => {
  const [graphData, setGraphData] = useState<MemoryGraphData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadGraphData();
  }, []);

  const loadGraphData = async () => {
    try {
      const data = await invoke<MemoryGraphData>('get_memory_graph_data');
      setGraphData(data);
    } catch (error) {
      console.error('Failed to load memory graph:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingText}>Loading...</div>
      </div>
    );
  }

  const hasData = graphData && graphData.nodes.length > 0;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>Memory Graph</h1>
        <p style={styles.subtitle}>
          Visualize your knowledge graph and memory structure
        </p>
      </div>

      {hasData ? (
        <div style={styles.graphContainer}>
          <div style={styles.graphPlaceholder}>
            <h3 style={styles.graphTitle}>Memory Graph Loaded</h3>
            <p style={styles.graphStats}>
              {graphData.nodes.length} nodes · {graphData.edges.length} edges
            </p>
            <div style={styles.nodeList}>
              {graphData.nodes.slice(0, 5).map((node) => (
                <div key={node.id} style={styles.nodeItem}>
                  <span style={styles.nodeLabel}>{node.label}</span>
                  <span style={styles.nodeId}>{node.id.slice(0, 8)}...</span>
                </div>
              ))}
              {graphData.nodes.length > 5 && (
                <div style={styles.moreNodes}>
                  +{graphData.nodes.length - 5} more nodes
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div style={styles.emptyState}>
          <h3 style={styles.emptyTitle}>No Memory Data</h3>
          <p style={styles.emptyText}>
            Your knowledge graph is empty. Start using Covalent to build your memory graph.
          </p>
        </div>
      )}

      <div style={styles.constructionNote}>
        Under Construction
      </div>

      <div style={styles.actionButtons}>
        <button style={styles.refreshButton} onClick={loadGraphData}>
          Refresh Data
        </button>
        <button
          style={styles.exportButton}
          onClick={() => {
            console.log('Export clicked');
            alert('Export under construction');
          }}
        >
          Export Graph
        </button>
      </div>
    </div>
  );
};

const styles = {
  container: {
    padding: '40px',
    maxWidth: '1000px',
  },
  header: {
    marginBottom: '32px',
  },
  title: {
    fontSize: '1.75rem',
    fontWeight: '600',
    color: '#FFFFFF',
    margin: '0 0 8px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: 'rgba(255, 255, 255, 0.5)',
    margin: 0,
  },
  graphContainer: {
    backgroundColor: 'rgba(20, 20, 30, 0.6)',
    borderRadius: '12px',
    padding: '40px 32px',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    marginBottom: '24px',
    minHeight: '400px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  graphPlaceholder: {
    textAlign: 'center' as const,
    maxWidth: '600px',
  },
  graphTitle: {
    fontSize: '1.25rem',
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: '12px',
  },
  graphStats: {
    fontSize: '0.9rem',
    color: 'rgba(255, 255, 255, 0.5)',
    marginBottom: '28px',
  },
  nodeList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
    maxWidth: '400px',
    margin: '0 auto',
  },
  nodeItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '10px 16px',
    backgroundColor: 'rgba(30, 30, 45, 0.5)',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.05)',
  },
  nodeLabel: {
    color: 'rgba(255, 255, 255, 0.8)',
    fontSize: '0.85rem',
  },
  nodeId: {
    color: 'rgba(255, 255, 255, 0.4)',
    fontSize: '0.75rem',
    fontFamily: 'monospace',
  },
  moreNodes: {
    padding: '8px',
    color: 'rgba(255, 255, 255, 0.5)',
    fontSize: '0.8rem',
    fontStyle: 'italic',
  },
  emptyState: {
    backgroundColor: 'rgba(20, 20, 30, 0.6)',
    borderRadius: '12px',
    padding: '64px 32px',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    textAlign: 'center' as const,
    marginBottom: '24px',
  },
  emptyTitle: {
    fontSize: '1.25rem',
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: '12px',
  },
  emptyText: {
    fontSize: '0.9rem',
    color: 'rgba(255, 255, 255, 0.4)',
    lineHeight: '1.6',
  },
  loadingText: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: '0.95rem',
  },
  constructionNote: {
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    border: '1px solid rgba(99, 102, 241, 0.2)',
    borderRadius: '8px',
    padding: '12px 16px',
    color: 'rgba(255, 255, 255, 0.7)',
    fontSize: '0.85rem',
    textAlign: 'center' as const,
    marginBottom: '24px',
  },
  actionButtons: {
    display: 'flex',
    gap: '12px',
  },
  refreshButton: {
    padding: '10px 20px',
    backgroundColor: '#6366F1',
    border: 'none',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  exportButton: {
    padding: '10px 20px',
    backgroundColor: 'transparent',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '0.85rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
};

export default MemoryPage;
