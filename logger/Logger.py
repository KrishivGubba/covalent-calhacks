"""
Unified Logger for Covalent.

- Console output: timestamped lines to stderr (captured by flask_server.log shell redirect)
- PostHog analytics: action_success, action_failure, authentication, integration
"""
import os
import logging
from typing import Optional

_posthog = None
_logging_configured = False


def _configure_logging() -> None:
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s]: %(message)s',
        datefmt='%H:%M:%S',
    )

    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.DEBUG)


_configure_logging()


def _get_posthog():
    global _posthog
    if _posthog is None:
        api_key = os.getenv("POSTHOG_API_KEY")
        # region agent log
        import json as _json, time as _time
        try:
            with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-7edf12.log', 'a') as _f:
                _f.write(_json.dumps({"sessionId":"7edf12","id":"get_posthog_entry","timestamp":int(_time.time()*1000),"location":"Logger.py:_get_posthog","message":"_get_posthog called","data":{"api_key_present":bool(api_key),"api_key_prefix":api_key[:8] if api_key else None},"hypothesisId":"H1,H2,H3"}) + '\n')
        except: pass
        # endregion
        if api_key:
            try:
                from posthog import Posthog
                _posthog = Posthog(
                    api_key=api_key
                    host='https://us.i.posthog.com'
                    )
                # region agent log
                try:
                    with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-7edf12.log', 'a') as _f:
                        _f.write(_json.dumps({"sessionId":"7edf12","id":"posthog_import_ok","timestamp":int(_time.time()*1000),"location":"Logger.py:_get_posthog","message":"posthog imported and initialized successfully","data":{},"hypothesisId":"H1"}) + '\n')
                except: pass
                # endregion
            except ImportError as _e:
                # region agent log
                try:
                    with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-7edf12.log', 'a') as _f:
                        _f.write(_json.dumps({"sessionId":"7edf12","id":"posthog_import_error","timestamp":int(_time.time()*1000),"location":"Logger.py:_get_posthog","message":"posthog ImportError - package not installed","data":{"error":str(_e)},"hypothesisId":"H1,H5"}) + '\n')
                except: pass
                # endregion
    return _posthog



# Custom wrapper that routes between posthog and standard logging (stderr)
class Logger:
    def __init__(self, user_id: Optional[str] = None):
        self._user_id = user_id
        self._posthog = _get_posthog()
        # Log if posthog is configured
        if self._posthog is not None:
            print("Posthog configured")
        else:
            print("Posthog not configured")
        self._logger = logging.getLogger('covalent')

    def set_user_id(self, user_id: Optional[str]) -> None:
        """Set the current user ID for analytics (from user_sessions after login)."""
        self._user_id = user_id

    def _capture(self, event: str, properties: Optional[dict] = None) -> None:
        # region agent log
        import json as _json, time as _time
        try:
            with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-7edf12.log', 'a') as _f:
                _f.write(_json.dumps({"sessionId":"7edf12","id":"capture_called","timestamp":int(_time.time()*1000),"location":"Logger.py:_capture","message":"_capture called","data":{"event":event,"posthog_is_none":self._posthog is None,"user_id":self._user_id},"hypothesisId":"H3,H4"}) + '\n')
        except: pass
        # endregion
        if self._posthog is None:
            return
        props = dict(properties) if properties else {}
        if self._user_id:
            props["distinct_id"] = self._user_id
        try:
            self._posthog.capture(
                event,
                distinct_id=self._user_id,
                properties=props,
            )
        except Exception as _e:
            # region agent log
            try:
                with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-7edf12.log', 'a') as _f:
                    _f.write(_json.dumps({"sessionId":"7edf12","id":"capture_exception","timestamp":int(_time.time()*1000),"location":"Logger.py:_capture","message":"posthog capture threw exception","data":{"event":event,"error":str(_e),"error_type":type(_e).__name__},"hypothesisId":"H3,H4"}) + '\n')
            except: pass
            # endregion
            print("Error capturing event in posthog")

    def info(self, msg: str) -> None:
        self._logger.info(msg)

    def debug(self, msg: str) -> None:
        self._logger.debug(msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)

    def error(self, msg: str) -> None:
        self._logger.error(msg)

    def action_success(self, event: str, properties: dict) -> None:
        self._capture("Action Success", {**properties, "event": event})

    def action_failure(self, event: str, properties: dict) -> None:
        self._capture("Action Failure", {**properties, "event": event})

    def authentication(self, event: str, properties: dict) -> None:
        self._capture("User Authentication", {**properties, "event": event})

    def integration(self, event: str, properties: dict) -> None:
        self._capture("Integration", {**properties, "event": event})


_logger: Optional[Logger] = None


def get_logger() -> Logger:
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger
