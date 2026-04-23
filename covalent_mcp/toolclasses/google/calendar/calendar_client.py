"""
Google Calendar API Client - Wrapper for Calendar operations.

Provides methods for calendar and event operations, wrapping the CalendarService.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import pytz
import logging
import traceback

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
except ImportError:
    raise ImportError("Google API client not installed. Install with: pip install google-api-python-client")

from covalent_mcp.toolclasses.google.gauth import get_credentials_from_db


class CalendarService:
    """
    Google Calendar service wrapper.
    
    This wraps the user's CalendarService code and provides a clean interface.
    """
    
    def __init__(self, credentials: Optional[Credentials] = None):
        """
        Initialize Calendar service.
        
        Args:
            credentials: Google Credentials object. If not provided, reads from database.
        """
        if credentials is None:
            credentials = get_credentials_from_db()
        
        self.credentials = credentials
        self.service = build('calendar', 'v3', credentials=self.credentials)
    
    def list_calendars(self) -> List[Dict[str, Any]]:
        """
        Lists all calendars accessible by the user.
        
        Returns:
            list: List of calendar objects with their metadata
        """
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = []
            
            for calendar in calendar_list.get('items', []):
                if calendar.get('kind') == 'calendar#calendarListEntry':
                    calendars.append({
                        'id': calendar.get('id'),
                        'summary': calendar.get('summary'),
                        'primary': calendar.get('primary', False),
                        'time_zone': calendar.get('timeZone'),
                        'etag': calendar.get('etag'),
                        'access_role': calendar.get('accessRole')
                    })
            
            return calendars
        except Exception as e:
            logging.error(f"Error retrieving calendars: {str(e)}")
            logging.error(traceback.format_exc())
            return []
    
    def get_calendar(self, calendar_id: str = 'primary') -> Optional[Dict[str, Any]]:
        """
        Get information about a specific calendar.
        
        Args:
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            Calendar information dict or None
        """
        try:
            calendar = self.service.calendars().get(calendarId=calendar_id).execute()
            return {
                'id': calendar.get('id'),
                'summary': calendar.get('summary'),
                'description': calendar.get('description'),
                'time_zone': calendar.get('timeZone'),
                'location': calendar.get('location'),
                'etag': calendar.get('etag')
            }
        except Exception as e:
            logging.error(f"Error retrieving calendar {calendar_id}: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def list_events(
        self,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 250,
        show_deleted: bool = False,
        calendar_id: str = 'primary',
        updated_min: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve calendar events within a specified time range.
        
        Args:
            time_min: Start time in RFC3339 format. Defaults to current time.
            time_max: End time in RFC3339 format
            max_results: Maximum number of events to return (1-2500)
            show_deleted: Whether to include deleted events
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            list: List of calendar events
        """
        try:
            # If no time_min specified, use current time
            if not time_min:
                time_min = datetime.now(pytz.UTC).isoformat()
            
            # Ensure max_results is within limits
            max_results = min(max(1, max_results), 2500)
            
            # Prepare parameters
            params = {
                'calendarId': calendar_id,
                'timeMin': time_min,
                'maxResults': max_results,
                'singleEvents': True,
                'orderBy': 'startTime',
                'showDeleted': show_deleted
            }
            
            # Add optional time_max if specified
            if time_max:
                params['timeMax'] = time_max
            if updated_min:
                params['updatedMin'] = updated_min

            # Execute the events().list() method
            events_result = self.service.events().list(**params).execute()
            
            # Extract the events
            events = events_result.get('items', [])
            
            # Process and return the events
            processed_events = []
            for event in events:
                processed_event = {
                    'id': event.get('id'),
                    'summary': event.get('summary'),
                    'description': event.get('description'),
                    'start': event.get('start'),
                    'end': event.get('end'),
                    'updated': event.get('updated'),
                    'status': event.get('status'),
                    'creator': event.get('creator'),
                    'organizer': event.get('organizer'),
                    'attendees': event.get('attendees'),
                    'location': event.get('location'),
                    'hangoutLink': event.get('hangoutLink'),
                    'htmlLink': event.get('htmlLink'),
                    'conferenceData': event.get('conferenceData'),
                    'recurringEventId': event.get('recurringEventId')
                }
                processed_events.append(processed_event)
            
            return processed_events
        except Exception as e:
            logging.error(f"Error retrieving calendar events: {str(e)}")
            logging.error(traceback.format_exc())
            return []
    
    def get_event(self, event_id: str, calendar_id: str = 'primary') -> Optional[Dict[str, Any]]:
        """
        Get a specific event by ID.
        
        Args:
            event_id: Event ID
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            Event data dict or None
        """
        try:
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            return {
                'id': event.get('id'),
                'summary': event.get('summary'),
                'description': event.get('description'),
                'start': event.get('start'),
                'end': event.get('end'),
                'updated': event.get('updated'),
                'status': event.get('status'),
                'creator': event.get('creator'),
                'organizer': event.get('organizer'),
                'attendees': event.get('attendees'),
                'location': event.get('location'),
                'hangoutLink': event.get('hangoutLink'),
                'htmlLink': event.get('htmlLink'),
                'conferenceData': event.get('conferenceData'),
                'recurringEventId': event.get('recurringEventId')
            }
        except Exception as e:
            logging.error(f"Error retrieving event {event_id}: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        send_notifications: bool = True,
        timezone: Optional[str] = None,
        calendar_id: str = 'primary'
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new calendar event.
        
        Args:
            summary: Title of the event
            start_time: Start time in RFC3339 format
            end_time: End time in RFC3339 format
            location: Location of the event
            description: Description of the event
            attendees: List of attendee email addresses
            send_notifications: Whether to send notifications to attendees
            timezone: Timezone for the event (e.g. 'America/New_York')
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            dict: Created event data or None if creation fails
        """
        try:
            # Prepare event data
            event = {
                'summary': summary,
                'start': {
                    'dateTime': start_time,
                    'timeZone': timezone or 'UTC',
                },
                'end': {
                    'dateTime': end_time,
                    'timeZone': timezone or 'UTC',
                }
            }
            
            # Add optional fields if provided
            if location:
                event['location'] = location
            if description:
                event['description'] = description
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            # Create the event
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendNotifications=send_notifications
            ).execute()
            
            return created_event
        except Exception as e:
            logging.error(f"Error creating calendar event: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        location: Optional[str] = None,
        description: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        send_notifications: bool = True,
        timezone: Optional[str] = None,
        calendar_id: str = 'primary'
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing calendar event.
        
        Args:
            event_id: Event ID to update
            summary: New title (optional)
            start_time: New start time in RFC3339 format (optional)
            end_time: New end time in RFC3339 format (optional)
            location: New location (optional)
            description: New description (optional)
            attendees: New list of attendee emails (optional)
            send_notifications: Whether to send notifications
            timezone: Timezone for times (optional)
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            Updated event data or None if update fails
        """
        try:
            # Get existing event
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Update fields if provided
            if summary is not None:
                event['summary'] = summary
            if start_time is not None:
                event['start'] = {
                    'dateTime': start_time,
                    'timeZone': timezone or 'UTC',
                }
            if end_time is not None:
                event['end'] = {
                    'dateTime': end_time,
                    'timeZone': timezone or 'UTC',
                }
            if location is not None:
                event['location'] = location
            if description is not None:
                event['description'] = description
            if attendees is not None:
                event['attendees'] = [{'email': email} for email in attendees]
            
            # Update the event
            updated_event = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendNotifications=send_notifications
            ).execute()
            
            return updated_event
        except Exception as e:
            logging.error(f"Error updating calendar event {event_id}: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def delete_event(
        self,
        event_id: str,
        send_notifications: bool = True,
        calendar_id: str = 'primary'
    ) -> bool:
        """
        Delete a calendar event by its ID.
        
        Args:
            event_id: The ID of the event to delete
            send_notifications: Whether to send cancellation notifications to attendees
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendNotifications=send_notifications
            ).execute()
            return True
        except Exception as e:
            logging.error(f"Error deleting calendar event {event_id}: {str(e)}")
            logging.error(traceback.format_exc())
            return False
    
    def update_calendar(
        self,
        calendar_id: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        time_zone: Optional[str] = None,
        location: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update calendar settings.
        
        Args:
            calendar_id: Calendar ID to update
            summary: New summary/title (optional)
            description: New description (optional)
            time_zone: New timezone (optional)
            location: New location (optional)
        
        Returns:
            Updated calendar data or None if update fails
        """
        try:
            # Get existing calendar
            calendar = self.service.calendars().get(calendarId=calendar_id).execute()
            
            # Update fields if provided
            if summary is not None:
                calendar['summary'] = summary
            if description is not None:
                calendar['description'] = description
            if time_zone is not None:
                calendar['timeZone'] = time_zone
            if location is not None:
                calendar['location'] = location
            
            # Update the calendar
            updated_calendar = self.service.calendars().patch(
                calendarId=calendar_id,
                body=calendar
            ).execute()
            
            return {
                'id': updated_calendar.get('id'),
                'summary': updated_calendar.get('summary'),
                'description': updated_calendar.get('description'),
                'time_zone': updated_calendar.get('timeZone'),
                'location': updated_calendar.get('location')
            }
        except Exception as e:
            logging.error(f"Error updating calendar {calendar_id}: {str(e)}")
            logging.error(traceback.format_exc())
            return None
