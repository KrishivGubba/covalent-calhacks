#!/usr/bin/env python3
"""
Graph Visualization Tool for the Context Engine Knowledge Graph

This script provides multiple ways to visualize the graph:
1. Terminal-based ASCII tree view
2. HTML interactive visualization using pyvis
3. Static image using matplotlib + networkx
"""

import os
import sys
import json
from collections import defaultdict

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use SQLCipher for encrypted database
try:
    from sqlcipher3 import dbapi2 as sqlite3
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlite3
    except ImportError:
        import sqlite3  # fallback to stdlib (will fail on encrypted DB)

def get_graph_data(db_path):
    """Load graph data from SQLite database (supports encrypted DB)."""
    conn = sqlite3.connect(db_path)
    try:
        from security.key_manager import get_db_encryption_key
        conn.execute(f"PRAGMA key = '{get_db_encryption_key()}'")
    except ImportError:
        pass  # no key_manager: assume unencrypted
    cursor = conn.cursor()
    
    # Get all nodes
    cursor.execute("""
        SELECT UUID, Metadata, parent_uuid, children_uuid_arr
        FROM node_table
    """)
    nodes = cursor.fetchall()
    
    # Get all actions
    cursor.execute("""
        SELECT UUID, Action_name, Node_UUID
        FROM action_table
    """)
    actions = cursor.fetchall()
    
    # Get all data entries
    cursor.execute("""
        SELECT UUID, Node_UUID, key, type, category
        FROM data_table
    """)
    data_entries = cursor.fetchall()
    
    conn.close()
    
    return nodes, actions, data_entries


def print_ascii_tree(db_path):
    """Print an ASCII representation of the tree structure."""
    nodes, actions, data_entries = get_graph_data(db_path)
    
    # Build lookup dictionaries
    node_dict = {}
    children_map = defaultdict(list)
    root_uuid = None
    
    for uuid, metadata, parent_uuid, children_arr in nodes:
        node_dict[uuid] = metadata
        if parent_uuid is None:
            root_uuid = uuid
        else:
            children_map[parent_uuid].append(uuid)
    
    # Count actions per node
    actions_per_node = defaultdict(int)
    for _, _, node_uuid in actions:
        actions_per_node[node_uuid] += 1
    
    # Count data per node
    data_per_node = defaultdict(int)
    for _, node_uuid, _, _, _ in data_entries:
        data_per_node[node_uuid] += 1
    
    def print_node(uuid, prefix="", is_last=True):
        connector = "└── " if is_last else "├── "
        metadata = node_dict.get(uuid, "Unknown")
        action_count = actions_per_node[uuid]
        data_count = data_per_node[uuid]
        
        # Build info string
        info_parts = []
        if action_count > 0:
            info_parts.append(f"📋 {action_count} actions")
        if data_count > 0:
            info_parts.append(f"📦 {data_count} data")
        
        info_str = f" ({', '.join(info_parts)})" if info_parts else ""
        
        print(f"{prefix}{connector}{metadata}{info_str}")
        
        children = children_map[uuid]
        for i, child_uuid in enumerate(children):
            is_last_child = (i == len(children) - 1)
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_node(child_uuid, new_prefix, is_last_child)
    
    if root_uuid:
        print("\n🌳 Knowledge Graph Structure")
        print("=" * 50)
        print(f"{node_dict[root_uuid]}")
        children = children_map[root_uuid]
        for i, child_uuid in enumerate(children):
            is_last_child = (i == len(children) - 1)
            print_node(child_uuid, "", is_last_child)
    else:
        print("No root node found!")
    
    print("\n" + "=" * 50)
    print(f"Total nodes: {len(nodes)}")
    print(f"Total actions: {len(actions)}")
    print(f"Total data entries: {len(data_entries)}")


