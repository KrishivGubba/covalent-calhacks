"""
Test script for Google Calendar MCP tools.

Token is read from the database (integration_tokens table) - no auth flow needed.
Server handles OAuth via /integrations/google/auth endpoint.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add project root to path
# test_script.py is in: covalent_mcp/toolclasses/google/calendar/
covalent_mcp_dir = Path(__file__).parent.parent.parent.parent  # Gets to covalent_mcp/
project_root = covalent_mcp_dir.parent  # Gets to project root
sys.path.insert(0, str(project_root))

from covalent_mcp.toolclasses.google.calendar.calendar_client import CalendarService


# Initialize client - reads token from database automatically
client = CalendarService()


def test_list_calendars():
    """Test: List all calendars (read-only, safe)."""
    print("=" * 60)
    print("📅 TEST: List Calendars (Resource)")
    print("=" * 60)
    
    calendars = client.list_calendars()
    print(f"Found {len(calendars)} calendars\n")
    
    for i, cal in enumerate(calendars, 1):
        print(f"{i}. {cal['summary']}")
        print(f"   ID: {cal['id']}")
        print(f"   Primary: {cal.get('primary', False)}")
        print(f"   Timezone: {cal.get('time_zone', 'N/A')}")
        print()
    
    return calendars


def test_get_calendar(calendar_id: str = "primary"):
    """Test: Get info about a specific calendar (read-only, safe)."""
    print("=" * 60)
    print(f"📂 TEST: Get Calendar Info (Resource) - {calendar_id}")
    print("=" * 60)
    
    calendar = client.get_calendar(calendar_id)
    if not calendar:
        print("❌ Calendar not found")
        return None
    
    print(f"Calendar: {calendar.get('summary', 'N/A')}")
    print(f"ID: {calendar.get('id')}")
    print(f"Timezone: {calendar.get('time_zone', 'N/A')}")
    if calendar.get('description'):
        print(f"Description: {calendar['description']}")
    if calendar.get('location'):
        print(f"Location: {calendar['location']}")
    print()
    
    return calendar


def test_list_events(calendar_id: str = "primary", days_ahead: int = 7):
    """Test: List events (read-only, safe)."""
    print("=" * 60)
    print(f"📆 TEST: List Events (Resource) - {calendar_id}")
    print("=" * 60)
    
    # Get events for next N days
    time_min = datetime.now(pytz.UTC).isoformat()
    time_max = (datetime.now(pytz.UTC) + timedelta(days=days_ahead)).isoformat()
    
    events = client.list_events(
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        max_results=50
    )
    
    print(f"Found {len(events)} events in next {days_ahead} days\n")
    
    for i, event in enumerate(events[:10], 1):  # Show first 10
        print(f"{i}. {event.get('summary', 'No title')}")
        start = event.get('start', {})
        if 'dateTime' in start:
            print(f"   Start: {start['dateTime']}")
        elif 'date' in start:
            print(f"   Start: {start['date']} (all day)")
        if event.get('location'):
            print(f"   Location: {event['location']}")
        print()
    
    return events


def test_get_event(event_id: str, calendar_id: str = "primary"):
    """Test: Get event details (read-only, safe)."""
    print("=" * 60)
    print(f"🔍 TEST: Get Event Details (Resource) - {event_id}")
    print("=" * 60)
    
    event = client.get_event(event_id, calendar_id)
    if not event:
        print("❌ Event not found")
        return None
    
    print(f"Event: {event.get('summary', 'No title')}")
    print(f"ID: {event.get('id')}")
    start = event.get('start', {})
    end = event.get('end', {})
    if 'dateTime' in start:
        print(f"Start: {start['dateTime']}")
        print(f"End: {end.get('dateTime', 'N/A')}")
    if event.get('description'):
        print(f"Description: {event['description']}")
    if event.get('location'):
        print(f"Location: {event['location']}")
    print()
    
    return event


def test_create_event(
    summary: str,
    start_time: str,
    end_time: str,
    calendar_id: str = "primary",
    location: str = None,
    description: str = None
):
    """Test: Create an event (creates real event!)."""
    print("=" * 60)
    print(f"➕ TEST: Create Event - {summary}")
    print("=" * 60)
    
    event = client.create_event(
        summary=summary,
        start_time=start_time,
        end_time=end_time,
        calendar_id=calendar_id,
        location=location,
        description=description
    )
    
    if not event:
        print("❌ Failed to create event")
        return None
    
    print(f"✅ Created event: {event.get('htmlLink', 'N/A')}")
    print(f"   ID: {event.get('id')}")
    print(f"   Summary: {event.get('summary')}")
    print()
    
    return event


def test_update_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: str = None,
    description: str = None
):
    """Test: Update an event (updates real event!)."""
    print("=" * 60)
    print(f"✏️  TEST: Update Event - {event_id}")
    print("=" * 60)
    
    event = client.update_event(
        event_id=event_id,
        calendar_id=calendar_id,
        summary=summary,
        description=description
    )
    
    if not event:
        print("❌ Failed to update event")
        return None
    
    print(f"✅ Updated event: {event.get('htmlLink', 'N/A')}")
    print(f"   Summary: {event.get('summary')}")
    print()
    
    return event


def test_delete_event(event_id: str, calendar_id: str = "primary"):
    """Test: Delete an event (deletes real event!)."""
    print("=" * 60)
    print(f"🗑️  TEST: Delete Event - {event_id}")
    print("=" * 60)
    
    success = client.delete_event(event_id, calendar_id)
    
    if success:
        print(f"✅ Deleted event: {event_id}")
    else:
        print(f"❌ Failed to delete event: {event_id}")
    print()
    
    return success


def test_update_calendar(calendar_id: str, description: str = None):
    """Test: Update calendar settings."""
    print("=" * 60)
    print(f"⚙️  TEST: Update Calendar - {calendar_id}")
    print("=" * 60)
    
    calendar = client.update_calendar(
        calendar_id=calendar_id,
        description=description
    )
    
    if not calendar:
        print("❌ Failed to update calendar")
        return None
    
    print(f"✅ Updated calendar: {calendar.get('summary', calendar_id)}")
    if calendar.get('description'):
        print(f"   Description: {calendar['description']}")
    print()
    
    return calendar


# ============================================================================
# TEST FLOW - Sequential workflow using the same calendar
# ============================================================================

if __name__ == "__main__":
    # Calendar to use for testing (default: primary)
    TEST_CALENDAR_ID = "primary"
    
    print("\n" + "=" * 60)
    print("🚀 GOOGLE CALENDAR MCP TOOLS - TEST FLOW")
    print("=" * 60 + "\n")
    
    try:
        # Step 1: List calendars (Resource)
        print("STEP 1: Listing calendars...\n")
        calendars = test_list_calendars()
        
        # Step 2: Get calendar info (Resource)
        print("STEP 2: Getting calendar info...\n")
        calendar_info = test_get_calendar(TEST_CALENDAR_ID)
        
        # Step 3: List existing events (Resource)
        print("STEP 3: Listing existing events...\n")
        existing_events = test_list_events(TEST_CALENDAR_ID, days_ahead=7)
        
        # Step 4: Create a test event
        print("STEP 4: Creating a test event...\n")
        # Create event 1 hour from now, 30 minutes long
        now = datetime.now(pytz.UTC)
        start_time = (now + timedelta(hours=1)).isoformat()
        end_time = (now + timedelta(hours=1, minutes=30)).isoformat()
        
        test_event = test_create_event(
            summary="MCP Test Event",
            start_time=start_time,
            end_time=end_time,
            calendar_id=TEST_CALENDAR_ID,
            location="Test Location",
            description="This is a test event created via MCP tools"
        )
        
        if not test_event:
            print("❌ Failed to create test event. Stopping flow.")
            exit(1)
        
        test_event_id = test_event['id']
        
        # Step 5: Get the event we just created (Resource)
        print("STEP 5: Getting the event we just created...\n")
        test_get_event(test_event_id, TEST_CALENDAR_ID)
        
        # Step 6: Update the event
        print("STEP 6: Updating the event...\n")
        test_update_event(
            event_id=test_event_id,
            calendar_id=TEST_CALENDAR_ID,
            summary="MCP Test Event - Updated",
            description="This event was updated via MCP tools"
        )
        
        # Step 7: Update calendar description
        print("STEP 7: Updating calendar description...\n")
        test_update_calendar(
            calendar_id=TEST_CALENDAR_ID,
            description="Updated via MCP tools"
        )
        
        # Step 8: List events again to see our new event
        print("STEP 8: Listing events again...\n")
        test_list_events(TEST_CALENDAR_ID, days_ahead=7)
        
        # Step 9: Optional - Delete the test event (commented out by default)
        # Uncomment if you want to clean up
        # print("STEP 9: Deleting test event...\n")
        # test_delete_event(test_event_id, TEST_CALENDAR_ID)
        
        print("\n" + "=" * 60)
        print("✅ TEST FLOW COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📅 Test event created in calendar: {TEST_CALENDAR_ID}")
        if test_event.get('htmlLink'):
            print(f"   Event URL: {test_event['htmlLink']}")
        print("   You can check it out on Google Calendar!\n")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FLOW FAILED")
        print("=" * 60)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
