import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceRadial,
  forceSimulation,
} from 'd3-force';

const FLASK_PORT = import.meta.env.VITE_FLASK_PORT || '15001';
const BACKEND_URL = `http://localhost:${FLASK_PORT}`;

interface GraphDataPreview {
  label: string;
  category: string | null;
}

interface GraphNode {
  id: string;
  label: string;
  parent_id: string | null;
  depth: number;
  child_count: number;
  action_count: number;
  data_count: number;
  action_previews: string[];
  data_previews: GraphDataPreview[];
  path_labels: string[];
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

interface ForceNode extends GraphNode {
  radius: number;
  topLevelId: string;
  seedAngle: number;
  fill: string;
  stroke: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

interface ForceLink {
  source: string | ForceNode;
  target: string | ForceNode;
}

interface LayoutNode extends GraphNode {
  x: number;
  y: number;
  radius: number;
  fill: string;
  stroke: string;
  topLevelId: string;
  hasContent: boolean;
}

interface LayoutEdge {
  id: string;
  path: string;
}

interface ClusterHalo {
  id: string;
  label: string;
  x: number;
  y: number;
  radius: number;
  fill: string;
  stroke: string;
}

interface LayoutResult {
  layoutNodes: LayoutNode[];
  layoutEdges: LayoutEdge[];
  halos: ClusterHalo[];
  svgWidth: number;
  svgHeight: number;
  offsetX: number;
  offsetY: number;
}

type CustomForce = {
  (alpha: number): void;
  initialize?: (nodes: ForceNode[]) => void;
};

const GRAPH_BACKGROUND = {
  base: '#F6F1E7',
  ink: '#1A1A1A',
  muted: '#6B655D',
  grid: 'rgba(85, 69, 54, 0.08)',
  link: 'rgba(113, 103, 90, 0.34)',
  rootFill: '#C77753',
  rootStroke: '#8D4D34',
};

const BRANCH_THEMES = [
  { node: '#5F7DDE', stroke: '#3552AE', halo: 'rgba(95, 125, 222, 0.16)' },
  { node: '#2C9A8B', stroke: '#17655B', halo: 'rgba(44, 154, 139, 0.16)' },
  { node: '#D18A45', stroke: '#9F5E21', halo: 'rgba(209, 138, 69, 0.16)' },
  { node: '#A76BC7', stroke: '#764595', halo: 'rgba(167, 107, 199, 0.16)' },
  { node: '#D06272', stroke: '#993A4B', halo: 'rgba(208, 98, 114, 0.16)' },
  { node: '#708E4E', stroke: '#4F6634', halo: 'rgba(112, 142, 78, 0.16)' },
];

const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);

function truncateLabel(label: string, maxLength: number): string {
  return label.length > maxLength ? `${label.slice(0, maxLength - 1)}…` : label;
}

function getReadableNodeLabel(label: string): string {
  const normalized = label.replace(/\s+/g, ' ').trim();
  if (!normalized) return 'Untitled';

  const bracketMatch = normalized.match(/\]\s*(.+)$/);
  const withoutPrefix = bracketMatch?.[1]?.trim() || normalized;
  const dashParts = withoutPrefix.split(' - ').map((part) => part.trim()).filter(Boolean);
  if (dashParts.length > 1) {
    const tail = dashParts[dashParts.length - 1];
    if (tail.length >= 8) return tail;
  }

  const slashParts = withoutPrefix.split('/').map((part) => part.trim()).filter(Boolean);
  if (slashParts.length > 1) {
    const tail = slashParts[slashParts.length - 1];
    if (tail && tail.length <= 42) return tail.replace(/[_-]+/g, ' ');
  }

  return withoutPrefix.replace(/[_]+/g, ' ');
}

function hashAngle(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) % 360;
  }
  return (hash / 180) * Math.PI;
}

function getTopLevelId(node: GraphNode, nodeMap: Map<string, GraphNode>, rootId: string): string {
  if (node.id === rootId) return rootId;

  let current: GraphNode | undefined = node;
  let lastBeforeRoot = node.id;
  const seen = new Set<string>();

  while (current && current.parent_id && !seen.has(current.id)) {
    seen.add(current.id);
    if (current.parent_id === rootId) {
      return current.id;
    }
    lastBeforeRoot = current.parent_id;
    current = nodeMap.get(current.parent_id);
  }

  return lastBeforeRoot;
}

