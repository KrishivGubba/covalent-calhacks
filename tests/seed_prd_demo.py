#!/usr/bin/env python3
"""
Demo script: Seed PRD-based project management nodes for demo purposes.

Creates a hierarchical structure using the Tree class methods from graph.py,
simulating how the graph would be constructed step by step at runtime.

Graph structure:
  Root
  ├── Projects
  │   ├── StreamFlow AI Assistant  (main PRD project)
  │   └── Mobile App Redesign
  ├── Communications
  │   ├── Stakeholder Updates
  │   ├── Team Syncs
  │   └── Emails
  ├── Customer Research
  │   └── User Interviews
  └── Personal
      └── Career Development

Usage:
    python tests/seed_prd_demo.py

    # Clear existing demo nodes first:
    python tests/seed_prd_demo.py --clear

    # Trigger via keystroke simulation (for demo):
    python tests/seed_prd_demo.py --watch
"""

import argparse
import json
import os
import sys
from datetime import datetime

# Preserve original stdout/stderr before importing modules that use the logger
# (the logger module redirects stdout/stderr to log files)
_real_stdout = sys.stdout
_real_stderr = sys.stderr

def cprint(*args, **kwargs):
    """Print to the real console, bypassing logger capture."""
    kwargs['file'] = _real_stdout
    kwargs['flush'] = True
    print(*args, **kwargs)

# Add context-engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'context-engine'))

from graph import Tree, Node

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'context-engine', 'graph.db')

# ============================================================================
# PRD-BASED DEMO DATA
# ============================================================================

STREAMFLOW_AI_DATA = [
    {
        "category": "PRD",
        "key": "Executive Summary",
        "type": "text",
        "info": "StreamFlow AI Assistant is an intelligent virtual assistant integrated into our video streaming platform. Helps users discover content, manage watchlists, get personalized recommendations, and control playback using natural language."
    },
    {
        "category": "PRD",
        "key": "Timeline & Milestones",
        "type": "text",
        "info": "Q3 2026 Release. Phase 1 (Mar-May): NLU + text chat. Phase 2 (Jun): Voice + playback. Phase 3 (Jul-Aug): Contextual info, notifications. Phase 4 (Sep): Beta, launch."
    },
    {
        "category": "PRD",
        "key": "Success Metrics",
        "type": "text",
        "info": "40% WAU by Q4 2026, 3+ interactions/session, reduce discovery time 18min→10min, 60% CTR (from 42%), 4.5/5.0 CSAT, 5% churn improvement."
    },
    {
        "category": "Engineering",
        "key": "Tech Stack Decision",
        "type": "text",
        "info": "Claude 4.5 API for NLU. WebSpeech API (web) + native SDKs (mobile/TV). GraphQL for knowledge graph. React Native mobile, React web."
    },
    {
        "category": "Engineering",
        "key": "P0 Blocker: API Contract",
        "type": "task",
        "info": "Anthropic contract delayed. Original: March 30. New: April 15. Legal review bottleneck. Need interim agreement or expedited review."
    },
    {
        "category": "Risks",
        "key": "Budget Variance",
        "type": "alert",
        "info": "API costs $0.15/user vs $0.12 projected (+25%). Solutions: query caching, Premium tier gating. Potential $180K/year savings."
    },
]

STREAMFLOW_AI_ACTIONS = [
    {
        "action_name": "Schedule design review with Emily",
        "action_plan": json.dumps({"intent": "calendar_event", "title": "AI Assistant Design Review", "attendees": ["emily@streamflow.com"], "duration": 60})
    },
    {
        "action_name": "Send weekly status to VP",
        "action_plan": json.dumps({"intent": "send_email", "to": "vp_product@streamflow.com", "subject": "AI Assistant Weekly Update"})
    },
    {
        "action_name": "Create Jira for API fallback",
        "action_plan": json.dumps({"intent": "create_issue", "project": "STREAM", "title": "Claude 3.5 fallback implementation"})
    },
]

MOBILE_REDESIGN_DATA = [
    {
        "category": "Overview",
        "key": "Project Summary",
        "type": "text",
        "info": "Complete redesign of StreamFlow mobile app. Focus: improved navigation, personalized home screen, faster load times. Target: 4.5 App Store rating (currently 3.8)."
    },
    {
        "category": "Overview",
        "key": "Timeline",
        "type": "text",
        "info": "Q4 2026. Design phase: Aug-Sep. Development: Oct-Nov. Beta: Dec. Launch: Jan 2027."
    },
    {
        "category": "Research",
        "key": "User Feedback Summary",
        "type": "text",
        "info": "Top complaints: (1) Hard to find Continue Watching, (2) Too many taps to play, (3) Slow startup. Opportunity: bottom nav redesign, quick-play shortcuts."
    },
]

MOBILE_REDESIGN_ACTIONS = [
    {
        "action_name": "Review Figma designs from Alex",
        "action_plan": json.dumps({"intent": "open_url", "url": "figma.com/streamflow-mobile-v2"})
    },
    {
        "action_name": "Schedule kickoff with mobile team",
        "action_plan": json.dumps({"intent": "calendar_event", "title": "Mobile Redesign Kickoff", "attendees": ["mobile-team@streamflow.com"]})
    },
]

STAKEHOLDER_UPDATES_DATA = [
    {
        "category": "Executive Updates",
        "key": "Board Deck - Q1 2026",
        "type": "document",
        "info": "Quarterly board presentation. Key slides: AI Assistant progress, mobile metrics, subscriber growth. Presented Feb 15. Feedback: board excited about AI, wants faster timeline."
    },
    {
        "category": "Executive Updates",
        "key": "VP Weekly Sync Notes",
        "type": "meeting_notes",
        "info": "Feb 11: Discussed API cost overrun. VP approved caching investment. Action: present cost optimization plan by Feb 20. VP flagged Disney+ voice search - wants competitive response."
    },
    {
        "category": "Investor Relations",
        "key": "Analyst Questions - AI Strategy",
        "type": "text",
        "info": "Morgan Stanley asking about AI investment ROI timeline. Key message: $55M projected revenue impact by FY2027. Need to prepare talking points for earnings call."
    },
]

STAKEHOLDER_UPDATES_ACTIONS = [
    {
        "action_name": "Draft board update email",
        "action_plan": json.dumps({"intent": "compose_email", "to": "board@streamflow.com", "subject": "AI Assistant Progress Update"})
    },
    {
        "action_name": "Prep earnings call talking points",
        "action_plan": json.dumps({"intent": "create_doc", "title": "Q1 Earnings - AI Talking Points"})
    },
]

TEAM_SYNCS_DATA = [
    {
        "category": "Recurring Meetings",
        "key": "AI Team Standup",
        "type": "meeting",
        "info": "Daily 9:30am. Attendees: 8 engineers, 2 designers, PM. Format: blockers, progress, needs. Current focus: Claude API integration sprint."
    },
    {
        "category": "Recurring Meetings",
        "key": "Cross-functional Sync",
        "type": "meeting",
        "info": "Wednesdays 2pm. Legal, Security, Engineering, Product. Purpose: unblock dependencies. Hot topic: privacy policy for voice data."
    },
    {
        "category": "Action Items",
        "key": "From Feb 12 Standup",
        "type": "tasks",
        "info": "1. Mike: finish API retry logic by EOD. 2. Emily: share updated onboarding mocks. 3. Sarah (me): schedule legal sync re: voice data."
    },
]

TEAM_SYNCS_ACTIONS = [
    {
        "action_name": "Send standup summary to team",
        "action_plan": json.dumps({"intent": "send_slack", "channel": "#streamflow-ai", "message": "Standup notes..."})
    },
    {
        "action_name": "Schedule legal sync",
        "action_plan": json.dumps({"intent": "calendar_event", "title": "Legal Sync - Voice Data Policy", "attendees": ["legal@streamflow.com"]})
    },
]