def create_html_visualization(db_path, output_path="graph_visualization.html"):
    """Create an interactive HTML visualization using pyvis."""
    try:
        from pyvis.network import Network
    except ImportError:
        print("pyvis not installed. Install with: pip install pyvis")
        print("Falling back to ASCII visualization...")
        print_ascii_tree(db_path)
        return None
    
    nodes, actions, data_entries = get_graph_data(db_path)
    
    # Create network
    net = Network(
        height="800px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="#eee",
        directed=True,
        notebook=False
    )
    
    # Physics settings for better layout
    net.set_options("""
    {
        "nodes": {
            "font": {
                "size": 14,
                "face": "Inter, system-ui, sans-serif"
            },
            "borderWidth": 2,
            "shadow": true
        },
        "edges": {
            "color": {
                "inherit": false,
                "color": "#4a5568"
            },
            "smooth": {
                "type": "cubicBezier",
                "forceDirection": "vertical"
            },
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": 0.5
                }
            }
        },
        "physics": {
            "enabled": true,
            "hierarchicalRepulsion": {
                "centralGravity": 0.5,
                "springLength": 150,
                "springConstant": 0.01,
                "nodeDistance": 200
            },
            "solver": "hierarchicalRepulsion"
        },
        "layout": {
            "hierarchical": {
                "enabled": true,
                "direction": "UD",
                "sortMethod": "directed",
                "levelSeparation": 150,
                "nodeSpacing": 200
            }
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 100
        }
    }
    """)
    
    # Build lookup dictionaries
    node_dict = {}
    for uuid, metadata, parent_uuid, children_arr in nodes:
        node_dict[uuid] = {
            'metadata': metadata,
            'parent_uuid': parent_uuid
        }
    
    # Count actions per node
    actions_per_node = defaultdict(list)
    for action_uuid, action_name, node_uuid in actions:
        actions_per_node[node_uuid].append(action_name)
    
    # Count data per node
    data_per_node = defaultdict(list)
    for data_uuid, node_uuid, key, dtype, category in data_entries:
        data_per_node[node_uuid].append({
            'key': key,
            'type': dtype,
            'category': category
        })
    
    # Color scheme based on node depth/type
    colors = {
        'root': '#e63946',      # Red for root
        'level1': '#f77f00',    # Orange for first level
        'level2': '#fcbf49',    # Yellow for second level
        'leaf': '#2a9d8f',      # Teal for leaf nodes
        'with_actions': '#9b5de5'  # Purple for nodes with actions
    }
    
    # Calculate depth for each node
    def get_depth(uuid, depth=0):
        if uuid not in node_dict:
            return depth
        parent = node_dict[uuid]['parent_uuid']
        if parent is None:
            return depth
        return get_depth(parent, depth + 1)
    
    # Add nodes
    for uuid, info in node_dict.items():
        metadata = info['metadata']
        parent_uuid = info['parent_uuid']
        depth = get_depth(uuid)
        
        # Determine color
        if parent_uuid is None:
            color = colors['root']
            size = 40
        elif actions_per_node[uuid]:
            color = colors['with_actions']
            size = 30
        elif depth == 1:
            color = colors['level1']
            size = 35
        elif depth == 2:
            color = colors['level2']
            size = 28
        else:
            color = colors['leaf']
            size = 25
        
        # Build tooltip
        tooltip_parts = [f"<b>{metadata}</b>"]
        tooltip_parts.append(f"<br><i>UUID: {uuid[:8]}...</i>")
        
        if actions_per_node[uuid]:
            tooltip_parts.append(f"<br><br><b>Actions ({len(actions_per_node[uuid])}):</b>")
            for action in actions_per_node[uuid][:5]:  # Limit to 5
                tooltip_parts.append(f"<br>• {action[:40]}...")
            if len(actions_per_node[uuid]) > 5:
                tooltip_parts.append(f"<br>... and {len(actions_per_node[uuid]) - 5} more")
        
        if data_per_node[uuid]:
            tooltip_parts.append(f"<br><br><b>Data ({len(data_per_node[uuid])}):</b>")
            for data in data_per_node[uuid][:3]:  # Limit to 3
                cat = data['category'] or 'uncategorized'
                tooltip_parts.append(f"<br>• [{cat}] {data['key'][:30]}...")
            if len(data_per_node[uuid]) > 3:
                tooltip_parts.append(f"<br>... and {len(data_per_node[uuid]) - 3} more")
        
        tooltip = "".join(tooltip_parts)
        
        net.add_node(
            uuid,
            label=metadata,
            title=tooltip,
            color=color,
            size=size,
            shape="dot"
        )
    
    # Add edges
    for uuid, info in node_dict.items():
        parent_uuid = info['parent_uuid']
        if parent_uuid and parent_uuid in node_dict:
            net.add_edge(parent_uuid, uuid)
    
    # Save to file
    output_file = os.path.join(os.path.dirname(db_path), output_path)
    net.save_graph(output_file)
    print(f"\n✨ Interactive visualization saved to: {output_file}")
    print("Open this file in a web browser to explore the graph!")
    
    return output_file


