import React, { useState, useEffect, useRef, useCallback } from 'react';

const BACKEND_URL = 'http://localhost:5001';

// ── Types ──────────────────────────────────────────────────────────────────────

interface GraphAction {
  uuid: string;
  name: string;
}

interface GraphDataEntry {
  uuid: string;
  key: string;
  type: string;
  category: string;
}

interface GraphNode {
  id: string;
  label: string;
  parent_id: string | null;
  depth: number;
  actions: GraphAction[];
  data: GraphDataEntry[];
}

interface GraphEdge {
  from: string;
  to: string;
}

interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    total_nodes: number;
    total_actions: number;
    total_data: number;
  };
}

// ── Layout helpers ─────────────────────────────────────────────────────────────

interface LayoutNode {
  id: string;
  label: string;
  depth: number;
  x: number;
  y: number;
  color: string;
  radius: number;
  actions: GraphAction[];
  data: GraphDataEntry[];
  childCount: number;
}

interface LayoutEdge {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

const COLORS = {
  root: '#e63946',
  level1: '#f77f00',
  level2: '#fcbf49',
  withActions: '#9b5de5',
  leaf: '#2a9d8f',
  deepLeaf: '#457b9d',
};

function getNodeColor(depth: number, hasActions: boolean, isRoot: boolean): string {
  if (isRoot) return COLORS.root;
  if (hasActions) return COLORS.withActions;
  if (depth === 1) return COLORS.level1;
  if (depth === 2) return COLORS.level2;
  if (depth >= 4) return COLORS.deepLeaf;
  return COLORS.leaf;
}

function computeLayout(nodes: GraphNode[], _edges: GraphEdge[]): { layoutNodes: LayoutNode[]; layoutEdges: LayoutEdge[] } {
  if (nodes.length === 0) return { layoutNodes: [], layoutEdges: [] };

  // Build children map
  const childrenMap: Record<string, string[]> = {};
  const nodeMap: Record<string, GraphNode> = {};
  let rootId: string | null = null;

  for (const node of nodes) {
    nodeMap[node.id] = node;
    childrenMap[node.id] = [];
    if (node.parent_id === null) rootId = node.id;
  }

  for (const node of nodes) {
    if (node.parent_id && childrenMap[node.parent_id]) {
      childrenMap[node.parent_id].push(node.id);
    }
  }

  // If no root found, use the first node
  if (!rootId && nodes.length > 0) rootId = nodes[0].id;
  if (!rootId) return { layoutNodes: [], layoutEdges: [] };

  // Compute subtree widths (leaf count)
  const subtreeWidth: Record<string, number> = {};
  function calcWidth(id: string): number {
    const children = childrenMap[id] || [];
    if (children.length === 0) {
      subtreeWidth[id] = 1;
      return 1;
    }
    let w = 0;
    for (const c of children) w += calcWidth(c);
    subtreeWidth[id] = w;
    return w;
  }
  calcWidth(rootId);

  const NODE_H_SPACING = 160;
  const NODE_V_SPACING = 120;

  // Assign positions
  const positions: Record<string, { x: number; y: number }> = {};

  function assignPositions(id: string, left: number, top: number) {
    const children = childrenMap[id] || [];
    const totalWidth = (subtreeWidth[id] || 1) * NODE_H_SPACING;
    const x = left + totalWidth / 2;
    const y = top;
    positions[id] = { x, y };

    let childLeft = left;
    for (const c of children) {
      const cw = (subtreeWidth[c] || 1) * NODE_H_SPACING;
      assignPositions(c, childLeft, top + NODE_V_SPACING);
      childLeft += cw;
    }
  }

  assignPositions(rootId, 0, 40);

  // Build layout nodes
  const layoutNodes: LayoutNode[] = nodes.map((node) => {
    const pos = positions[node.id] || { x: 0, y: 0 };
    const isRoot = node.parent_id === null;
    const hasActions = node.actions.length > 0;
    const radius = isRoot ? 22 : node.depth === 1 ? 18 : 14;
    return {
      id: node.id,
      label: node.label,
      depth: node.depth,
      x: pos.x,
      y: pos.y,
      color: getNodeColor(node.depth, hasActions, isRoot),
      radius,
      actions: node.actions,
      data: node.data,
      childCount: (childrenMap[node.id] || []).length,
    };
  });

  // Build layout edges
  const layoutEdges: LayoutEdge[] = [];
  for (const node of nodes) {
    if (node.parent_id && positions[node.parent_id] && positions[node.id]) {
      layoutEdges.push({
        fromX: positions[node.parent_id].x,
        fromY: positions[node.parent_id].y,
        toX: positions[node.id].x,
        toY: positions[node.id].y,
      });
    }
  }

  return { layoutNodes, layoutEdges };
}

// ── Tooltip component ──────────────────────────────────────────────────────────

const Tooltip: React.FC<{
  node: LayoutNode;
  mouseX: number;
  mouseY: number;
  containerRect: DOMRect;
}> = ({ node, mouseX, mouseY, containerRect }) => {
  const tooltipWidth = 280;
  const tooltipPad = 12;
  let left = mouseX - containerRect.left + 16;
  let top = mouseY - containerRect.top - 10;

  // Keep tooltip inside container
  if (left + tooltipWidth > containerRect.width) {
    left = mouseX - containerRect.left - tooltipWidth - 16;
  }
  if (top < 0) top = 8;

  return (
    <div
      style={{
        position: 'absolute',
        left,
        top,
        width: tooltipWidth,
        backgroundColor: '#1e1e2e',
        border: '1px solid #3a3a4a',
        borderRadius: 10,
        padding: tooltipPad,
        pointerEvents: 'none',
        zIndex: 100,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
      }}
    >
      <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#fff', marginBottom: 6 }}>
        {node.label}
      </div>
      <div style={{ fontSize: '0.75rem', color: '#71717a', fontFamily: 'monospace', marginBottom: 8 }}>
        {node.id.slice(0, 12)}...
      </div>
      {node.actions.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <div style={{ fontSize: '0.75rem', color: '#9b5de5', fontWeight: 600, marginBottom: 4 }}>
            Actions ({node.actions.length})
          </div>
          {node.actions.slice(0, 4).map((a, i) => (
            <div key={i} style={{ fontSize: '0.75rem', color: '#a1a1aa', paddingLeft: 8 }}>
              • {a.name.length > 40 ? a.name.slice(0, 40) + '...' : a.name}
            </div>
          ))}
          {node.actions.length > 4 && (
            <div style={{ fontSize: '0.7rem', color: '#71717a', paddingLeft: 8, fontStyle: 'italic' }}>
              +{node.actions.length - 4} more
            </div>
          )}
        </div>
      )}
      {node.data.length > 0 && (
        <div>
          <div style={{ fontSize: '0.75rem', color: '#2a9d8f', fontWeight: 600, marginBottom: 4 }}>
            Data ({node.data.length})
          </div>
          {node.data.slice(0, 3).map((d, i) => (
            <div key={i} style={{ fontSize: '0.75rem', color: '#a1a1aa', paddingLeft: 8 }}>
              • [{d.category || 'uncategorized'}] {d.key ? (d.key.length > 30 ? d.key.slice(0, 30) + '...' : d.key) : '(no key)'}
            </div>
          ))}
          {node.data.length > 3 && (
            <div style={{ fontSize: '0.7rem', color: '#71717a', paddingLeft: 8, fontStyle: 'italic' }}>
              +{node.data.length - 3} more
            </div>
          )}
        </div>
      )}
      {node.actions.length === 0 && node.data.length === 0 && (
        <div style={{ fontSize: '0.75rem', color: '#52525b', fontStyle: 'italic' }}>
          No actions or data
        </div>
      )}
    </div>
  );
};

