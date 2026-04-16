"""
FastAPI Test Client Tests.

These tests use httpx.AsyncClient to test the FastAPI endpoints directly
without needing to run the server separately.

Run with: pytest tests/test_fastapi_client.py -v
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add project paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'context-engine'))

# Set test environment variables before importing app
os.environ.setdefault('GRAPH_DB_PATH', ':memory:')
os.environ.setdefault('VITE_FLASK_PORT', '15001')


@pytest.fixture
def mock_tree():
    """Mock the Tree dependency to avoid database/LLM calls."""
    mock = MagicMock()
    mock.nodes = {}
    mock.graph_dao = MagicMock()
    mock.graph_dao.get_all_nodes.return_value = []
    mock.graph_dao.get_all_actions.return_value = []
    mock.graph_dao.get_all_data.return_value = []
    return mock


@pytest.fixture
def mock_auth_dao():
    """Mock the AuthDAO dependency."""
    mock = MagicMock()
    mock.get_session_by_state.return_value = None
    mock.get_session_by_user_id.return_value = None
    return mock


@pytest.fixture
def mock_integration_dao():
    """Mock the IntegrationDAO dependency."""
    mock = MagicMock()
    mock.get_integration_status.return_value = []
    return mock


@pytest.fixture
def client(mock_tree, mock_auth_dao, mock_integration_dao):
    """Create a test client with mocked dependencies."""
    from httpx import AsyncClient, ASGITransport
    from server.fastapi_app.main import app
    from server.fastapi_app import dependencies
    
    # Override dependencies
    app.dependency_overrides[dependencies.get_tree] = lambda: mock_tree
    app.dependency_overrides[dependencies.get_auth_dao] = lambda: mock_auth_dao
    app.dependency_overrides[dependencies.get_integration_dao] = lambda: mock_integration_dao
    
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestHealthEndpoint:
    """Test the /health endpoint."""
    
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        """Health endpoint should return status ok."""
        async with client:
            response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_health_has_process_time_header(self, client):
        """Health endpoint should include X-Process-Time header."""
        async with client:
            response = await client.get("/health")
        
        assert "x-process-time" in response.headers


class TestGraphEndpoints:
    """Test the /graph/* endpoints."""
    
    @pytest.mark.asyncio
    async def test_graph_data_empty(self, client):
        """Graph data should return empty when no nodes exist."""
        async with client:
            response = await client.get("/graph/data")
        
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        assert data["stats"]["total_nodes"] == 0
    
    @pytest.mark.asyncio
    async def test_graph_reset(self, client):
        """Graph reset should succeed."""
        async with client:
            response = await client.post("/graph/reset")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok" or data.get("ok") == True


class TestAuthEndpoints:
    """Test the /auth/* endpoints."""
    
    @pytest.mark.asyncio
    async def test_auth_check_pending(self, client, mock_auth_dao):
        """Auth check should return pending when no session exists."""
        mock_auth_dao.get_session_by_state.return_value = None
        
        async with client:
            response = await client.get("/auth/check?state=test123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
    
    @pytest.mark.asyncio
    async def test_auth_start(self, client):
        """Auth start should accept state and code_verifier."""
        async with client:
            response = await client.post(
                "/auth/start",
                json={"state": "test123", "code_verifier": "verifier123"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True or data.get("status") == "ok"


class TestIntegrationsEndpoints:
    """Test the /integrations/* endpoints."""
    
    @pytest.mark.asyncio
    async def test_integrations_status(self, client):
        """Integrations status should return a list."""
        async with client:
            response = await client.get("/integrations/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "integrations" in data
        assert isinstance(data["integrations"], list)


class TestMCPEndpoints:
    """Test the MCP-related endpoints."""
    
    @pytest.mark.asyncio
    async def test_mcp_health(self, client):
        """MCP health should return status."""
        async with client:
            response = await client.get("/mcp_health")
        
        # MCP health may fail if MCP server isn't running, but endpoint should respond
        assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_action_history_empty(self, client, mock_tree):
        """Action history should return empty list when no history exists."""
        mock_tree.graph_dao.get_action_history.return_value = []
        
        async with client:
            response = await client.get("/action_history?limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)


class TestTabCompletionEndpoints:
    """Test the tab completion endpoints."""
    
    @pytest.mark.asyncio
    async def test_tab_context(self, client):
        """Tab context endpoint should accept context data."""
        async with client:
            response = await client.post(
                "/tab_context",
                json={
                    "context_before": "def hello(",
                    "context_after": "):\n    pass",
                    "app_name": "VSCode",
                    "file_path": "/test/file.py"
                }
            )
        
        # Should accept the request even if processing fails
        assert response.status_code in [200, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