def create_matplotlib_visualization(db_path, output_path="graph_static.png"):
    """Create a static image visualization using matplotlib and networkx."""
    try:
        import networkx as nx
        import matplotlib.pyplot as plt
    except ImportError:
        print("networkx or matplotlib not installed.")
        print("Install with: pip install networkx matplotlib")
        return None
    
    nodes, actions, data_entries = get_graph_data(db_path)
    
    # Create directed graph
    G = nx.DiGraph()
    
    # Build lookup
    node_dict = {}
    for uuid, metadata, parent_uuid, children_arr in nodes:
        node_dict[uuid] = {
            'metadata': metadata,
            'parent_uuid': parent_uuid
        }
        G.add_node(uuid, label=metadata)
    
    # Add edges
    for uuid, info in node_dict.items():
        parent_uuid = info['parent_uuid']
        if parent_uuid and parent_uuid in node_dict:
            G.add_edge(parent_uuid, uuid)
    
    # Create figure
    plt.figure(figsize=(20, 12))
    plt.style.use('dark_background')
    
    # Use hierarchical layout
    try:
        # Try graphviz layout for better hierarchy
        pos = nx.nx_agraph.graphviz_layout(G, prog='dot')
    except:
        # Fallback to spring layout
        pos = nx.spring_layout(G, k=3, iterations=50)
    
    # Draw the graph
    labels = {uuid: info['metadata'] for uuid, info in node_dict.items()}
    
    # Node colors based on depth
    def get_depth(uuid, depth=0):
        if uuid not in node_dict:
            return depth
        parent = node_dict[uuid]['parent_uuid']
        if parent is None:
            return depth
        return get_depth(parent, depth + 1)
    
    node_colors = []
    color_map = ['#e63946', '#f77f00', '#fcbf49', '#2a9d8f', '#457b9d', '#1d3557']
    for uuid in G.nodes():
        depth = get_depth(uuid)
        node_colors.append(color_map[min(depth, len(color_map) - 1)])
    
    # Draw
    nx.draw(
        G, pos,
        labels=labels,
        with_labels=True,
        node_color=node_colors,
        node_size=2000,
        font_size=8,
        font_color='white',
        font_weight='bold',
        edge_color='#4a5568',
        arrows=True,
        arrowsize=15,
        alpha=0.9
    )
    
    plt.title("Knowledge Graph Structure", fontsize=16, color='white', pad=20)
    
    # Save
    output_file = os.path.join(os.path.dirname(db_path), output_path)
    plt.savefig(output_file, dpi=150, bbox_inches='tight', facecolor='#1a1a2e')
    plt.close()
    
    print(f"\n📊 Static visualization saved to: {output_file}")
    return output_file


def main():
    """Main entry point for graph visualization."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Visualize the Context Engine Knowledge Graph")
    parser.add_argument(
        '--db', '-d',
        default='graph.db',
        help='Path to the SQLite database file (default: graph.db)'
    )
    parser.add_argument(
        '--mode', '-m',
        choices=['ascii', 'html', 'png', 'all'],
        default='all',
        help='Visualization mode (default: all)'
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output filename (for html/png modes)'
    )
    
    args = parser.parse_args()
    
    # Resolve database path
    if os.path.isabs(args.db):
        db_path = args.db
    else:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.db)
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)
    
    print(f"📂 Loading graph from: {db_path}")
    
    if args.mode in ['ascii', 'all']:
        print_ascii_tree(db_path)
    
    if args.mode in ['html', 'all']:
        output = args.output or "graph_visualization.html"
        create_html_visualization(db_path, output)
    
    if args.mode in ['png', 'all']:
        output = args.output or "graph_static.png"
        create_matplotlib_visualization(db_path, output)


if __name__ == "__main__":
    main()

