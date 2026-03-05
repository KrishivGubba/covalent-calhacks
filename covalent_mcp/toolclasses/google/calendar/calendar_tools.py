"""
Google Calendar MCP Tools - Calendar and Event operations.

Exposes Google Calendar operations as MCP tools and resources for LLM agents.
Token is managed by the server via OAuth flow - MCP reads token from database.
"""
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()
from typing import Dict, Optional, List
from covalent_mcp.toolclasses.base import (
    MCPToolModule,
    ToolDisplaySchema,
    DisplayField,
)
from covalent_mcp.toolclasses.google.calendar.calendar_client import CalendarService
from fastmcp import FastMCP


class CalendarToolModule(MCPToolModule):
    """
    Google Calendar tool module for calendar and event operations.
    
    Provides MCP tools for:
    - Creating/updating/deleting events
    - Updating calendar settings (NOT WORKING - insufficient permissions)
    
    Provides MCP resources for:
    - Listing/getting calendars (NOT WORKING - insufficient permissions)
    - Listing/getting events
    
    Note: Calendar-level operations (list_calendars, get_calendar, update_calendar) 
    require additional OAuth scopes that are not currently configured.
    """
    
    def __init__(self):
        """Initialize Calendar tool module."""
        self._client = None
    
    def _ensure_client(self) -> CalendarService:
        """Ensure Calendar client is initialized with fresh credentials from database."""
        # Re-create on every call so token refresh is picked up
        self._client = CalendarService()
        return self._client

    # -----------------------------------------------------------------
    # Resolve helpers (used by display schemas)
    # -----------------------------------------------------------------

    async def _resolve_event_details(self, params: dict) -> dict:
        """
        Fetch event details from Google Calendar so the approval UI can show
        human-readable info (event name, times, etc.) instead of just an event_id.
        """
        event_id = params.get("event_id", "")
        calendar_id = params.get("calendar_id", "primary")
        if not event_id:
            return {}
        try:
            client = self._ensure_client()
            event = client.get_event(event_id, calendar_id)
            if not event:
                return {"event_name": "(event not found)"}
            start = event.get("start", {})
            end = event.get("end", {})
            return {
                "event_name": event.get("summary", "(no title)"),
                "current_start": start.get("dateTime") or start.get("date", ""),
                "current_end": end.get("dateTime") or end.get("date", ""),
                "current_location": event.get("location", ""),
                "current_description": event.get("description", ""),
                "current_attendees": [
                    a.get("email", "") for a in (event.get("attendees") or [])
                ],
            }
        except Exception as e:
            log.warning(f"Warning: failed to resolve event details for {event_id}: {e}")
            return {"event_name": "(could not load event)"}

    # -----------------------------------------------------------------
    # Display schemas
    # -----------------------------------------------------------------

    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        """Return display schemas for calendar tools."""
        return {
            # ----------------------------------------------------------
            # CREATE EVENT
            # ----------------------------------------------------------
            "create_event": ToolDisplaySchema(
                tool_name="create_event",
                display_name="Create Calendar Event",
                description="Create a new event on your Google Calendar.",
                fields=[
                    DisplayField(
                        key="summary",
                        label="Event Title",
                        source="param",
                        editable=True,
                        required=True,
                        widget="text_input",
                        placeholder="e.g. Team Standup",
                    ),
                    DisplayField(
                        key="start_time",
                        label="Start",
                        source="param",
                        editable=True,
                        required=True,
                        widget="datetime_picker",
                        format_hint="RFC3339",
                    ),
                    DisplayField(
                        key="end_time",
                        label="End",
                        source="param",
                        editable=True,
                        required=True,
                        widget="datetime_picker",
                        format_hint="RFC3339",
                    ),
                    DisplayField(
                        key="location",
                        label="Location",
                        source="param",
                        editable=True,
                        widget="text_input",
                        placeholder="e.g. Conference Room B",
                    ),
                    DisplayField(
                        key="description",
                        label="Description",
                        source="param",
                        editable=True,
                        widget="textarea",
                        placeholder="Event details...",
                    ),
                    DisplayField(
                        key="attendees",
                        label="Attendees",
                        source="param",
                        editable=True,
                        widget="email_list",
                        placeholder="Add email addresses...",
                    ),
                    DisplayField(
                        key="send_notifications",
                        label="Notify Attendees",
                        source="param",
                        editable=True,
                        widget="toggle",
                    ),
                ],
                resolve=None,  # all fields come straight from params
            ),

            # ----------------------------------------------------------
            # UPDATE EVENT
            # ----------------------------------------------------------
            "update_event": ToolDisplaySchema(
                tool_name="update_event",
                display_name="Update Calendar Event",
                description="Update an existing event on your Google Calendar.",
                fields=[
                    # Resolved: show which event is being updated
                    DisplayField(
                        key="event_name",
                        label="Event",
                        source="resolved",
                        editable=False,
                        widget="display_text",
                    ),
                    DisplayField(
                        key="summary",
                        label="New Title",
                        source="param",
                        editable=True,
                        widget="text_input",
                        placeholder="Leave blank to keep current title",
                    ),
                    DisplayField(
                        key="start_time",
                        label="New Start",
                        source="param",
                        editable=True,
                        widget="datetime_picker",
                        format_hint="RFC3339",
                    ),
                    DisplayField(
                        key="end_time",
                        label="New End",
                        source="param",
                        editable=True,
                        widget="datetime_picker",
                        format_hint="RFC3339",
                    ),
                    DisplayField(
                        key="location",
                        label="New Location",
                        source="param",
                        editable=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="description",
                        label="New Description",
                        source="param",
                        editable=True,
                        widget="textarea",
                    ),
                    DisplayField(
                        key="attendees",
                        label="New Attendees",
                        source="param",
                        editable=True,
                        widget="email_list",
                    ),
                    DisplayField(
                        key="send_notifications",
                        label="Notify Attendees",
                        source="param",
                        editable=True,
                        widget="toggle",
                    ),
                ],
                resolve=self._resolve_event_details,
            ),

            # ----------------------------------------------------------
            # DELETE EVENT
            # ----------------------------------------------------------
            "delete_event": ToolDisplaySchema(
                tool_name="delete_event",
                display_name="Delete Calendar Event",
                description="Permanently delete an event from your Google Calendar.",
                fields=[
                    DisplayField(
                        key="event_name",
                        label="Event",
                        source="resolved",
                        editable=False,
                        widget="display_text",
                    ),
                    DisplayField(
                        key="current_start",
                        label="Start",
                        source="resolved",
                        editable=False,
                        widget="display_datetime",
                    ),
                    DisplayField(
                        key="current_end",
                        label="End",
                        source="resolved",
                        editable=False,
                        widget="display_datetime",
                    ),
                    DisplayField(
                        key="send_notifications",
                        label="Notify Attendees",
                        source="param",
                        editable=True,
                        widget="toggle",
                    ),
                ],
                resolve=self._resolve_event_details,
            ),
        }
    
    def register(self, mcp: FastMCP) -> None:
        """Register Google Calendar tools (write operations) with MCP server."""
        tool_module = self
        
        @mcp.tool()
        def create_event(
            summary: str,
            start_time: str,
            end_time: str,
            calendar_id: str = "primary",
            location: Optional[str] = None,
            description: Optional[str] = None,
            attendees: Optional[List[str]] = None,
            timezone: Optional[str] = None,
            send_notifications: bool = True
        ) -> dict:
            """
            Create a new calendar event.
            
            Args:
                summary: Title of the event
                start_time: Start time in RFC3339 format (e.g., "2024-01-15T10:00:00-08:00")
                end_time: End time in RFC3339 format
                calendar_id: Calendar ID (default: "primary")
                location: Location of the event
                description: Description of the event
                attendees: List of attendee email addresses
                timezone: Timezone for the event (e.g., "America/New_York")
                send_notifications: Whether to send notifications to attendees
            
            Returns:
                Event information including ID and HTML link
            """
            client = tool_module._ensure_client()
            event = client.create_event(
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                calendar_id=calendar_id,
                location=location,
                description=description,
                attendees=attendees,
                timezone=timezone,
                send_notifications=send_notifications
            )
            
            if not event:
                return {"success": False, "error": "Failed to create event"}
            
            return {
                "success": True,
                "id": event.get("id"),
                "summary": event.get("summary"),
                "htmlLink": event.get("htmlLink"),
                "start": event.get("start"),
                "end": event.get("end")
            }
        
        @mcp.tool()
        def update_event(
            event_id: str,
            calendar_id: str = "primary",
            summary: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            location: Optional[str] = None,
            description: Optional[str] = None,
            attendees: Optional[List[str]] = None,
            timezone: Optional[str] = None,
            send_notifications: bool = True
        ) -> dict:
            """
            Update an existing calendar event.
            
            Args:
                event_id: Event ID to update
                calendar_id: Calendar ID (default: "primary")
                summary: New title (optional)
                start_time: New start time in RFC3339 format (optional)
                end_time: New end time in RFC3339 format (optional)
                location: New location (optional)
                description: New description (optional)
                attendees: New list of attendee emails (optional)
                timezone: Timezone for times (optional)
                send_notifications: Whether to send notifications
            
            Returns:
                Updated event information
            """
            client = tool_module._ensure_client()
            event = client.update_event(
                event_id=event_id,
                calendar_id=calendar_id,
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                location=location,
                description=description,
                attendees=attendees,
                timezone=timezone,
                send_notifications=send_notifications
            )
            
            if not event:
                return {"success": False, "error": "Failed to update event"}
            
            return {
                "success": True,
                "id": event.get("id"),
                "summary": event.get("summary"),
                "htmlLink": event.get("htmlLink")
            }
        
        @mcp.tool()
        def delete_event(
            event_id: str,
            calendar_id: str = "primary",
            send_notifications: bool = True
        ) -> dict:
            """
            Delete a calendar event.
            
            Args:
                event_id: Event ID to delete
                calendar_id: Calendar ID (default: "primary")
                send_notifications: Whether to send cancellation notifications
            
            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            success = client.delete_event(
                event_id=event_id,
                calendar_id=calendar_id,
                send_notifications=send_notifications
            )
            
            return {
                "success": success,
                "message": "Event deleted" if success else "Failed to delete event"
            }
        
        @mcp.tool()
        def update_calendar(
            calendar_id: str,
            summary: Optional[str] = None,
            description: Optional[str] = None,
            time_zone: Optional[str] = None,
            location: Optional[str] = None
        ) -> dict:
            """
            Update calendar settings.
            
            ⚠️ NOT WORKING: Requires additional OAuth scopes (insufficient permissions).
            
            Args:
                calendar_id: Calendar ID to update
                summary: New summary/title (optional)
                description: New description (optional)
                time_zone: New timezone (optional)
                location: New location (optional)
            
            Returns:
                Updated calendar information
            """
            client = tool_module._ensure_client()
            calendar = client.update_calendar(
                calendar_id=calendar_id,
                summary=summary,
                description=description,
                time_zone=time_zone,
                location=location
            )
            
            if not calendar:
                return {"success": False, "error": "Failed to update calendar"}
            
            return {
                "success": True,
                "id": calendar.get("id"),
                "summary": calendar.get("summary"),
                "description": calendar.get("description")
            }
    
    def register_resources(self, mcp: FastMCP) -> None:
        """Register Google Calendar resources (read operations) with MCP server."""
        tool_module = self
        
        @mcp.resource("google://calendars{?view}")
        def list_calendars_resource(view: Optional[str] = None) -> str:
            """
            List all calendars accessible by the user.
            
            ⚠️ NOT WORKING: Requires additional OAuth scopes (insufficient permissions).
            
            URI: google://calendars{?view}
            Optional query param: view - reserved for future use (e.g. filter)
            """
            client = tool_module._ensure_client()
            calendars = client.list_calendars()
            return json.dumps({
                "count": len(calendars),
                "calendars": calendars
            }, indent=2)
        
        @mcp.resource("google://calendar/{calendar_id}")
        def get_calendar_resource(calendar_id: str) -> str:
            """
            Get information about a specific calendar.
            
            ⚠️ NOT WORKING: Requires additional OAuth scopes (insufficient permissions).
            
            URI: google://calendar/{calendar_id}
            """
            client = tool_module._ensure_client()
            calendar = client.get_calendar(calendar_id)
            if not calendar:
                return json.dumps({"error": "Calendar not found"}, indent=2)
            return json.dumps(calendar, indent=2)
        
        @mcp.resource("google://calendar/{calendar_id}/events")
        def list_events_resource(calendar_id: str, time_min: Optional[str] = None, time_max: Optional[str] = None) -> str:
            """
            List events in a calendar.
            
            URI: google://calendar/{calendar_id}/events
            Optional query params: time_min, time_max (RFC3339 format)
            """
            client = tool_module._ensure_client()
            events = client.list_events(
                calendar_id=calendar_id,
                time_min=time_min,
                time_max=time_max,
                max_results=250
            )
            return json.dumps({
                "count": len(events),
                "calendar_id": calendar_id,
                "events": events
            }, indent=2)
        
        @mcp.resource("google://calendar/{calendar_id}/event/{event_id}")
        def get_event_resource(calendar_id: str, event_id: str) -> str:
            """
            Get information about a specific event.
            
            URI: google://calendar/{calendar_id}/event/{event_id}
            """
            client = tool_module._ensure_client()
            event = client.get_event(event_id, calendar_id)
            if not event:
                return json.dumps({"error": "Event not found"}, indent=2)
            return json.dumps(event, indent=2)


# Create module instance (required for registry pattern)
module = CalendarToolModule()