// ── Graph canvas component ─────────────────────────────────────────────────────

const GraphVisualization: React.FC<{
  nodes: GraphNode[];
  edges: GraphEdge[];
}> = ({ nodes, edges }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredNode, setHoveredNode] = useState<LayoutNode | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const [containerRect, setContainerRect] = useState<DOMRect | null>(null);

  const { layoutNodes, layoutEdges } = computeLayout(nodes, edges);

  // Compute SVG viewBox bounds from layout
  const padding = 60;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of layoutNodes) {
    if (n.x - n.radius < minX) minX = n.x - n.radius;
    if (n.x + n.radius > maxX) maxX = n.x + n.radius;
    if (n.y - n.radius < minY) minY = n.y - n.radius;
    if (n.y + n.radius > maxY) maxY = n.y + n.radius;
  }
  if (!isFinite(minX)) { minX = 0; maxX = 800; minY = 0; maxY = 600; }
  const svgWidth = maxX - minX + padding * 2;
  const svgHeight = maxY - minY + padding * 2;
  const offsetX = -minX + padding;
  const offsetY = -minY + padding;

  // Update container rect on mount + resize
  useEffect(() => {
    const update = () => {
      if (containerRef.current) setContainerRect(containerRef.current.getBoundingClientRect());
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  // Center the graph initially when layout changes
  useEffect(() => {
    if (containerRef.current && layoutNodes.length > 0) {
      const rect = containerRef.current.getBoundingClientRect();
      const scaleX = rect.width / svgWidth;
      const scaleY = rect.height / svgHeight;
      const fitScale = Math.min(scaleX, scaleY, 1) * 0.9;
      const cx = (rect.width - svgWidth * fitScale) / 2;
      const cy = (rect.height - svgHeight * fitScale) / 2;
      setTransform({ x: cx, y: cy, scale: fitScale });
    }
  }, [layoutNodes.length, svgWidth, svgHeight]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setTransform((prev) => {
      const newScale = Math.min(Math.max(prev.scale * delta, 0.1), 4);
      // Zoom toward mouse position
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return { ...prev, scale: newScale };
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const newX = mx - (mx - prev.x) * (newScale / prev.scale);
      const newY = my - (my - prev.y) * (newScale / prev.scale);
      return { x: newX, y: newY, scale: newScale };
    });
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsPanning(true);
    setPanStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
  }, [transform.x, transform.y]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    setMousePos({ x: e.clientX, y: e.clientY });
    if (isPanning) {
      setTransform((prev) => ({ ...prev, x: e.clientX - panStart.x, y: e.clientY - panStart.y }));
    }
  }, [isPanning, panStart]);

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        cursor: isPanning ? 'grabbing' : 'grab',
      }}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => { setIsPanning(false); setHoveredNode(null); }}
    >
      <svg
        width={svgWidth}
        height={svgHeight}
        style={{
          transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
          transformOrigin: '0 0',
        }}
      >
        <defs>
          {/* Glow filter for hovered nodes */}
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Edges */}
        {layoutEdges.map((edge, i) => {
          const fx = edge.fromX + offsetX;
          const fy = edge.fromY + offsetY;
          const tx = edge.toX + offsetX;
          const ty = edge.toY + offsetY;
          const midY = (fy + ty) / 2;
          return (
            <path
              key={`edge-${i}`}
              d={`M ${fx} ${fy} C ${fx} ${midY}, ${tx} ${midY}, ${tx} ${ty}`}
              fill="none"
              stroke="#3a3a4a"
              strokeWidth={1.5}
              opacity={0.6}
            />
          );
        })}

        {/* Nodes */}
        {layoutNodes.map((node) => {
          const nx = node.x + offsetX;
          const ny = node.y + offsetY;
          const isHovered = hoveredNode?.id === node.id;
          // Truncate label for display
          const displayLabel = node.label.length > 20 ? node.label.slice(0, 18) + '...' : node.label;
          return (
            <g
              key={node.id}
              onMouseEnter={() => setHoveredNode(node)}
              onMouseLeave={() => setHoveredNode(null)}
              style={{ cursor: 'pointer' }}
            >
              {/* Node circle */}
              <circle
                cx={nx}
                cy={ny}
                r={isHovered ? node.radius + 3 : node.radius}
                fill={node.color}
                opacity={isHovered ? 1 : 0.85}
                filter={isHovered ? 'url(#glow)' : undefined}
                stroke={isHovered ? '#fff' : 'rgba(255,255,255,0.1)'}
                strokeWidth={isHovered ? 2 : 1}
                style={{ transition: 'r 0.15s ease, opacity 0.15s ease' }}
              />
              {/* Badge: action count */}
              {node.actions.length > 0 && (
                <>
                  <circle
                    cx={nx + node.radius * 0.7}
                    cy={ny - node.radius * 0.7}
                    r={8}
                    fill="#9b5de5"
                    stroke="#1a1a2e"
                    strokeWidth={1.5}
                  />
                  <text
                    x={nx + node.radius * 0.7}
                    y={ny - node.radius * 0.7 + 3.5}
                    textAnchor="middle"
                    fill="#fff"
                    fontSize={9}
                    fontWeight={700}
                  >
                    {node.actions.length}
                  </text>
                </>
              )}
              {/* Label */}
              <text
                x={nx}
                y={ny + node.radius + 16}
                textAnchor="middle"
                fill="#d4d4d8"
                fontSize={11}
                fontFamily="Inter, system-ui, sans-serif"
                fontWeight={500}
              >
                {displayLabel}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Tooltip overlay (HTML, positioned outside SVG for cleaner rendering) */}
      {hoveredNode && containerRect && (
        <Tooltip node={hoveredNode} mouseX={mousePos.x} mouseY={mousePos.y} containerRect={containerRect} />
      )}
    </div>
  );
};

// ── Legend ──────────────────────────────────────────────────────────────────────

const Legend: React.FC = () => {
  const items = [
    { color: COLORS.root, label: 'Root' },
    { color: COLORS.level1, label: 'Level 1' },
    { color: COLORS.level2, label: 'Level 2' },
    { color: COLORS.leaf, label: 'Leaf' },
    { color: COLORS.withActions, label: 'Has Actions' },
  ];
  return (
    <div style={{
      display: 'flex',
      gap: 16,
      padding: '10px 16px',
      backgroundColor: 'rgba(20, 20, 20, 0.6)',
      borderRadius: 8,
      border: '1px solid #27272a',
      flexWrap: 'wrap',
    }}>
      {items.map((item) => (
        <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            backgroundColor: item.color, flexShrink: 0,
          }} />
          <span style={{ fontSize: '0.75rem', color: '#a1a1aa' }}>{item.label}</span>
        </div>
      ))}
    </div>
  );
};

