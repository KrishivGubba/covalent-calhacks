"""
Base MCP Tool Module - Abstract base class for all tool modules.

All tool modules MUST inherit from this and implement the register() method.
This enforces the contract that every tool module must define how to register its tools.
"""
import sys
from pathlib import Path
from abc import ABC, abstractmethod

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    # Only needed for type-checking; avoid import-time dependency.
    from fastmcp import FastMCP


# =============================================================================
# DISPLAY SCHEMA TYPES
# =============================================================================

# UI Widget types - maps to frontend HTML elements
# text_input       -> <input type="text">
# textarea         -> <textarea>
# datetime_picker  -> <input type="datetime-local">
# email_list       -> chip/tag input (comma-separated emails)
# toggle           -> <input type="checkbox"> / switch
# select           -> <select> dropdown (requires `options` list)
# display_text     -> read-only <span> / <p>
# display_datetime -> read-only formatted date string
# display_list     -> read-only comma-separated list

VALID_WIDGETS = {
    "text_input",
    "textarea",
    "datetime_picker",
    "email_list",
    "toggle",
    "select",
    "display_text",
    "display_datetime",
    "display_list",
}


@dataclass
class DisplayField:
    """
    A single field to show in the approval UI for a tool call.

    Attributes:
        key:         Field identifier. If source="param", must match a tool parameter name.
                     If source="resolved", can be any name (populated by the resolve function).
        label:       Human-readable label shown in the UI (e.g. "Event Title").
        source:      Where the value comes from:
                       "param"    - directly from the LLM-proposed tool parameters
                       "resolved" - populated by the resolve function (extra API call)
        editable:    Whether the user can edit this field before approving.
        widget:      UI widget type (see VALID_WIDGETS).
        required:    Whether the field must have a value to approve.
        placeholder: Placeholder text for editable fields.
        options:     For "select" widget: list of {"value": ..., "label": ...} dicts.
        format_hint: Optional hint for the frontend (e.g. "RFC3339" for datetime fields).
    """
    key: str
    label: str
    source: str = "param"       # "param" or "resolved"
    editable: bool = True
    widget: str = "text_input"
    required: bool = False
    placeholder: str = ""
    options: Optional[List[Dict[str, str]]] = None
    format_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON response."""
        d = {
            "key": self.key,
            "label": self.label,
            "source": self.source,
            "editable": self.editable,
            "widget": self.widget,
            "required": self.required,
        }
        if self.placeholder:
            d["placeholder"] = self.placeholder
        if self.options is not None:
            d["options"] = self.options
        if self.format_hint:
            d["format_hint"] = self.format_hint
        return d


@dataclass
class PassableOutput:
    """
    Describes an output field that can be passed to subsequent steps in a chain.
    
    Attributes:
        key:         The field name in the tool's result dict (e.g., "id", "document_id")
        description: Human-readable description for LLM context (e.g., "The ID of the created document")
        example:     Optional example value for LLM context
    """
    key: str
    description: str
    example: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = {"key": self.key, "description": self.description}
        if self.example:
            d["example"] = self.example
        return d


@dataclass
class ToolDisplaySchema:
    """
    Display schema for a single tool - defines how its approval UI looks.

    Attributes:
        tool_name:       The MCP tool name (must match exactly).
        display_name:    Human-readable action name (e.g. "Create Calendar Event").
        description:     Short description shown in the approval card.
        fields:          Ordered list of DisplayField to show.
        resolve:         Optional async callable: (params: dict) -> dict of extra resolved fields.
                         Called server-side before sending to frontend.
                         Returns a dict mapping field keys to their resolved values.
                         Example: resolve({"event_id": "abc"}) -> {"event_name": "Team Standup"}
        passable_outputs: List of outputs this tool returns that can be used by subsequent
                         steps in a multi-action chain. Used during planning to tell the LLM
                         what variables will be available after this tool runs.
    """
    tool_name: str
    display_name: str
    description: str = ""
    fields: List[DisplayField] = field(default_factory=list)
    resolve: Optional[Callable] = None
    passable_outputs: List[PassableOutput] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON response (excludes the resolve callable)."""
        d = {
            "tool_name": self.tool_name,
            "display_name": self.display_name,
            "description": self.description,
            "fields": [f.to_dict() for f in self.fields],
        }
        if self.passable_outputs:
            d["passable_outputs"] = [p.to_dict() for p in self.passable_outputs]
        return d


# =============================================================================
# DISPLAY FIELD RESOLUTION
# =============================================================================

import re

# Regex to detect variable references like {{$1.id}} or {{$2.document_id}}
_VARIABLE_REF_PATTERN = re.compile(r'\{\{\$(\d+)\.(\w+)\}\}')


def _is_inherited_value(value: Any) -> bool:
    """Check if a value contains a variable reference from a previous step."""
    if not isinstance(value, str):
        return False
    return bool(_VARIABLE_REF_PATTERN.search(value))


def _make_synthetic_field(key: str, value: Any) -> Dict[str, Any]:
    """
    Create a synthetic read-only DisplayField for an inherited parameter.
    
    These are parameters that aren't in the tool's DisplayField list but
    contain variable references (e.g., {{$1.id}}) and should be shown
    to the user so they understand the chain dependencies.
    """
    return {
        "key": key,
        "label": key.replace("_", " ").title(),
        "source": "inherited",
        "editable": False,
        "widget": "display_text",
        "required": False,
        "value": value,
    }


async def resolve_display_fields(
    schema: ToolDisplaySchema,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Resolve display fields for a tool call.

    Takes the tool's display schema and the LLM-proposed parameters,
    runs the resolve function if present, and returns a dict ready for the frontend:

    {
        "display_name": "Create Calendar Event",
        "description": "...",
        "fields": [
            {"key": "summary", "label": "Event Title", "value": "Team Standup", "editable": True, "widget": "text_input", ...},
            {"key": "event_name", "label": "Event", "value": "Team Standup", "editable": False, "widget": "display_text", ...},
        ]
    }

    For tools WITHOUT a display schema, returns None (caller should fall back
    to showing raw params).
    
    INHERITED FIELDS:
    If a parameter contains a variable reference (e.g., {{$1.id}}) but is NOT
    in the tool's DisplayField list, we inject a synthetic read-only field so
    the user can see the chain dependency. This is important for multi-step
    actions where one tool's output feeds into another.
    """
    # Run the resolve function to get extra fields (e.g. event name from event_id)
    resolved_values = {}
    if schema.resolve is not None:
        try:
            resolved_values = await schema.resolve(params)
            if resolved_values is None:
                resolved_values = {}
        except Exception as e:
            log.warning(f"Warning: resolve function failed for {schema.tool_name}: {e}")
            resolved_values = {}

    # Build the display fields with values populated
    display_fields = []
    display_field_keys = set()
    
    for field_def in schema.fields:
        field_dict = field_def.to_dict()
        display_field_keys.add(field_def.key)

        if field_def.source == "param":
            field_dict["value"] = params.get(field_def.key)
        elif field_def.source == "resolved":
            field_dict["value"] = resolved_values.get(field_def.key)

        display_fields.append(field_dict)

    # Auto-inject synthetic fields for inherited parameters that aren't in the schema
    # This ensures users can see chain dependencies even for "hidden" params like IDs
    for key, value in params.items():
        if key not in display_field_keys and _is_inherited_value(value):
            display_fields.append(_make_synthetic_field(key, value))

    return {
        "display_name": schema.display_name,
        "description": schema.description,
        "fields": display_fields,
    }


# =============================================================================
# BASE MODULE CLASS
# =============================================================================

class MCPToolModule(ABC):
    """
    Abstract base class for MCP tool modules.
    
    Every tool module must inherit from this and implement register(mcp).
    Optionally, implement register_resources(mcp) to expose read-only resources.
    Optionally, implement get_display_schemas() to define approval UI schemas.
    This ensures a consistent interface across all tool modules.
    
    Example:
        class MyToolModule(MCPToolModule):
            def register(self, mcp: FastMCP) -> None:
                @mcp.tool()
                def my_tool(param: str) -> str:
                    return f"Result: {param}"
            
            def register_resources(self, mcp: FastMCP) -> None:
                @mcp.resource()
                def my_resource(uri: str) -> str:
                    return "Resource content"
            
            def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
                return {
                    "my_tool": ToolDisplaySchema(
                        tool_name="my_tool",
                        display_name="My Tool",
                        fields=[DisplayField(key="param", label="Parameter")],
                    )
                }
    """
    
    @abstractmethod
    def register(self, mcp: "FastMCP") -> None:
        """
        Register this module's tools with the MCP server.
        
        This method MUST be implemented by all tool modules.
        Use @mcp.tool() decorator to register each tool function.
        
        Args:
            mcp: The FastMCP server instance to register tools with
        
        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement register(mcp) method"
        )
    
    def register_resources(self, mcp: "FastMCP") -> None:
        """
        Register this module's resources with the MCP server.
        
        This method is OPTIONAL. Override it if your module provides resources.
        Use @mcp.resource() decorator to register each resource function.
        
        Resources are read-only data that clients can fetch for context.
        They are application-controlled (client decides when to load them),
        unlike tools which are model-controlled (model decides when to invoke).
        
        Args:
            mcp: The FastMCP server instance to register resources with
        
        Default implementation: Does nothing (no resources).
        """
        pass  # Default: no resources

    def get_display_schemas(self) -> Dict[str, "ToolDisplaySchema"]:
        """
        Return display schemas for this module's tools.

        Override this to define how each tool's approval UI should look.
        The keys must match the MCP tool names exactly.

        Returns:
            Dict mapping tool_name -> ToolDisplaySchema.
            Default: empty dict (tools will show raw params as fallback).
        """
        return {}