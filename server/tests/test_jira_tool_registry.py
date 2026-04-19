from covalent_mcp.tools import TOOL_MODULES, get_display_schema


def test_jira_tools_are_registered():
    assert any(module.__class__.__name__ == "JiraToolModule" for module in TOOL_MODULES)
    assert get_display_schema("create_jira_issue") is not None
    assert get_display_schema("transition_jira_issue") is not None