// ── Main Page ──────────────────────────────────────────────────────────────────

const MemoryPage: React.FC = () => {
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const loadGraphData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${BACKEND_URL}/graph/data`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data: GraphResponse = await response.json();
      setGraphData(data);
    } catch (err: any) {
      console.error('Failed to load graph data:', err);
      setError(err.message || 'Failed to load graph data');
    } finally {
      setLoading(false);
    }
  };

  const handleClearGraph = () => {
    setShowConfirmDialog(true);
  };

  const confirmClearGraph = async () => {
    setShowConfirmDialog(false);
    setResetting(true);
    setError(null);
    try {
      console.log('Calling graph reset endpoint...');
      const response = await fetch(`${BACKEND_URL}/graph/reset`, { method: 'POST' });
      console.log('Graph reset response status:', response.status);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${response.status}`);
      }
      const result = await response.json();
      console.log('Graph reset result:', result);
      // Clear UI immediately, then reload fresh data
      setGraphData(null);
      await loadGraphData();
    } catch (err: any) {
      console.error('Failed to reset graph:', err);
      setError(err.message || 'Failed to reset graph');
    } finally {
      setResetting(false);
    }
  };

  useEffect(() => {
    loadGraphData();
  }, []);

  const hasData = graphData && graphData.nodes.length > 0;

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Memory Graph</h1>
          <p style={styles.subtitle}>
            Visualize your knowledge graph and memory structure
          </p>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={styles.errorBanner}>
          <span>{error}</span>
          <button style={styles.errorDismiss} onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Stats bar */}
      {hasData && graphData && (
        <div style={styles.statsBar}>
          <div style={styles.statItem}>
            <span style={styles.statValue}>{graphData.stats.total_nodes}</span>
            <span style={styles.statLabel}>Nodes</span>
          </div>
          <div style={styles.statDivider} />
          <div style={styles.statItem}>
            <span style={styles.statValue}>{graphData.edges.length}</span>
            <span style={styles.statLabel}>Edges</span>
          </div>
          <div style={styles.statDivider} />
          <div style={styles.statItem}>
            <span style={styles.statValue}>{graphData.stats.total_actions}</span>
            <span style={styles.statLabel}>Actions</span>
          </div>
          <div style={styles.statDivider} />
          <div style={styles.statItem}>
            <span style={styles.statValue}>{graphData.stats.total_data}</span>
            <span style={styles.statLabel}>Data</span>
          </div>
        </div>
      )}

      {/* Main graph area */}
      {loading ? (
        <div style={styles.graphContainer}>
          <div style={styles.loadingState}>
            <div style={styles.spinner} />
            <p style={styles.loadingText}>Loading graph...</p>
          </div>
        </div>
      ) : hasData && graphData ? (
        <div style={styles.graphContainer}>
          <GraphVisualization nodes={graphData.nodes} edges={graphData.edges} />
        </div>
      ) : (
        <div style={styles.emptyState}>
          <div style={styles.emptyIcon}>⬡</div>
          <h3 style={styles.emptyTitle}>No Memory Data</h3>
          <p style={styles.emptyText}>
            Your knowledge graph is empty. Start using Covalent to build your memory graph.
          </p>
        </div>
      )}

      {/* Legend + Actions */}
      <div style={styles.footer}>
        {hasData && <Legend />}
        <div style={styles.actionButtons}>
          <button style={styles.refreshButton} onClick={loadGraphData} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          <button
            style={styles.clearButton}
            onClick={handleClearGraph}
            disabled={resetting || loading}
          >
            {resetting ? 'Resetting...' : 'Clear Graph'}
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div style={styles.dialogOverlay}>
          <div style={styles.dialogBox}>
            <h3 style={styles.dialogTitle}>Clear Graph?</h3>
            <p style={styles.dialogText}>
              This will permanently delete all nodes, actions, and data from your knowledge graph. This action cannot be undone.
            </p>
            <div style={styles.dialogButtons}>
              <button
                style={styles.dialogCancelBtn}
                onClick={() => setShowConfirmDialog(false)}
              >
                Cancel
              </button>
              <button
                style={styles.dialogConfirmBtn}
                onClick={confirmClearGraph}
              >
                Yes, Clear Everything
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Styles ─────────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '32px 40px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    marginBottom: '20px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: '1.75rem',
    fontWeight: 600,
    color: '#ffffff',
    margin: '0 0 6px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.9rem',
    color: '#71717a',
    margin: 0,
  },
  errorBanner: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'rgba(230, 57, 70, 0.1)',
    border: '1px solid rgba(230, 57, 70, 0.3)',
    borderRadius: 8,
    padding: '10px 16px',
    marginBottom: 16,
    color: '#e63946',
    fontSize: '0.85rem',
  },
  errorDismiss: {
    background: 'none',
    border: 'none',
    color: '#e63946',
    fontSize: '1.1rem',
    cursor: 'pointer',
    padding: '0 4px',
  },
  statsBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 20,
    marginBottom: 16,
    padding: '12px 20px',
    backgroundColor: '#141414',
    borderRadius: 10,
    border: '1px solid #27272a',
  },
  statItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 2,
  },
  statValue: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#ffffff',
    fontVariantNumeric: 'tabular-nums',
  },
  statLabel: {
    fontSize: '0.7rem',
    color: '#71717a',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  statDivider: {
    width: 1,
    height: 28,
    backgroundColor: '#27272a',
  },
  graphContainer: {
    flex: 1,
    minHeight: 400,
    backgroundColor: '#0d0d12',
    borderRadius: 12,
    border: '1px solid #27272a',
    overflow: 'hidden',
    position: 'relative',
  },
  loadingState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    gap: 12,
  },
  spinner: {
    width: 28,
    height: 28,
    border: '3px solid #27272a',
    borderTopColor: '#C5F467',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  loadingText: {
    color: '#71717a',
    fontSize: '0.9rem',
  },
  emptyState: {
    flex: 1,
    minHeight: 400,
    backgroundColor: '#0d0d12',
    borderRadius: 12,
    border: '1px solid #27272a',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 48,
  },
  emptyIcon: {
    fontSize: '2.5rem',
    color: '#27272a',
    marginBottom: 16,
  },
  emptyTitle: {
    fontSize: '1.15rem',
    fontWeight: 600,
    color: '#ffffff',
    marginBottom: 8,
  },
  emptyText: {
    fontSize: '0.85rem',
    color: '#52525b',
    lineHeight: 1.6,
    textAlign: 'center',
    maxWidth: 400,
  },
  footer: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 16,
    gap: 16,
    flexWrap: 'wrap',
  },
  actionButtons: {
    display: 'flex',
    gap: 10,
    marginLeft: 'auto',
  },
  refreshButton: {
    padding: '9px 20px',
    backgroundColor: '#C5F467',
    border: 'none',
    borderRadius: 8,
    color: '#0a0a0a',
    fontSize: '0.82rem',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  clearButton: {
    padding: '9px 20px',
    backgroundColor: 'transparent',
    border: '1px solid rgba(230, 57, 70, 0.4)',
    borderRadius: 8,
    color: '#e63946',
    fontSize: '0.82rem',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  dialogOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  dialogBox: {
    backgroundColor: '#1a1a1f',
    borderRadius: 12,
    padding: '28px 32px',
    maxWidth: 420,
    width: '90%',
    border: '1px solid #27272a',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
  },
  dialogTitle: {
    fontSize: '1.15rem',
    fontWeight: 600,
    color: '#ffffff',
    marginBottom: 12,
    marginTop: 0,
  },
  dialogText: {
    fontSize: '0.88rem',
    color: '#a1a1aa',
    lineHeight: 1.6,
    marginBottom: 24,
  },
  dialogButtons: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 10,
  },
  dialogCancelBtn: {
    padding: '10px 20px',
    backgroundColor: 'transparent',
    border: '1px solid #27272a',
    borderRadius: 8,
    color: '#ffffff',
    fontSize: '0.82rem',
    fontWeight: 500,
    cursor: 'pointer',
  },
  dialogConfirmBtn: {
    padding: '10px 20px',
    backgroundColor: '#e63946',
    border: 'none',
    borderRadius: 8,
    color: '#ffffff',
    fontSize: '0.82rem',
    fontWeight: 600,
    cursor: 'pointer',
  },
};

export default MemoryPage;
