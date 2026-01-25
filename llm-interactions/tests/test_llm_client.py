import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from uuid import uuid4
import importlib.util


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LLM_CLIENT_PATH = PROJECT_ROOT / "llm-interactions" / "llm_client.py"


def _ensure_stub_dotenv():
    """Provide a minimal 'dotenv' module so importing llm_client works in minimal envs."""
    if "dotenv" in sys.modules:
        return
    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *args, **kwargs: None  # noqa: E731
    sys.modules["dotenv"] = dotenv_mod


def _install_fake_openai_module(response_text: str = "ok-openai"):
    """Install a fake 'openai' module that matches llm_client's expectations."""
    openai_mod = types.ModuleType("openai")

    class _RespMsg:
        def __init__(self, content: str):
            self.content = content

    class _Choice:
        def __init__(self, content: str):
            self.message = _RespMsg(content)

    class _Resp:
        def __init__(self, content: str):
            self.choices = [_Choice(content)]

    class _Completions:
        @staticmethod
        def create(**kwargs):
            return _Resp(response_text)

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class OpenAI:
        def __init__(self, api_key=None, **kwargs):
            self.api_key = api_key
            self.chat = _Chat()

    openai_mod.OpenAI = OpenAI
    sys.modules["openai"] = openai_mod


def _install_fake_anthropic_module(response_text: str = "ok-anthropic"):
    """Install a fake 'anthropic' module that matches llm_client's expectations."""
    anthropic_mod = types.ModuleType("anthropic")

    class _Block:
        def __init__(self, text: str):
            self.text = text

    class _Resp:
        def __init__(self, text: str):
            self.content = [_Block(text)]

    class _Messages:
        @staticmethod
        def create(**kwargs):
            return _Resp(response_text)

    class Anthropic:
        def __init__(self, api_key=None, **kwargs):
            self.api_key = api_key
            self.messages = _Messages()

    anthropic_mod.Anthropic = Anthropic
    sys.modules["anthropic"] = anthropic_mod


def load_llm_client_module_fresh():
    """
    Load llm_client.py as a fresh, isolated module so global caches don't leak across tests.
    """
    _ensure_stub_dotenv()
    module_name = f"_llm_client_test_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, LLM_CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # Reset provider caches in module under test (defensive)
    if hasattr(module, "_openai_client"):
        module._openai_client = None
    if hasattr(module, "_anthropic_client"):
        module._anthropic_client = None
    return module


class TestLLMClientConfig(unittest.TestCase):
    def test_missing_config_file_raises(self):
        module = load_llm_client_module_fresh()
        LLMClient = module.LLMClient
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does_not_exist.json"
            with self.assertRaises(FileNotFoundError):
                LLMClient(config_path=str(missing))

    def test_invalid_json_raises(self):
        module = load_llm_client_module_fresh()
        LLMClient = module.LLMClient
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "llm_config.json"
            cfg.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(ValueError):
                LLMClient(config_path=str(cfg))

    def test_missing_provider_key_raises(self):
        module = load_llm_client_module_fresh()
        LLMClient = module.LLMClient
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "llm_config.json"
            cfg.write_text(json.dumps({"openai": {"model": "gpt-4-turbo"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                LLMClient(config_path=str(cfg))

    def test_unsupported_provider_raises(self):
        module = load_llm_client_module_fresh()
        LLMClient = module.LLMClient
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "llm_config.json"
            cfg.write_text(json.dumps({"provider": "foo"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                LLMClient(config_path=str(cfg))


class TestLLMClientRouting(unittest.TestCase):
    def setUp(self):
        # Ensure we don't accidentally use real SDKs
        sys.modules.pop("openai", None)
        sys.modules.pop("anthropic", None)

    def test_openai_routing_calls_openai_sdk(self):
        _install_fake_openai_module(response_text="hello-from-openai")
        module = load_llm_client_module_fresh()
        LLMClient = module.LLMClient

        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "llm_config.json"
            cfg.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "openai": {"model": "gpt-4-turbo", "api_key_env": "OPENAI_API_KEY"},
                        "defaults": {"max_tokens": 50, "temperature": 0.0},
                    }
                ),
                encoding="utf-8",
            )
            os.environ["OPENAI_API_KEY"] = "test-key"
            client = LLMClient(config_path=str(cfg))
            out = client.generate("hi", system_prompt="be nice")
            self.assertEqual(out, "hello-from-openai")

    def test_anthropic_routing_calls_anthropic_sdk(self):
        _install_fake_anthropic_module(response_text="hello-from-anthropic")
        module = load_llm_client_module_fresh()
        LLMClient = module.LLMClient

        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "llm_config.json"
            cfg.write_text(
                json.dumps(
                    {
                        "provider": "anthropic",
                        "anthropic": {"model": "claude-sonnet", "api_key_env": "ANTHROPIC_API_KEY"},
                        "defaults": {"max_tokens": 50, "temperature": 0.0},
                    }
                ),
                encoding="utf-8",
            )
            os.environ["ANTHROPIC_API_KEY"] = "test-key"
            client = LLMClient(config_path=str(cfg))
            out = client.generate("hi", system_prompt="be nice")
            self.assertEqual(out, "hello-from-anthropic")