EMAILS_DATA = [
    {
        "category": "Drafts",
        "key": "Weekly Status to VP",
        "type": "email_draft",
        "info": "To: VP Product. Subject: AI Assistant Week of Feb 10. Phase 1 on track. Wins: Claude POC success, 89% user interest. Risks: legal approval, API costs +25%. Ask: multilingual v1 vs v2?"
    },
    {
        "category": "Drafts",
        "key": "Budget Variance Alert",
        "type": "email_draft",
        "info": "To: CFO, VP Product. API costs $0.03/user over. Solutions: caching, Premium tier gating. $180K/year savings potential."
    },
    {
        "category": "Important",
        "key": "From: Legal Team",
        "type": "email",
        "info": "Re: Voice Data Policy. Review complete, minor edits needed. Can approve by March 18 if we address 3 items: (1) retention period clarity, (2) opt-out UX, (3) EU data residency."
    },
    {
        "category": "Important",
        "key": "From: Anthropic Account Rep",
        "type": "email",
        "info": "Contract update: revised pricing tier available. Enterprise rate: $0.10/user at 500K+ MAU. Action needed: confirm volume commitment by Feb 20 for Q2 activation."
    },
]

EMAILS_ACTIONS = [
    {
        "action_name": "Reply to Legal team",
        "action_plan": json.dumps({"intent": "reply_email", "thread": "Voice Data Policy", "to": "legal@streamflow.com"})
    },
    {
        "action_name": "Send VP weekly update",
        "action_plan": json.dumps({"intent": "send_email", "to": "vp_product@streamflow.com", "subject": "AI Assistant Weekly"})
    },
    {
        "action_name": "Respond to Anthropic on pricing",
        "action_plan": json.dumps({"intent": "reply_email", "to": "enterprise@anthropic.com", "subject": "Re: Contract Pricing"})
    },
]

USER_INTERVIEWS_DATA = [
    {
        "category": "Recent Interviews",
        "key": "Enterprise Client - Feb 10",
        "type": "meeting_notes",
        "info": "Netflix comparison discussion. Pain: 18+ min browsing. Interest: voice control while cooking, accessibility. Action: follow up with accessibility demo."
    },
    {
        "category": "Recent Interviews",
        "key": "Busy Multitasker Persona - Feb 8",
        "type": "meeting_notes",
        "info": "Sarah, 32, working parent. Can't control playback while cooking. Wants to ask 'what should I watch'. Validated voice playback feature."
    },
    {
        "category": "Recent Interviews",
        "key": "Beta Tester Session - Feb 5",
        "type": "meeting_notes",
        "info": "5 testers. Feedback: (1) <2s latency required, (2) mood-based recommendations, (3) privacy concerns - need opt-out. Overall positive reception."
    },
    {
        "category": "Insights",
        "key": "Research Summary",
        "type": "text",
        "info": "47 interviews (Nov-Jan). 89% want voice features. 76% say better recs = more usage. 62% OK sharing voice data if benefits clear."
    },
]

USER_INTERVIEWS_ACTIONS = [
    {
        "action_name": "Schedule follow-up with enterprise client",
        "action_plan": json.dumps({"intent": "calendar_event", "title": "Accessibility Demo Follow-up"})
    },
    {
        "action_name": "Update persona documentation",
        "action_plan": json.dumps({"intent": "edit_doc", "doc": "User Personas - Q1 2026"})
    },
]

CAREER_DATA = [
    {
        "category": "Goals",
        "key": "2026 Career Goals",
        "type": "text",
        "info": "1. Ship AI Assistant successfully (Q3). 2. Get promoted to Senior PM (H2). 3. Build expertise in AI product management. 4. Mentor 1 junior PM."
    },
    {
        "category": "Learning",
        "key": "AI/ML Course Progress",
        "type": "text",
        "info": "Stanford Online - AI Product Management. 60% complete. Next module: 'Evaluating LLM Performance'. Due: Feb 28."
    },
    {
        "category": "1:1 Notes",
        "key": "Manager Sync - Feb 7",
        "type": "meeting_notes",
        "info": "Discussed promotion path. Feedback: need to demonstrate cross-functional leadership. AI Assistant is the opportunity. Action: document wins and learnings for promo packet."
    },
]

CAREER_ACTIONS = [
    {
        "action_name": "Complete AI course module",
        "action_plan": json.dumps({"intent": "open_url", "url": "coursera.org/stanford-ai-pm"})
    },
    {
        "action_name": "Update promo packet doc",
        "action_plan": json.dumps({"intent": "edit_doc", "doc": "Promotion Packet - Sarah Chen"})
    },
]


# ============================================================================
# HELPERS
# ============================================================================