function getNodeRadius(node: GraphNode, isRoot: boolean): number {
  if (isRoot) return 30;

  const contentWeight = Math.min(node.action_count + node.data_count, 8) * 1.2;
  const branchWeight = Math.min(node.child_count, 6) * 1.4;
  const depthAdjustment = node.depth === 1 ? 8 : node.depth === 2 ? 3 : -1;
  return clamp(11 + contentWeight + branchWeight + depthAdjustment, 11, 24);
}

function createSiblingClusterForce(parentAngles: Record<string, number>): CustomForce {
  let nodes: ForceNode[] = [];

  const force = ((alpha: number) => {
    const siblingGroups = new Map<string, ForceNode[]>();

    for (const node of nodes) {
      if (!node.parent_id) continue;
      const siblings = siblingGroups.get(node.parent_id) || [];
      siblings.push(node);
      siblingGroups.set(node.parent_id, siblings);
    }

    siblingGroups.forEach((siblings, parentId) => {
      if (siblings.length < 2) return;

      const center = siblings.reduce(
        (accumulator, node) => {
          return {
            x: accumulator.x + (node.x || 0),
            y: accumulator.y + (node.y || 0),
          };
        },
        { x: 0, y: 0 },
      );

      const centroidX = center.x / siblings.length;
      const centroidY = center.y / siblings.length;
      const baseAngle = parentAngles[parentId] ?? parentAngles[siblings[0].topLevelId] ?? 0;
      const ordered = [...siblings].sort((left, right) => left.label.localeCompare(right.label));

      ordered.forEach((node, index) => {
        const angle = baseAngle + (index / siblings.length) * Math.PI * 2;
        const orbitRadius = 24 + siblings.length * 5 + Math.max(node.depth - 1, 0) * 12;
        const targetX = centroidX + Math.cos(angle) * orbitRadius;
        const targetY = centroidY + Math.sin(angle) * orbitRadius;

        node.vx = (node.vx || 0) + (targetX - (node.x || 0)) * 0.08 * alpha;
        node.vy = (node.vy || 0) + (targetY - (node.y || 0)) * 0.08 * alpha;
      });
    });
  }) as CustomForce;

  force.initialize = (newNodes: ForceNode[]) => {
    nodes = newNodes;
  };

  return force;
}

function createBranchOrbitForce(
  branchAnchors: Record<string, { x: number; y: number; angle: number }>,
  rootId: string,
): CustomForce {
  let nodes: ForceNode[] = [];

  const force = ((alpha: number) => {
    for (const node of nodes) {
      if (node.id === rootId) continue;

      const anchor = branchAnchors[node.topLevelId] || { x: 0, y: 0, angle: node.seedAngle };
      const orbitRadius = node.depth <= 1 ? 0 : 38 + (node.depth - 1) * 42 + Math.min(node.child_count, 5) * 8;
      const targetAngle = anchor.angle + node.seedAngle * 0.35 + node.depth * 0.18;
      const targetX = node.depth === 1 ? anchor.x : anchor.x + Math.cos(targetAngle) * orbitRadius;
      const targetY = node.depth === 1 ? anchor.y : anchor.y + Math.sin(targetAngle) * orbitRadius;
      const strength = node.depth === 1 ? 0.18 : 0.1;

      node.vx = (node.vx || 0) + (targetX - (node.x || 0)) * strength * alpha;
      node.vy = (node.vy || 0) + (targetY - (node.y || 0)) * strength * alpha;
    }
  }) as CustomForce;

  force.initialize = (newNodes: ForceNode[]) => {
    nodes = newNodes;
  };

  return force;
}

