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
        # region agent log
        import json as _json, time as _time, atexit as _atexit
        try:
            with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                _f.write(_json.dumps({"sessionId":"d01c5b","id":"get_posthog_entry","timestamp":int(_time.time()*1000),"location":"Logger.py:_get_posthog","message":"_get_posthog called","data":{"build":"v4",**_dbg_proc,"api_key_present":bool(api_key),"api_key_prefix":api_key[:8] if api_key else None},"hypothesisId":"H6"}) + '\n')
        except: pass
        def _dbg_atexit():
            try:
                with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                    _f.write(_json.dumps({"sessionId":"d01c5b","id":"process_exit","timestamp":int(_time.time()*1000),"location":"Logger.py:atexit","message":"process exiting","data":{"build":"v4",**_dbg_proc},"hypothesisId":"H6"}) + '\n')
            except: pass
        _atexit.register(_dbg_atexit)
        # endregion
        if api_key:
            try:
                from posthog import Posthog
                _posthog = Posthog(
                    project_api_key=api_key,
                    host='https://us.i.posthog.com',
                )
                # region agent log
                try:
                    with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                        _f.write(_json.dumps({"sessionId":"d01c5b","id":"posthog_import_ok","timestamp":int(_time.time()*1000),"location":"Logger.py:_get_posthog","message":"posthog imported and initialized successfully","data":{**_dbg_proc},"hypothesisId":"H6"}) + '\n')
                except: pass
                # endregion
            except (ImportError, Exception) as _e:
                # region agent log
                try:
                    with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                        _f.write(_json.dumps({"sessionId":"d01c5b","id":"posthog_import_error","timestamp":int(_time.time()*1000),"location":"Logger.py:_get_posthog","message":"posthog init failed","data":{**_dbg_proc,"error":str(_e),"error_type":type(_e).__name__},"hypothesisId":"H6"}) + '\n')
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
            with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                _f.write(_json.dumps({"sessionId":"d01c5b","id":"capture_called","timestamp":int(_time.time()*1000),"location":"Logger.py:_capture","message":"_capture called","data":{**_dbg_proc,"event":event,"posthog_is_none":self._posthog is None,"user_id":self._user_id},"hypothesisId":"H6"}) + '\n')
        except: pass
        # endregion
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
            # region agent log
            try:
                with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                    _f.write(_json.dumps({"sessionId":"d01c5b","id":"capture_success","timestamp":int(_time.time()*1000),"location":"Logger.py:_capture","message":"posthog capture+flush succeeded","data":{**_dbg_proc,"event":event,"distinct_id":did},"hypothesisId":"H6"}) + '\n')
            except: pass
            # endregion
        except Exception as _e:
            # region agent log
            try:
                with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                    _f.write(_json.dumps({"sessionId":"d01c5b","id":"capture_exception","timestamp":int(_time.time()*1000),"location":"Logger.py:_capture","message":"posthog capture threw exception","data":{**_dbg_proc,"event":event,"error":str(_e),"error_type":type(_e).__name__},"hypothesisId":"H6"}) + '\n')
            except: pass
            # endregion
            print("Error capturing event in posthog")

    def info(self, msg: str) -> None:
        # region agent log
        global _info_call_count
        _info_call_count += 1
        import json as _json, time as _time
        if _info_call_count <= 3 or '\U0001f510' in msg:
            try:
                with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                    _f.write(_json.dumps({"sessionId":"d01c5b","id":"info_call","timestamp":int(_time.time()*1000),"location":"Logger.py:info","message":"log.info called","data":{**_dbg_proc,"msg":msg[:120],"call_count":_info_call_count},"hypothesisId":"H6"}) + '\n')
            except: pass
        # endregion
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
        # region agent log
        import json as _json, time as _time
        try:
            with open('/Users/Patron/Desktop/covalent-calhacks/.cursor/debug-d01c5b.log', 'a') as _f:
                _f.write(_json.dumps({"sessionId":"d01c5b","id":"authentication_called","timestamp":int(_time.time()*1000),"location":"Logger.py:authentication","message":"log.authentication called","data":{**_dbg_proc,"event":event,"props_keys":list(properties.keys()) if properties else None},"hypothesisId":"H6"}) + '\n')
        except: pass
        # endregion
        self._capture("User Authentication", {**properties, "event": event})

    def integration(self, event: str, properties: dict) -> None:
        self._capture("Integration", {**properties, "event": event})


_logger: Optional[Logger] = None


def get_logger() -> Logger:
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger
