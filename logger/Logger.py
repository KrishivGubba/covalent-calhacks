"""
Unified Logger for Covalent.

- Console output: timestamped lines to stderr
- File output: rotating log files in the Covalent data directory
- PostHog analytics: action_success, action_failure, authentication, integration
"""
import os
import platform
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

_posthog = None
_logging_configured = False
_info_call_count = 0
import sys as _sys
_dbg_proc = {"pid": os.getpid(), "exe": os.path.basename(_sys.executable)}


def _get_log_dir() -> str:
    data_dir = os.environ.get('COVALENT_DATA_DIR')
    if not data_dir:
        if platform.system() == 'Darwin':
            data_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Covalent")
        else:
            data_dir = os.path.join(os.path.expanduser("~"), ".covalent")
    return os.path.join(data_dir, "logs")


def _configure_logging() -> None:
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    console_fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s]: %(message)s',
        datefmt='%H:%M:%S',
    )
    file_fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_fmt)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(console_handler)

    try:
        log_dir = _get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "covalent.log"),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
        )
        file_handler.setFormatter(file_fmt)
        file_handler.setLevel(logging.INFO)
        root.addHandler(file_handler)
    except OSError:
        pass

    root.setLevel(logging.INFO)


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