def _add_data(tree: Tree, node: Node, data_list: list):
    """Insert data entries into a node via the DAO."""
    for entry in data_list:
        timestamp_key = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        tree.dao.add_data_with_category(
            node_uuid=node.node_uuid,
            category=entry.get("category", "general"),
            key=f"{entry['key']}_{timestamp_key}",
            data_type=entry.get("type", "text"),
            info=entry["info"],
        )


def _add_actions(tree: Tree, node: Node, actions_list: list):
    """Insert actions into a node via the DAO."""
    current_time = datetime.now().isoformat()
    for action in actions_list:
        tree.dao.add_action(
            node_uuid=node.node_uuid,
            action_name=action["action_name"],
            action_plan=action.get("action_plan"),
            last_selected=current_time,
        )


def _create_child(tree: Tree, parent: Node, metadata: str) -> Node:
    """
    Create a child node via DAO methods, mirroring what _create_child_node() does
    at runtime but without triggering LLM-based embedding generation.
    """
    new_uuid = tree.dao.create_node(metadata, parent.node_uuid)
    tree.dao.add_child_to_node(parent.node_uuid, new_uuid)

    current_time = datetime.now().isoformat()
    new_node = Node(
        node_uuid=new_uuid,
        metadata=metadata,
        created=current_time,
        last_modified=current_time,
        parent_uuid=parent.node_uuid,
        children_uuid_arr=[],
        actions=[],
        data=None,
        embedding=None,
    )

    # Wire up in-memory links (same as _create_child_node does)
    new_node.parent = parent
    parent.children.append(new_node)
    if new_uuid not in parent.children_uuid_arr:
        parent.children_uuid_arr.append(new_uuid)
    tree.nodes[new_uuid] = new_node

    return new_node


def _build_node(tree: Tree, parent: Node, metadata: str, data_list: list, actions_list: list) -> Node:
    """Create a child node, then populate it with data and actions."""
    node = _create_child(tree, parent, metadata)
    _add_data(tree, node, data_list)
    _add_actions(tree, node, actions_list)
    return node


# ============================================================================
# SEED / CLEAR
# ============================================================================

def seed_demo_data():
    """Build the PM demo knowledge graph using Tree class methods."""
    cprint("📦 Initializing Tree from database...")
    tree = Tree(DB_PATH)

    # Load existing graph into memory
    node_data = tree.dao.get_all_nodes()
    tree.construct_graph(node_data)
    cprint(f"   Loaded {len(tree.nodes)} existing node(s)")

    # Ensure a root node exists
    if tree.root is None:
        cprint("\n🌱 No root found — creating Root node...")
        root_uuid = tree.dao.create_node("Root", parent_uuid=None)
        current_time = datetime.now().isoformat()
        tree.root = Node(
            node_uuid=root_uuid,
            metadata="Root",
            created=current_time,
            last_modified=current_time,
            parent_uuid=None,
            children_uuid_arr=[],
            actions=[],
            data=None,
            embedding=None,
        )
        tree.nodes[root_uuid] = tree.root
        cprint(f"   ✓ Root ({root_uuid[:8]}...)")

    root = tree.root
    total_data = 0
    total_actions = 0

    cprint("\n📦 Creating PM Knowledge Graph...")
    cprint("-" * 50)
    cprint(f"   Root ({root.node_uuid[:8]}...)")

    # ------------------------------------------------------------------
    # BRANCH 1: Projects
    # ------------------------------------------------------------------
    projects = _create_child(tree, root, "Projects")
    cprint(f"   ├── Projects ({projects.node_uuid[:8]}...)")

    streamflow = _build_node(tree, projects, "StreamFlow AI Assistant", STREAMFLOW_AI_DATA, STREAMFLOW_AI_ACTIONS)
    total_data += len(STREAMFLOW_AI_DATA)
    total_actions += len(STREAMFLOW_AI_ACTIONS)
    cprint(f"   │   ├── StreamFlow AI Assistant ({streamflow.node_uuid[:8]}...) [{len(STREAMFLOW_AI_DATA)} data, {len(STREAMFLOW_AI_ACTIONS)} actions]")

    mobile = _build_node(tree, projects, "Mobile App Redesign", MOBILE_REDESIGN_DATA, MOBILE_REDESIGN_ACTIONS)
    total_data += len(MOBILE_REDESIGN_DATA)
    total_actions += len(MOBILE_REDESIGN_ACTIONS)
    cprint(f"   │   └── Mobile App Redesign ({mobile.node_uuid[:8]}...) [{len(MOBILE_REDESIGN_DATA)} data, {len(MOBILE_REDESIGN_ACTIONS)} actions]")

    # ------------------------------------------------------------------
    # BRANCH 2: Communications
    # ------------------------------------------------------------------
    comms = _create_child(tree, root, "Communications")
    cprint(f"   ├── Communications ({comms.node_uuid[:8]}...)")

    stakeholder = _build_node(tree, comms, "Stakeholder Updates", STAKEHOLDER_UPDATES_DATA, STAKEHOLDER_UPDATES_ACTIONS)
    total_data += len(STAKEHOLDER_UPDATES_DATA)
    total_actions += len(STAKEHOLDER_UPDATES_ACTIONS)
    cprint(f"   │   ├── Stakeholder Updates ({stakeholder.node_uuid[:8]}...) [{len(STAKEHOLDER_UPDATES_DATA)} data, {len(STAKEHOLDER_UPDATES_ACTIONS)} actions]")

    syncs = _build_node(tree, comms, "Team Syncs", TEAM_SYNCS_DATA, TEAM_SYNCS_ACTIONS)
    total_data += len(TEAM_SYNCS_DATA)
    total_actions += len(TEAM_SYNCS_ACTIONS)
    cprint(f"   │   ├── Team Syncs ({syncs.node_uuid[:8]}...) [{len(TEAM_SYNCS_DATA)} data, {len(TEAM_SYNCS_ACTIONS)} actions]")

    emails = _build_node(tree, comms, "Emails", EMAILS_DATA, EMAILS_ACTIONS)
    total_data += len(EMAILS_DATA)
    total_actions += len(EMAILS_ACTIONS)
    cprint(f"   │   └── Emails ({emails.node_uuid[:8]}...) [{len(EMAILS_DATA)} data, {len(EMAILS_ACTIONS)} actions]")

    # ------------------------------------------------------------------
    # BRANCH 3: Customer Research
    # ------------------------------------------------------------------
    research = _create_child(tree, root, "Customer Research")
    cprint(f"   ├── Customer Research ({research.node_uuid[:8]}...)")

    interviews = _build_node(tree, research, "User Interviews", USER_INTERVIEWS_DATA, USER_INTERVIEWS_ACTIONS)
    total_data += len(USER_INTERVIEWS_DATA)
    total_actions += len(USER_INTERVIEWS_ACTIONS)
    cprint(f"   │   └── User Interviews ({interviews.node_uuid[:8]}...) [{len(USER_INTERVIEWS_DATA)} data, {len(USER_INTERVIEWS_ACTIONS)} actions]")

    # ------------------------------------------------------------------
    # BRANCH 4: Personal
    # ------------------------------------------------------------------
    personal = _create_child(tree, root, "Personal")
    cprint(f"   └── Personal ({personal.node_uuid[:8]}...)")

    career = _build_node(tree, personal, "Career Development", CAREER_DATA, CAREER_ACTIONS)
    total_data += len(CAREER_DATA)
    total_actions += len(CAREER_ACTIONS)
    cprint(f"       └── Career Development ({career.node_uuid[:8]}...) [{len(CAREER_DATA)} data, {len(CAREER_ACTIONS)} actions]")

    # Summary
    new_nodes = 9  # projects, streamflow, mobile, comms, stakeholder, syncs, emails, research, interviews, personal, career — 11 but count top-level separately
    cprint("\n" + "=" * 50)
    cprint("✅ PM Knowledge Graph seeded!")
    cprint("=" * 50)
    cprint(f"""
Graph Structure:
  Root
  ├── Projects
  │   ├── StreamFlow AI Assistant  (main PRD)
  │   └── Mobile App Redesign
  ├── Communications
  │   ├── Stakeholder Updates
  │   ├── Team Syncs
  │   └── Emails
  ├── Customer Research
  │   └── User Interviews
  └── Personal
      └── Career Development

Total: 11 new nodes, {total_data} data entries, {total_actions} actions
""")

    tree.dao.close()


