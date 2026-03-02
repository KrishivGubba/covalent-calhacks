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
_info_call_count = 0
import sys as _sys
_dbg_proc = {"pid": os.getpid(), "exe": os.path.basename(_sys.executable)}


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
        if api_key:
            try:
                from posthog import Posthog
                _posthog = Posthog(
                    project_api_key=api_key,
                    host='https://us.i.posthog.com',
                )
            except (ImportError, Exception) as _e:
                pass
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
        if self._posthog is None:
            return
        props = dict(properties) if properties else {}
        did = self._user_id or "anonymous"
        try:
            self._posthog.capture(
                event,
                distinct_id=did,
                properties=props,
            )
            self._posthog.flush()
        except Exception as _e:
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
