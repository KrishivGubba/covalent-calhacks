# Covalent.ai 

**A Promptless AI Desktop Agent with Proactive Intelligence**

Covalent.ai is an autonomous desktop agent that continuously monitors your screen, learns your workflows, and proactively suggests actions before you even ask. Unlike traditional AI assistants that wait for prompts, Covalent anticipates your needs using a proprietary context engine and executes tasks through MCP integrations and screen control.

---

## 🎯 Core Concept

**The Problem**: Existing AI agents are reactive—you prompt, they respond. But real work doesn't happen that way. You juggle contexts, repeat workflows, and constantly switch between apps.

**Our Solution**: Covalent runs silently in the background, building a semantic understanding of your workflows through continuous observation. When it detects patterns, it proactively suggests actions and executes them autonomously.

---

## 🏗️ Architecture Overview
<img width="2213" height="2380" alt="Mermaid Chart - Create complex, visual diagrams with text -2025-10-26-145616" src="https://github.com/user-attachments/assets/feeea2e5-7c08-43aa-aa09-88a27a7cfa0e" />


## 🔧 Technical Stack

### Frontend
- **Tauri**: Native desktop application framework (Rust + WebView)
- **React**: UI components and state management
- **TypeScript**: Type-safe frontend code
- **Vite**: Fast build tooling

### Backend
- **Flask**: Lightweight Python web server
- **SQLite**: Persistent graph database
- **AWS Lambda + Terraform**: AI gateway, auth, and per-user budget enforcement
- **Auth0**: User authentication

### Models
Model selection is configured per-task in `model_config.yml` rather than hardcoded:

| Task | Provider | Model |
|---|---|---|
| Embeddings | Google | `gemini-embedding-001` |
| Action creation & learning | Bedrock | `claude-sonnet-4-6` |
| Data condensation | Bedrock | `claude-sonnet-4-6` |
| Node traversal | Google | `gemini-2.5-flash` |
| Fit validation | OpenAI | `gpt-5-nano` |

### Context Engine
- **NumPy**: Vector operations and cosine similarity
- **scikit-learn**: Similarity calculations
- **Custom Graph System**: Hierarchical knowledge representation

### Action Execution
- **LangGraph**: Agentic workflow orchestration
- **Custom MCP server** (`covalent_mcp/`): first-party Model Context Protocol
  implementation with a pluggable tool-class system. Integrations: Google
  (Gmail/Calendar/Docs/Drive), GitHub, Jira, Notion, Slack, filesystem,
  Perplexity and Tavily search.
- **LangChain**: Agent creation and tool binding

---

## 🔄 How It Works

### 1. **Screen Monitoring & Learning**
```python
# Frontend captures screen content
screen_description = "User is viewing an email about scheduling a meeting"

# Send to backend
POST /screen
{
  "description": screen_description,
  "data": {...}
}
```

### 2. **Context Retrieval**
```python
# Backend: graph.py - traverse()
def traverse(self, screen):
    # Convert screen description to embedding
    screen_embedding = self.vectorize_text(screen)
    
    # Find most similar node using cosine similarity
    for node in self.nodes:
        similarity = cosine_similarity(screen_embedding, node.embedding)
        if similarity > best_similarity:
            best_node = node
    
    return best_node
```

### 3. **Proactive Action Generation**
```python
# Backend: graph.py - learn()
def learn(self, summary, data):
    # Find relevant node
    node = self.traverse(summary)
    
    # Generate action using Claude with full context
    mtd = self.get_parent_metadata(node)  # Get all ancestor context
    
    prompt = f"""
    Based on context: {mtd}
    Current activity: {summary}
    
    Suggest a proactive action the user might want to take.
    """
    
    action = claude.messages.create(prompt)
    
    # Store action in database
    action_uuid = self.dao.add_action(node.node_uuid, action)
    
    return action, action_uuid
```