function buildClusterHalos(layoutNodes: LayoutNode[], rootId: string, themeByTopLevel: Record<string, { node: string; stroke: string; halo: string }>): ClusterHalo[] {
  const grouped = new Map<string, LayoutNode[]>();

  for (const node of layoutNodes) {
    if (node.id === rootId || node.topLevelId === rootId) continue;
    const group = grouped.get(node.topLevelId) || [];
    group.push(node);
    grouped.set(node.topLevelId, group);
  }

  return Array.from(grouped.entries()).map(([clusterId, nodes]) => {
    const center = nodes.reduce(
      (accumulator, node) => ({
        x: accumulator.x + node.x,
        y: accumulator.y + node.y,
      }),
      { x: 0, y: 0 },
    );
    const x = center.x / nodes.length;
    const y = center.y / nodes.length;
    const radius = nodes.reduce((maxRadius, node) => {
      const dx = node.x - x;
      const dy = node.y - y;
      const distance = Math.hypot(dx, dy) + node.radius + 48;
      return Math.max(maxRadius, distance);
    }, 90);

    const theme = themeByTopLevel[clusterId] || BRANCH_THEMES[0];
    const anchorNode = nodes.find((node) => node.id === clusterId) || nodes[0];

    return {
      id: clusterId,
      label: anchorNode.label,
      x,
      y,
      radius,
      fill: theme.halo,
      stroke: `${theme.stroke}55`,
    };
  });
}

function buildEdgePath(fromNode: LayoutNode, toNode: LayoutNode): string {
  const dx = toNode.x - fromNode.x;
  const dy = toNode.y - fromNode.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  const unitX = dx / length;
  const unitY = dy / length;
  const startX = fromNode.x + unitX * fromNode.radius;
  const startY = fromNode.y + unitY * fromNode.radius;
  const endX = toNode.x - unitX * toNode.radius;
  const endY = toNode.y - unitY * toNode.radius;
  const midX = (startX + endX) / 2;
  const midY = (startY + endY) / 2;
  const curve = clamp(length * 0.08, 10, 38);
  const normalX = -unitY;
  const normalY = unitX;
  const controlX = midX + normalX * curve;
  const controlY = midY + normalY * curve;

  return `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`;
}

function computeLayout(nodes: GraphNode[], edges: GraphEdge[], containerWidth: number, containerHeight: number): LayoutResult {
  if (nodes.length === 0) {
    return {
      layoutNodes: [],
      layoutEdges: [],
      halos: [],
      svgWidth: 800,
      svgHeight: 600,
      offsetX: 0,
      offsetY: 0,
    };
  }

  const rootId = nodes.find((node) => node.parent_id === null)?.id || nodes[0].id;
  const nodeMap = new Map<string, GraphNode>(nodes.map((node) => [node.id, node]));
  const topLevelIds = nodes
    .filter((node) => node.parent_id === rootId)
    .map((node) => node.id);
  const themeByTopLevel: Record<string, { node: string; stroke: string; halo: string }> = {};
  topLevelIds.forEach((nodeId, index) => {
    themeByTopLevel[nodeId] = BRANCH_THEMES[index % BRANCH_THEMES.length];
  });

  const simulationWidth = Math.max(containerWidth, 920);
  const simulationHeight = Math.max(containerHeight, 720);
  const orbitRadius = Math.min(simulationWidth, simulationHeight) * 0.28;
  const branchAnchors: Record<string, { x: number; y: number; angle: number }> = {};
  const parentAngles: Record<string, number> = {};

  topLevelIds.forEach((nodeId, index) => {
    const angle = (-Math.PI / 2) + (index / Math.max(topLevelIds.length, 1)) * Math.PI * 2;
    branchAnchors[nodeId] = {
      x: Math.cos(angle) * orbitRadius,
      y: Math.sin(angle) * orbitRadius,
      angle,
    };
    parentAngles[nodeId] = angle;
  });

  const simNodes: ForceNode[] = nodes.map((node) => {
    const isRoot = node.id === rootId;
    const topLevelId = getTopLevelId(node, nodeMap, rootId);
    const theme = themeByTopLevel[topLevelId] || BRANCH_THEMES[0];
    const radius = getNodeRadius(node, isRoot);
    const seedAngle = hashAngle(node.id);
    const anchor = branchAnchors[topLevelId] || { x: 0, y: 0, angle: seedAngle };
    const orbit = node.depth <= 1 ? 0 : 24 + node.depth * 36;

    return {
      ...node,
      x: isRoot ? 0 : anchor.x + Math.cos(seedAngle) * orbit,
      y: isRoot ? 0 : anchor.y + Math.sin(seedAngle) * orbit,
      fx: isRoot ? 0 : null,
      fy: isRoot ? 0 : null,
      radius,
      topLevelId,
      seedAngle,
      fill: isRoot ? GRAPH_BACKGROUND.rootFill : theme.node,
      stroke: isRoot ? GRAPH_BACKGROUND.rootStroke : theme.stroke,
    };
  });

  const simLinks: ForceLink[] = edges.map((edge) => ({
    source: edge.from,
    target: edge.to,
  }));

  const radialDistance = (node: ForceNode): number => {
    if (node.id === rootId) return 0;
    if (node.depth === 1) return orbitRadius;
    return orbitRadius + node.depth * 88;
  };

  const simulation = forceSimulation(simNodes)
    .force('center', forceCenter(0, 0))
    .force(
      'link',
      forceLink(simLinks)
        .id((node: ForceNode) => node.id)
        .distance((link: ForceLink) => {
          const source = typeof link.source === 'string' ? nodeMap.get(link.source) : link.source;
          const target = typeof link.target === 'string' ? nodeMap.get(link.target) : link.target;
          const targetDepth = target?.depth ?? 0;
          const sourceChildren = source?.child_count ?? 0;
          return 80 + targetDepth * 14 + Math.min(sourceChildren, 5) * 6;
        })
        .strength((link: ForceLink) => {
          const source = typeof link.source === 'string' ? nodeMap.get(link.source) : link.source;
          return source?.depth === 0 ? 0.42 : 0.32;
        }),
    )
    .force(
      'charge',
      forceManyBody().strength((node: ForceNode) => {
        if (node.id === rootId) return -1200;
        if (node.depth === 1) return -460;
        return -210;
      }),
    )
    .force(
      'collide',
      forceCollide().radius((node: ForceNode) => node.radius + (node.depth <= 1 ? 26 : 16)).strength(0.92),
    )
    .force(
      'radial',
      forceRadial(radialDistance, 0, 0).strength((node: ForceNode) => {
        if (node.id === rootId) return 1;
        if (node.depth === 1) return 0.24;
        return 0.08;
      }),
    )
    .force('branchOrbit', createBranchOrbitForce(branchAnchors, rootId))
    .force('siblingCluster', createSiblingClusterForce(parentAngles))
    .alpha(1)
    .alphaDecay(0.03)
    .velocityDecay(0.35);

  simulation.stop();
  for (let iteration = 0; iteration < 280; iteration += 1) {
    simulation.tick();
  }

  const layoutNodes: LayoutNode[] = simNodes.map((node) => {
    const hasContent = node.action_count > 0 || node.data_count > 0;
    return {
      ...node,
      x: node.x || 0,
      y: node.y || 0,
      hasContent,
    };
  });

  const layoutNodeMap = new Map<string, LayoutNode>(layoutNodes.map((node) => [node.id, node]));
  const halos = buildClusterHalos(layoutNodes, rootId, themeByTopLevel);
  const layoutEdges: LayoutEdge[] = edges
    .map((edge) => {
      const fromNode = layoutNodeMap.get(edge.from);
      const toNode = layoutNodeMap.get(edge.to);
      if (!fromNode || !toNode) return null;
      return {
        id: `${edge.from}-${edge.to}`,
        path: buildEdgePath(fromNode, toNode),
      };
    })
    .filter((edge): edge is LayoutEdge => edge !== null);

  const padding = 120;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const halo of halos) {
    minX = Math.min(minX, halo.x - halo.radius);
    minY = Math.min(minY, halo.y - halo.radius);
    maxX = Math.max(maxX, halo.x + halo.radius);
    maxY = Math.max(maxY, halo.y + halo.radius);
  }

  for (const node of layoutNodes) {
    minX = Math.min(minX, node.x - node.radius - 60);
    minY = Math.min(minY, node.y - node.radius - 40);
    maxX = Math.max(maxX, node.x + node.radius + 60);
    maxY = Math.max(maxY, node.y + node.radius + 60);
  }

  if (!isFinite(minX)) {
    minX = -400;
    minY = -300;
    maxX = 400;
    maxY = 300;
  }

  return {
    layoutNodes,
    layoutEdges,
    halos,
    svgWidth: maxX - minX + padding * 2,
    svgHeight: maxY - minY + padding * 2,
    offsetX: -minX + padding,
    offsetY: -minY + padding,
  };
}

