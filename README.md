# Covalent

A desktop agent that watches what you're working on and acts before you ask.

---

## What we were trying to build

Every AI assistant we used had the same problem: you have to stop what you're
doing, figure out what you want, and describe it. The tool is only as good as
your ability to articulate the request — which means it's useless in exactly the
moments you're busiest.

Real work doesn't look like that. It's the same handful of workflows over and
over: an email comes in about scheduling, you check a calendar, you draft a
reply, you update a tracker. You already know the steps. Typing them into a chat
box is pure overhead.

**So we wanted an agent with no prompt box at all.** Covalent runs in the
background, watches the screen, and builds a persistent semantic model of how
you actually work. When it recognizes a situation it has seen before, it
proposes the next action — already filled in with the right context — and
executes it on approval.

The bet was that a *hierarchical* memory would make this work where flat vector
search wouldn't. Knowing you're "reading an email" isn't enough to act. You need
to know it's a recruiting email, in the Summer 2026 pipeline, from a candidate
you already scheduled once. So context lives in a tree: broad parent nodes pass
their meaning down to specific children, and a node's embedding is built from
its whole ancestor chain. Retrieval walks the tree instead of scanning a flat
list, which means a suggestion arrives with the full situation attached.

The second bet: an agent is only as useful as what it can actually touch. So
actions run through real integrations (Gmail, Calendar, Docs, Drive, GitHub,
Jira, Notion, Slack) — and when no API exists, it falls back to driving the GUI
directly. Anything you can do on screen, it can do.

---

## How it works

```
screen capture → semantic summary → graph traversal → action proposal → execution
```

1. **Observe.** The Tauri client captures screen context and POSTs a description
   to the Flask backend (`/screen`).
2. **Locate.** `traverse_with_confidence()` embeds the summary and walks the
   knowledge graph for the best-matching node, returning a confidence score. Low
   confidence means the agent stays quiet rather than guessing.
3. **Learn.** `learn_with_structure()` folds new information into the graph —
   creating, splitting, or merging nodes as the picture of your workflow sharpens.
4. **Propose.** With the node's full ancestor context, the action model drafts a
   concrete next step and the tool calls to accomplish it.
5. **Execute.** The action executor routes to the MCP tool layer for API-backed
   work, or to screen control for anything without an API.

Graph state persists in encrypted SQLite, so context compounds across sessions.

---

## Architecture

<img width="2213" height="2380" alt="Architecture diagram" src="https://github.com/user-attachments/assets/feeea2e5-7c08-43aa-aa09-88a27a7cfa0e" />

| Layer | Tech |
|---|---|
| Desktop client | Tauri (Rust + WebView), React, TypeScript, Vite |
| Backend | Flask, encrypted SQLite |
| Context engine | Custom hierarchical graph, NumPy / scikit-learn similarity |
| Tool layer | First-party MCP server (`covalent_mcp/`), LangGraph, LangChain |
| Cloud | AWS Lambda AI gateway, DynamoDB budgets, Terraform, Auth0 |

Models are selected per task in `model_config.yml` rather than hardcoded:

| Task | Provider | Model |
|---|---|---|
| Embeddings | Google | `gemini-embedding-001` |
| Action creation | Bedrock | `claude-sonnet-4-6` |
| Data condensation | Bedrock | `claude-sonnet-4-6` |
| Node traversal | Google | `gemini-2.5-flash` |
| Fit validation | OpenAI | `gpt-5-nano` |

### Layout

```
covalent_mcp/        First-party MCP server + integrations
  toolclasses/       Google, GitHub, Jira, Notion, Slack, filesystem, search
context-engine/      Knowledge graph, retrieval, persistence
lambda/              AWS AI gateway, auth, per-user budgets, Terraform
server/              Flask backend
src/                 React frontend
src-tauri/           Tauri native shell (Rust)
executor/            Screen control automation
.github/workflows/   Signed release builds, Lambda deploys
```

---

## Setup

**Prerequisites:** Python 3.9+, Node 18+, Rust toolchain, macOS (the screen
executor targets darwin).

```bash
git clone https://github.com/KrishivGubba/covalent-calhacks.git
cd covalent-calhacks

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-lock.txt
npm install

cp .env.example .env          # fill in keys — see the file for the full list
cd context-engine && python init_db.py && cd ..
```

For the Google integrations, add an OAuth client config (Desktop app) from the
[Google Cloud Console](https://console.cloud.google.com/apis/credentials):

```bash
cp covalent_mcp/toolclasses/google/oauth_secrets.example.json \
   covalent_mcp/toolclasses/google/oauth_secrets.json
```

On first run the OAuth flow writes `google_credentials.json` alongside it. That
file and `.env` hold live credentials and are gitignored — keep them that way.

Run it:

```bash
cd server && python app.py     # backend
npm run tauri dev              # frontend, separate terminal
```

---

## Team

Four of us built Covalent over ~500 commits, starting at CalHacks 2025 and
continuing well past it.

The system was designed together — the graph model, the agent loop, and the
execution split between MCP tools and screen control were all worked out
collaboratively before the code got written. Commit counts show who typed what,
not who shaped it.

| | Commits | Led |
|---|---:|---|
| hem8705 | 256 | Tauri shell, Flask backend, React UI, Google Docs MCP |
| **Krishiv Gubba** | **147** | **MCP server & integrations, AWS gateway, CI/CD** |
| Ritesh Neela | 95 | Context engine, screen-automation agent |
| Siddharth Ghantasala | 29 | LangGraph orchestration, executor routing |

### What I worked on

I owned three surfaces end to end:

- **`covalent_mcp/`** — the first-party MCP server (stdio and HTTP transports)
  and the pluggable `toolclasses/` system that made adding an integration a
  contained job rather than a refactor. Built the Google (Gmail, Calendar, Docs,
  Drive), GitHub, Jira, Notion, and Slack integrations, including each OAuth flow.
- **`lambda/`** — the AWS gateway that routes model calls across Bedrock, Google,
  and OpenAI behind one interface, with Auth0 authentication and per-user budget
  enforcement in DynamoDB. Provisioned with Terraform.
- **CI/CD** — GitHub Actions for signed and notarized macOS release builds, the
  auto-updater, and automated Lambda deploys.

Beyond that I was in the design of the parts I didn't write — the graph schema
and traversal strategy, and how proposed actions get routed to executors were
worked out jointly at the whiteboard.

Verify any of this directly:

```bash
git shortlog -sne HEAD
git log --author="kgubba@wisc.edu" --oneline
```
