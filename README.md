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
- **Google Gemini**: Text embeddings (text-embedding-004)
- **Claude Sonnet 4.5**: Action generation and orchestration
- **Anthropic API**: LLM inference

### Context Engine
- **NumPy**: Vector operations and cosine similarity
- **scikit-learn**: Similarity calculations
- **Custom Graph System**: Hierarchical knowledge representation

### Action Execution
- **LangGraph**: Agentic workflow orchestration
- **Composio**: MCP (Model Context Protocol) integrations
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
├── context-engine/           # Core intelligence engine
│   ├── graph.py             # Knowledge graph & retrieval
│   ├── graph_dao.py         # Database access layer
│   └── init_db.py           # Database initialization
│
├── server/                  # Flask backend
│   ├── app.py              # API endpoints
│   └── start_server.sh     # Server startup script
│
├── src/                     # React frontend
│   ├── components/
│   │   ├── FloatingAssistant.tsx
│   │   ├── ControlButtons.tsx
│   │   └── Header.tsx
│   └── App.tsx
│
├── src-tauri/              # Tauri native wrapper
│   └── src/
│       └── main.rs         # Rust backend
│
├── executor/               # Screen control automation
│   ├── main.py
│   └── action_run.py
│
├── LLMGraph.py            # LangGraph orchestration
├── GSuite_router.py       # GSuite routing logic
└── requirements.txt       # Python dependencies
```

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.9+
- Node.js 18+
- Rust (for Tauri)
- API Keys:
  - `GOOGLE_API_KEY` (for Gemini embeddings)
  - `ANTHROPIC_API_KEY` (for Claude)
  - `COMPOSIO_API_KEY` (for MCP integrations)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/covalent-calhacks.git
cd covalent-calhacks
```

2. **Set up Python environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Initialize the database**
```bash
cd context-engine
python init_db.py
```

4. **Configure environment variables**
```bash
# Create .env file
GOOGLE_API_KEY=your_gemini_key
ANTHROPIC_API_KEY=your_claude_key
COMPOSIO_API_KEY=your_composio_key
USER_ID=your_user_id
GOOGLE_AUTH_CONFIG_ID=your_auth_config
```

5. **Install frontend dependencies**
```bash
npm install
```

6. **Start the backend**
```bash
cd server
python app.py
```

7. **Start the frontend**
```bash
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

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines and submit PRs.

---

## 🏆 Acknowledgments

Built during CalHacks 2025. Inspired by the vision of AI that doesn't wait for prompts—it anticipates your needs.

---

**Covalent.ai**: The AI that doesn't wait for prompts—it anticipates your next move.