def clear_demo_nodes():
    """Remove all demo nodes from the graph using the DAO's delete_node method."""
    demo_metadata = [
        # Legacy names from old versions
        "Project Management", "StreamFlow", "AI Assistant",
        # Current structure
        "Projects", "StreamFlow AI Assistant", "Mobile App Redesign",
        "Communications", "Stakeholder Updates", "Team Syncs", "Emails",
        "Customer Research", "User Interviews",
        "Personal", "Career Development",
    ]

    cprint("📦 Loading Tree for cleanup...")
    tree = Tree(DB_PATH)
    node_data = tree.dao.get_all_nodes()
    tree.construct_graph(node_data)
    cprint(f"   Loaded {len(tree.nodes)} node(s)")

    deleted_count = 0
    for node_uuid, node in list(tree.nodes.items()):
        if node.metadata in demo_metadata:
            cprint(f"   Deleting: {node.metadata} ({node_uuid[:8]}...)")
            # DAO handles: removing from parent's children_uuid_arr, cascading deletes
            tree.dao.delete_node(node_uuid, cascade=True)

            # Update in-memory tree
            if node.parent:
                if node in node.parent.children:
                    node.parent.children.remove(node)
                if node_uuid in node.parent.children_uuid_arr:
                    node.parent.children_uuid_arr.remove(node_uuid)

            if node_uuid in tree.nodes:
                del tree.nodes[node_uuid]

            deleted_count += 1

    tree.dao.close()
    return deleted_count


# ============================================================================
# WATCH MODE
# ============================================================================

def watch_for_keystroke():
    """Watch for keystrokes to trigger seeding or clearing."""
    cprint("\n⌨️  Keystroke watcher mode")
    cprint("   Press 'D' to seed demo data")
    cprint("   Press 'C' to clear demo data")
    cprint("   Press 'Q' to quit")
    cprint("-" * 40)

    try:
        from pynput import keyboard

        def on_press(key):
            try:
                if key.char and key.char.lower() == 'd':
                    cprint("\n🚀 Triggered: Seeding demo data...")
                    seed_demo_data()
                    cprint("\n⌨️  Waiting for keystroke...")
                elif key.char and key.char.lower() == 'c':
                    cprint("\n🗑️  Triggered: Clearing demo data...")
                    deleted = clear_demo_nodes()
                    cprint(f"   Deleted {deleted} demo nodes")
                    cprint("\n⌨️  Waiting for keystroke...")
                elif key.char and key.char.lower() == 'q':
                    cprint("\n👋 Exiting watcher mode")
                    return False
            except AttributeError:
                pass

        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()

    except ImportError:
        cprint("\n⚠️  pynput not installed. Using simple input mode.")
        cprint("   Install with: pip install pynput")
        cprint("\nPress Enter to seed, 'c' to clear, 'q' to quit:")

        while True:
            user_input = input("> ").strip().lower()
            if user_input == 'q':
                break
            elif user_input == 'c':
                deleted = clear_demo_nodes()
                cprint(f"🗑️  Deleted {deleted} demo nodes")
            else:
                cprint("🚀 Seeding demo data...")
                seed_demo_data()
                cprint("\nPress Enter to seed again, 'c' to clear, 'q' to quit:")


# ============================================================================
# MAIN
# ============================================================================

def main():
    global DB_PATH

    parser = argparse.ArgumentParser(description="Seed PRD-based demo nodes")
    parser.add_argument("--clear", action="store_true", help="Clear existing demo nodes")
    parser.add_argument("--watch", action="store_true", help="Watch for keystroke to trigger seeding")
    parser.add_argument("--db-path", default=DB_PATH, help="Path to the SQLite database")
    args = parser.parse_args()

    DB_PATH = args.db_path

    cprint("=" * 60)
    cprint("🎬 StreamFlow AI Assistant - PRD Demo Seeder")
    cprint("=" * 60)
    cprint(f"📂 Database: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        cprint("❌ Database file not found. Run init_db.py first.")
        sys.exit(1)

    if args.watch:
        watch_for_keystroke()
    else:
        if args.clear:
            cprint("\n🗑️  Clearing existing demo nodes...")
            deleted = clear_demo_nodes()
            cprint(f"   Cleared {deleted} demo node(s)")

        seed_demo_data()


if __name__ == "__main__":
    main()