### 4. **Action Execution**
```python
# Backend: LLMGraph.py
async def orchestrator(state):
    # Parse action and route to appropriate executor
    tasks = parse_action(state['task'])
    
    if "email" in task or "calendar" in task:
        return Send("gsuite", state)
    else:
        return Send("screen controller", state)

# GSuite MCP execution
async def gsuite(state):
    # Use Composio to execute GSuite actions
    session = composio.tool_router.create_session(user_id)
    tools = await client.get_tools()
    agent = create_agent("claude-sonnet-4-5", tools)
    
    result = await agent.ainvoke({"messages": [task]})
    return result

# Screen control execution
def screen_controller(state):
    # Execute screen automation
    from executor.main import thingy
    thingy(state['sc_tasks'][0])
```

---

## 📁 Project Structure

```
covalent-calhacks/
├── covalent_mcp/            # First-party MCP server + integrations
│   ├── server.py            # MCP server (stdio)
│   ├── server_http.py       # MCP server (HTTP transport)
│   ├── client.py            # MCP client
│   ├── agent_integration.py # Tool routing into the agent loop
│   └── toolclasses/         # Pluggable integrations
│       ├── google/          # Gmail, Calendar, Docs, Drive
│       ├── github/  jira/  notion/  slack/
│       ├── filesystem/  perplexity_search/  tavily_search/
│       └── _template.py     # Scaffold for new integrations
│
├── context-engine/          # Core intelligence engine
│   ├── graph.py             # Knowledge graph & retrieval
│   ├── graph_dao.py         # Database access layer
│   └── init_db.py           # Database initialization
│
├── lambda/                  # AWS AI gateway
│   ├── ai-gateway.py        # Model routing + auth
│   ├── perplexity-gateway.py
│   ├── budget_metadata.py   # Per-user budget enforcement
│   └── terraform/           # Infrastructure as code
│
├── server/                  # Flask backend
├── src/                     # React frontend (Vite)
├── src-tauri/               # Tauri native shell (Rust)
├── executor/                # Screen control automation
├── llm-interactions/        # Prompt & interaction layer
├── tests/                   # Test suite
├── .github/workflows/       # CI: signed release builds, Lambda deploy
│
├── action_executor.py       # Action execution engine
├── LLMGraph_claude.py       # LangGraph orchestration
├── GSuite_router.py         # GSuite routing logic
├── model_config.yml         # Per-task model selection
└── requirements.txt         # Python dependencies
```

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.9+
- Node.js 18+
- Rust toolchain (for Tauri)
- macOS (screen-control executor targets darwin)

### Installation

**1. Clone**
```bash
git clone https://github.com/KrishivGubba/covalent-calhacks.git
cd covalent-calhacks
```

**2. Python environment**
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-lock.txt
```

**3. Configure environment**
```bash
cp .env.example .env
```
Then fill in `.env`. At minimum you need `ANTHROPIC_API_KEY` plus the Google
OAuth credentials (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`) for the GSuite
integrations. See `.env.example` for the full list, grouped by subsystem.