const SelectionPanel: React.FC<{
  node: LayoutNode;
  onClose: () => void;
}> = ({ node, onClose }) => {
  const readableLabel = getReadableNodeLabel(node.label);
  const path = node.path_labels.map(getReadableNodeLabel).join(' / ');
  return (
    <div
      onClick={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
      style={{
        position: 'absolute',
        right: 18,
        top: 18,
        width: 320,
        maxWidth: 'calc(100% - 36px)',
        background: 'rgba(255, 251, 245, 0.96)',
        border: '1px solid rgba(120, 101, 80, 0.12)',
        borderRadius: 18,
        padding: 16,
        zIndex: 10,
        boxShadow: '0 18px 42px rgba(65, 51, 38, 0.14)',
        backdropFilter: 'blur(12px)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 6 }}>
        <div style={{ fontWeight: 700, fontSize: '0.98rem', color: GRAPH_BACKGROUND.ink, minWidth: 0 }}>
          {truncateLabel(readableLabel, 56)}
        </div>
        <button
          onClick={(event) => {
            event.stopPropagation();
            onClose();
          }}
          style={{
            border: 'none',
            background: 'transparent',
            color: '#8C8377',
            cursor: 'pointer',
            fontSize: '1rem',
            padding: 0,
            lineHeight: 1,
            flexShrink: 0,
          }}
        >
          ×
        </button>
      </div>
      <div style={{ fontSize: '0.76rem', color: '#746C63', lineHeight: 1.5, marginBottom: 12 }}>
        {path}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <span style={tooltipStatPill}>{node.child_count} child{node.child_count === 1 ? '' : 'ren'}</span>
        <span style={tooltipStatPill}>{node.action_count} action{node.action_count === 1 ? '' : 's'}</span>
        <span style={tooltipStatPill}>{node.data_count} data item{node.data_count === 1 ? '' : 's'}</span>
      </div>

      {node.action_previews.length > 0 && (
        <div style={{ marginBottom: node.data_previews.length > 0 ? 12 : 0 }}>
          <div style={tooltipSectionTitle}>Action previews</div>
          {node.action_previews.map((preview) => (
            <div key={preview} style={tooltipPreviewRow}>
              {truncateLabel(getReadableNodeLabel(preview), 54)}
            </div>
          ))}
        </div>
      )}

      {node.data_previews.length > 0 && (
        <div>
          <div style={tooltipSectionTitle}>Data previews</div>
          {node.data_previews.map((preview, index) => (
            <div key={`${preview.label}-${index}`} style={tooltipPreviewRow}>
              {preview.category ? `[${preview.category}] ` : ''}
              {truncateLabel(getReadableNodeLabel(preview.label), 52)}
            </div>
          ))}
        </div>
      )}

      {node.action_previews.length === 0 && node.data_previews.length === 0 && (
        <div style={{ fontSize: '0.8rem', color: '#8E877F', fontStyle: 'italic' }}>
          This node is mostly structural right now.
        </div>
      )}
    </div>
  );
};

const tooltipStatPill: React.CSSProperties = {
  padding: '5px 10px',
  borderRadius: 999,
  background: 'rgba(212, 197, 177, 0.36)',
  color: '#5A5046',
  fontSize: '0.72rem',
  fontWeight: 600,
};

const tooltipSectionTitle: React.CSSProperties = {
  fontSize: '0.68rem',
  color: '#8B6A4B',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  marginBottom: 6,
};

const tooltipPreviewRow: React.CSSProperties = {
  fontSize: '0.8rem',
  color: '#4F4640',
  lineHeight: 1.5,
  marginBottom: 4,
};

const GraphVisualization: React.FC<{
  nodes: GraphNode[];
  edges: GraphEdge[];
}> = ({ nodes, edges }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });
  const panStartRef = useRef({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutResult>({
    layoutNodes: [],
    layoutEdges: [],
    halos: [],
    svgWidth: 800,
    svgHeight: 600,
    offsetX: 0,
    offsetY: 0,
  });
  const rootId = nodes.find((entry) => entry.parent_id === null)?.id || null;
  const selectedNode = selectedNodeId ? layout.layoutNodes.find((node) => node.id === selectedNodeId) || null : null;

  const applyTransform = useCallback(() => {
    if (!svgRef.current) return;
    const { x, y, scale } = transformRef.current;
    svgRef.current.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
  }, []);

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const element = containerRef.current;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const rect = entry.contentRect;
      setContainerSize({ width: rect.width, height: rect.height });
    });

    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const nextLayout = computeLayout(nodes, edges, containerSize.width, containerSize.height);
    setLayout(nextLayout);
  }, [nodes, edges, containerSize.width, containerSize.height]);

  useEffect(() => {
    if (!containerRef.current || layout.layoutNodes.length === 0) return;
    const rect = containerRef.current.getBoundingClientRect();
    const scaleX = rect.width / layout.svgWidth;
    const scaleY = rect.height / layout.svgHeight;
    const fitScale = Math.min(scaleX, scaleY, 1) * 0.92;
    transformRef.current = {
      x: (rect.width - layout.svgWidth * fitScale) / 2,
      y: (rect.height - layout.svgHeight * fitScale) / 2,
      scale: fitScale,
    };
    applyTransform();
  }, [applyTransform, layout]);

  const handleWheel = useCallback((event: React.WheelEvent) => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;

    const previous = transformRef.current;
    const newScale = clamp(previous.scale * delta, 0.22, 4);
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;

    transformRef.current = {
      x: mouseX - (mouseX - previous.x) * (newScale / previous.scale),
      y: mouseY - (mouseY - previous.y) * (newScale / previous.scale),
      scale: newScale,
    };
    applyTransform();
  }, [applyTransform]);

  const handleMouseDown = useCallback((event: React.MouseEvent) => {
    if (event.button !== 0) return;
    setIsPanning(true);
    const { x, y } = transformRef.current;
    panStartRef.current = { x: event.clientX - x, y: event.clientY - y };
  }, []);

  const handleMouseMove = useCallback((event: React.MouseEvent) => {
    if (isPanning) {
      transformRef.current = {
        ...transformRef.current,
        x: event.clientX - panStartRef.current.x,
        y: event.clientY - panStartRef.current.y,
      };
      applyTransform();
    }
  }, [applyTransform, isPanning]);

  const handleMouseUp = useCallback(() => setIsPanning(false), []);

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
      onMouseLeave={() => {
        setIsPanning(false);
      }}
      onClick={() => setSelectedNodeId(null)}
    >
      <svg
        ref={svgRef}
        width={layout.svgWidth}
        height={layout.svgHeight}
        style={{
          transformOrigin: '0 0',
          willChange: 'transform',
        }}
      >
        <defs>
          <radialGradient id="memoryGraphGlow" cx="50%" cy="45%" r="85%">
            <stop offset="0%" stopColor="#FFF9F1" />
            <stop offset="65%" stopColor="#F3EBDD" />
            <stop offset="100%" stopColor="#E8DECD" />
          </radialGradient>
          <pattern id="memoryGraphGrid" width="48" height="48" patternUnits="userSpaceOnUse">
            <path d="M 48 0 L 0 0 0 48" fill="none" stroke={GRAPH_BACKGROUND.grid} strokeWidth="1" />
          </pattern>
          <filter id="nodeGlow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="8" result="softGlow" />
            <feMerge>
              <feMergeNode in="softGlow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <rect x={0} y={0} width={layout.svgWidth} height={layout.svgHeight} fill="url(#memoryGraphGlow)" />
        <rect x={0} y={0} width={layout.svgWidth} height={layout.svgHeight} fill="url(#memoryGraphGrid)" opacity={0.45} />

        <g transform={`translate(${layout.offsetX}, ${layout.offsetY})`}>
          {layout.halos.map((halo) => (
            <g key={halo.id}>
              <circle cx={halo.x} cy={halo.y} r={halo.radius} fill={halo.fill} stroke={halo.stroke} strokeWidth={1} opacity={0.82} />
            </g>
          ))}

          {layout.layoutEdges.map((edge) => (
            <path
              key={edge.id}
              d={edge.path}
              fill="none"
              stroke={GRAPH_BACKGROUND.link}
              strokeWidth={1.5}
              opacity={0.9}
            />
          ))}

          {layout.layoutNodes.map((node) => {
            const isSelected = selectedNodeId === node.id;
            const label = truncateLabel(getReadableNodeLabel(node.label), node.depth <= 1 ? 20 : 16);
            const displayLabel = node.id === rootId || node.depth === 1 || isSelected;
            const contentCount = node.action_count + node.data_count;

            return (
              <g
                key={node.id}
                onClick={(event) => {
                  event.stopPropagation();
                  setSelectedNodeId(node.id);
                }}
                style={{ cursor: 'pointer' }}
              >
                {node.id === rootId && (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.radius + 18}
                    fill="rgba(199, 119, 83, 0.12)"
                    stroke="rgba(141, 77, 52, 0.18)"
                    strokeWidth={1.5}
                  />
                )}

                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isSelected ? node.radius + 2 : node.radius}
                  fill={node.fill}
                  stroke={node.stroke}
                  strokeWidth={isSelected ? 3.5 : 1.8}
                  opacity={0.96}
                  filter={isSelected ? 'url(#nodeGlow)' : undefined}
                  style={{ transition: 'r 0.16s ease, stroke-width 0.16s ease, opacity 0.16s ease' }}
                />

                {node.hasContent && (
                  <circle
                    cx={node.x + node.radius * 0.7}
                    cy={node.y - node.radius * 0.7}
                    r={Math.min(10, Math.max(7, node.radius * 0.45))}
                    fill="#FFF9F1"
                    stroke={node.stroke}
                    strokeWidth={1.6}
                  />
                )}

                {node.hasContent && (
                  <text
                    x={node.x + node.radius * 0.7}
                    y={node.y - node.radius * 0.7 + 3.5}
                    textAnchor="middle"
                    fill={node.stroke}
                    fontSize={10}
                    fontWeight={700}
                  >
                    {contentCount > 9 ? '9+' : contentCount}
                  </text>
                )}

                {displayLabel && (
                  <text
                    x={node.x}
                    y={node.y + node.radius + 18}
                    textAnchor="middle"
                    fill={node.depth <= 1 ? GRAPH_BACKGROUND.ink : '#62594F'}
                    fontSize={node.depth <= 1 ? 12 : 10}
                    fontFamily="DM Sans, system-ui, sans-serif"
                    fontWeight={node.depth <= 1 ? 700 : 500}
                    opacity={isSelected ? 1 : node.depth <= 1 ? 0.94 : 0.78}
                  >
                    {label}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {selectedNode && (
        <SelectionPanel node={selectedNode} onClose={() => setSelectedNodeId(null)} />
      )}
    </div>
  );
};

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
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load graph data');
    } finally {
      setLoading(false);
    }
  };

  const confirmClearGraph = async () => {
    setShowConfirmDialog(false);
    setResetting(true);
    setError(null);
    try {
      const response = await fetch(`${BACKEND_URL}/graph/reset`, { method: 'POST' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const message = typeof body.error === 'string' ? body.error : `HTTP ${response.status}`;
        throw new Error(message);
      }
      setGraphData(null);
      await loadGraphData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reset graph');
    } finally {
      setResetting(false);
    }
  };

  useEffect(() => {
    loadGraphData();
  }, []);

  const hasData = Boolean(graphData && graphData.nodes.length > 0);

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Memory Graph</h1>
          <p style={styles.subtitle}>Explore clustered memory regions instead of a cramped tree.</p>
        </div>
      </div>

      {error && (
        <div style={styles.errorBanner}>
          <span>{error}</span>
          <button style={styles.errorDismiss} onClick={() => setError(null)}>×</button>
        </div>
      )}

      {hasData && graphData && (
        <div style={styles.statsBar}>
          <div style={styles.statItem}>
            <span style={styles.statValue}>{graphData.stats.total_nodes}</span>
            <span style={styles.statLabel}>Items</span>
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

      {loading ? (
        <div style={styles.graphContainer}>
          <div style={styles.loadingState}>
            <div style={styles.spinner} />
            <p style={styles.loadingText}>Building memory map...</p>
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

      <div style={styles.footer}>
        <div style={styles.actionButtons}>
          <button style={styles.refreshButton} onClick={loadGraphData} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          <button
            style={styles.clearButton}
            onClick={() => setShowConfirmDialog(true)}
            disabled={resetting || loading}
          >
            {resetting ? 'Resetting...' : 'Clear Graph'}
          </button>
        </div>
      </div>

      {showConfirmDialog && (
        <div style={styles.dialogOverlay}>
          <div style={styles.dialogBox}>
            <h3 style={styles.dialogTitle}>Clear Memory Graph?</h3>
            <p style={styles.dialogText}>
              This will permanently delete all nodes, actions, and data from your knowledge graph. This action cannot be undone.
            </p>
            <div style={styles.dialogButtons}>
              <button style={styles.dialogCancelBtn} onClick={() => setShowConfirmDialog(false)}>
                Cancel
              </button>
              <button style={styles.dialogConfirmBtn} onClick={confirmClearGraph}>
                Yes, Clear Everything
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '32px 40px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    marginBottom: '18px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: '1.6rem',
    fontWeight: 700,
    color: '#1A1A1A',
    margin: '0 0 5px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '0.875rem',
    color: '#5A5A5A',
    margin: 0,
  },
  errorBanner: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.06)',
    border: '1px solid rgba(239, 68, 68, 0.22)',
    borderRadius: 10,
    padding: '10px 16px',
    marginBottom: 14,
    color: '#991b1b',
    fontSize: '0.85rem',
  },
  errorDismiss: {
    background: 'none',
    border: 'none',
    color: '#991b1b',
    fontSize: '1.1rem',
    cursor: 'pointer',
    padding: '0 4px',
  },
  statsBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 20,
    marginBottom: 14,
    padding: '12px 20px',
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    border: '1px solid #E8E4DC',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
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
    color: '#1A1A1A',
    fontVariantNumeric: 'tabular-nums',
  },
  statLabel: {
    fontSize: '0.68rem',
    color: '#9A9A96',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    fontWeight: 600,
  },
  statDivider: {
    width: 1,
    height: 28,
    backgroundColor: '#E8E4DC',
  },
  graphContainer: {
    flex: 1,
    minHeight: 440,
    background: 'linear-gradient(180deg, #F8F3EA 0%, #F0E7DA 100%)',
    borderRadius: 18,
    border: '1px solid rgba(184, 160, 130, 0.12)',
    overflow: 'hidden',
    position: 'relative',
    boxShadow: '0 12px 36px rgba(77, 58, 32, 0.05), inset 0 1px 0 rgba(255,255,255,0.48)',
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
    width: 26,
    height: 26,
    border: '3px solid #E8E4DC',
    borderTopColor: '#1A1A1A',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  loadingText: {
    color: '#8B8378',
    fontSize: '0.875rem',
    margin: 0,
  },
  emptyState: {
    flex: 1,
    minHeight: 400,
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    border: '1px solid #E8E4DC',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 48,
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  emptyIcon: {
    fontSize: '2rem',
    color: '#D4CFC6',
    marginBottom: 14,
  },
  emptyTitle: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#1A1A1A',
    marginBottom: 8,
    marginTop: 0,
    letterSpacing: '-0.01em',
  },
  emptyText: {
    fontSize: '0.85rem',
    color: '#9A9A96',
    lineHeight: 1.6,
    textAlign: 'center',
    maxWidth: 380,
    margin: 0,
  },
  footer: {
    display: 'flex',
    justifyContent: 'flex-end',
    alignItems: 'center',
    marginTop: 14,
    gap: 10,
  },
  actionButtons: {
    display: 'flex',
    gap: 8,
  },
  refreshButton: {
    padding: '9px 20px',
    backgroundColor: '#1A1A1A',
    border: 'none',
    borderRadius: 100,
    color: '#FFFFFF',
    fontSize: '0.825rem',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  clearButton: {
    padding: '9px 20px',
    backgroundColor: 'transparent',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    borderRadius: 100,
    color: '#991b1b',
    fontSize: '0.825rem',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    fontFamily: 'inherit',
  },
  dialogOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.25)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    backdropFilter: 'blur(4px)',
  },
  dialogBox: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: '28px 32px',
    maxWidth: 400,
    width: '90%',
    border: '1px solid #E8E4DC',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.12)',
  },
  dialogTitle: {
    fontSize: '1.05rem',
    fontWeight: 700,
    color: '#1A1A1A',
    marginBottom: 10,
    marginTop: 0,
    letterSpacing: '-0.01em',
  },
  dialogText: {
    fontSize: '0.875rem',
    color: '#5A5A5A',
    lineHeight: 1.6,
    marginBottom: 22,
    marginTop: 0,
  },
  dialogButtons: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 8,
  },
  dialogCancelBtn: {
    padding: '9px 18px',
    backgroundColor: 'transparent',
    border: '1px solid #E8E4DC',
    borderRadius: 100,
    color: '#5A5A5A',
    fontSize: '0.825rem',
    fontWeight: 500,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  dialogConfirmBtn: {
    padding: '9px 18px',
    backgroundColor: '#ef4444',
    border: 'none',
    borderRadius: 100,
    color: '#FFFFFF',
    fontSize: '0.825rem',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
};

export default MemoryPage;