For the Google integrations you also need an OAuth client config from the
[Google Cloud Console](https://console.cloud.google.com/apis/credentials)
(Desktop app credentials):
```bash
cp covalent_mcp/toolclasses/google/oauth_secrets.example.json \
   covalent_mcp/toolclasses/google/oauth_secrets.json
```
Fill in your `client_id` / `client_secret`. On first run the OAuth flow writes
`google_credentials.json` next to it — that file holds a live refresh token.

> **Note:** `.env`, `oauth_secrets.json`, and `google_credentials.json` are all
> gitignored and must stay that way. They hold live credentials — never commit them.

**4. Initialize the database**
```bash
cd context-engine && python init_db.py && cd ..
```

**5. Frontend dependencies**
```bash
npm install
```

**6. Run**
```bash
# backend
cd server && python app.py

# frontend (separate terminal)
npm run tauri dev
```

---

## 🧠 Key Innovations

### 1. **Hierarchical Context Engine**
Unlike flat vector databases, our graph structure maintains semantic relationships:
- **Parent nodes** contain broad context (e.g., "Recruiting")
- **Child nodes** inherit parent context + add specifics (e.g., "Summer 2026 Interns")
- **Embeddings** created from full metadata chain for accurate retrieval

### 2. **Proactive Intelligence**
Traditional agents wait for prompts. Covalent:
- Continuously learns from screen content
- Predicts next actions based on patterns
- Suggests tasks at the right moment

### 3. **Dual Execution Paths**
- **MCP Tools**: For API-based actions (email, calendar, docs)
- **Screen Control**: For visual automation beyond APIs

### 4. **Context-Aware Routing**
LangGraph orchestrator intelligently routes tasks based on:
- Action type (API-accessible vs. screen-only)
- User context (what node they're in)
- Available tools

---

## 📊 Database Schema

### Nodes Table
```sql
CREATE TABLE nodes (
    UUID TEXT PRIMARY KEY,
    Metadata TEXT,
    Created TEXT,
    Last_Modified TEXT,
    Parent_UUID TEXT,
    Children_UUID_arr TEXT,  -- JSON array
    FOREIGN KEY (Parent_UUID) REFERENCES nodes(UUID)
);
```

### Actions Table
```sql
CREATE TABLE action_table (
    UUID TEXT PRIMARY KEY,
    Action_name TEXT,
    Node_UUID TEXT,
    FOREIGN KEY (Node_UUID) REFERENCES nodes(UUID)
);
```

### Data Table
```sql
CREATE TABLE data_table (
    UUID TEXT PRIMARY KEY,
    Node_UUID TEXT,
    Key TEXT,
    Data_Type TEXT,
    Info TEXT,
    FOREIGN KEY (Node_UUID) REFERENCES nodes(UUID)
);
```

---

## 🎯 Use Cases

1. **Email Management**: Sees you reading a scheduling email → drafts calendar invite
2. **Recruiting Workflows**: Detects candidate email → suggests interview scheduling + context retrieval
3. **Document Creation**: Notices repetitive doc creation → suggests template + automation
4. **Meeting Follow-ups**: After meetings → generates follow-up email draft with action items
5. **Data Analysis**: Sees you working with data → suggests export/visualization tasks

---

## 🔮 Future Roadmap

- [ ] Multi-modal learning (vision + OCR)
- [ ] Cross-application workflow chaining
- [ ] Self-improving action model (feedback loop)
- [ ] Team collaboration features
- [ ] Mobile companion app
- [ ] Plugin marketplace for custom MCPs

---

## 👥 Team & Contributions

Covalent was built by four people over ~500 commits. Rough ownership, derived
from `git shortlog` and per-directory commit history:

| Contributor | Commits | Primary areas |
|---|---:|---|
| **hem8705** | 256 | Tauri shell (`src-tauri/`), Flask backend, React UI, Google Docs MCP |
| **Krishiv Gubba** | 146 | MCP server & integrations (`covalent_mcp/`), AWS Lambda AI gateway (`lambda/`), CI/CD & signed release pipeline |
| **Ritesh Neela** | 95 | Context engine (`context-engine/`), Agent-S screen-control fork |
| **Siddharth Ghantasala** | 29 | LangGraph orchestration, executor routing |

Verify any of this yourself:
```bash
git shortlog -sne HEAD
git log --author="kgubba@wisc.edu" --oneline
```

### Krishiv's contributions in detail
- **`covalent_mcp/`** — first-party MCP server (stdio + HTTP transports) and the
  pluggable `toolclasses/` system. Built the Google (Gmail/Calendar/Docs/Drive),
  GitHub, Jira, Notion, and Slack integrations, including the OAuth flows for each.
- **`lambda/`** — AWS AI gateway routing model calls across Bedrock/Google/OpenAI,
  with Auth0-backed authentication and per-user budget enforcement (DynamoDB),
  provisioned via Terraform.
- **CI/CD** — GitHub Actions for signed/notarized macOS release builds and the
  auto-updater, plus automated Lambda deploys.

---

## 🏆 Acknowledgments

Started at CalHacks 2025 and developed well beyond the hackathon. Inspired by the
vision of AI that doesn't wait for prompts—it anticipates your needs.

---

**Covalent.ai**: The AI that doesn't wait for prompts—it anticipates your next move.
