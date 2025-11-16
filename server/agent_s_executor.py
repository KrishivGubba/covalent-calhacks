"""
Agent-S Executor Service

This module provides a clean interface for executing actions using Agent-S-fork.
It wraps the Agent-S SDK and handles initialization, execution, and cleanup.
"""

import io
import os
import sys
import time
import logging
from typing import Dict, Optional, Tuple
from PIL import Image
import pyautogui

# Add Agent-S-fork to Python path
AGENT_S_PATH = os.path.join(os.path.dirname(__file__), '..', 'Agent-S-fork')
if os.path.exists(AGENT_S_PATH):
    sys.path.insert(0, AGENT_S_PATH)

from gui_agents.s3.agents.agent_s import AgentS3
from gui_agents.s3.agents.grounding import OSWorldACI
from gui_agents.s3.utils.local_env import LocalEnv

logger = logging.getLogger(__name__)


class AgentSExecutor:
    """
    Executor for Agent-S actions.
    
    This class initializes Agent-S with proper configuration and provides
    a simple interface for executing actions on the user's computer.
    """
    
    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-5-2025-08-07",
        model_url: str = "",
        model_api_key: str = "",
        model_temperature: Optional[float] = None,
        ground_provider: str = "huggingface",
        ground_url: str = "http://localhost:8080",
        ground_api_key: str = "",
        ground_model: str = "ui-tars-1.5-7b",
        grounding_width: int = 1920,
        grounding_height: int = 1080,
        max_trajectory_length: int = 8,
        enable_reflection: bool = True,
        enable_local_env: bool = False,
        platform: str = "darwin",
    ):
        """
        Initialize the Agent-S executor.
        
        Args:
            provider: LLM provider (openai, anthropic, etc.)
            model: Model name (e.g., gpt-5-2025-08-07)
            model_url: Custom API URL (optional)
            model_api_key: API key for main model (optional, uses env var if not provided)
            model_temperature: Temperature for model (optional)
            ground_provider: Provider for grounding model
            ground_url: URL for grounding model endpoint
            ground_api_key: API key for grounding model (optional)
            ground_model: Name of grounding model
            grounding_width: Width of grounding coordinate space (1920 for UI-TARS-1.5-7B)
            grounding_height: Height of grounding coordinate space (1080 for UI-TARS-1.5-7B)
            max_trajectory_length: Maximum number of image turns to keep in memory
            enable_reflection: Whether to enable reflection agent
            enable_local_env: Whether to enable local code execution (WARNING: security risk)
            platform: Platform name (darwin, linux, windows)
        """
        self.provider = provider
        self.model = model
        self.platform = platform
        self.max_trajectory_length = max_trajectory_length
        self.enable_reflection = enable_reflection
        self.enable_local_env = enable_local_env
        
        # Get screen dimensions
        self.screen_width, self.screen_height = pyautogui.size()
        
        # Scale dimensions if needed (for UI-TARS context limit)
        self.scaled_width, self.scaled_height = self._scale_screen_dimensions(
            self.screen_width, self.screen_height, max_dim_size=2400
        )
        
        # Engine params for main LLM
        self.engine_params = {
            "engine_type": provider,
            "model": model,
            "base_url": model_url if model_url else None,
            "api_key": model_api_key if model_api_key else None,
            "temperature": model_temperature,
        }
        
        # Engine params for grounding model
        self.engine_params_for_grounding = {
            "engine_type": ground_provider,
            "model": ground_model,
            "base_url": ground_url,
            "api_key": ground_api_key if ground_api_key else None,
            "grounding_width": grounding_width,
            "grounding_height": grounding_height,
        }
        
        # Initialize local environment if enabled
        self.local_env = None
        if enable_local_env:
            logger.warning("⚠️  Local coding environment ENABLED - Agent can execute arbitrary code!")
            self.local_env = LocalEnv()
        
        # Initialize agent (lazy loading - only when needed)
        self._agent = None
        self._grounding_agent = None
    
    def _scale_screen_dimensions(self, width: int, height: int, max_dim_size: int) -> Tuple[int, int]:
        """Scale screen dimensions to fit within max size while maintaining aspect ratio."""
        scale_factor = min(max_dim_size / width, max_dim_size / height, 1)
        safe_width = int(width * scale_factor)
        safe_height = int(height * scale_factor)
        return safe_width, safe_height
    
    def _initialize_agent(self):
        """Initialize Agent-S components (lazy loading)."""
        if self._agent is not None:
            return
        
        logger.info("🤖 Initializing Agent-S...")
        
        # Create grounding agent
        self._grounding_agent = OSWorldACI(
            env=self.local_env,
            platform=self.platform,
            engine_params_for_generation=self.engine_params,
            engine_params_for_grounding=self.engine_params_for_grounding,
            width=self.screen_width,
            height=self.screen_height,
        )
        
        # Create main agent
        self._agent = AgentS3(
            self.engine_params,
            self._grounding_agent,
            platform=self.platform,
            max_trajectory_length=self.max_trajectory_length,
            enable_reflection=self.enable_reflection,
        )
        
        logger.info("✅ Agent-S initialized successfully")
    
    def _get_screenshot(self) -> bytes:
        """Capture and return screenshot as bytes."""
        screenshot = pyautogui.screenshot()
        screenshot = screenshot.resize((self.scaled_width, self.scaled_height), Image.LANCZOS)
        
        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        return buffered.getvalue()
    
    def execute_action(
        self,
        instruction: str,
        max_steps: int = 15,
        step_delay: float = 1.0
    ) -> Dict[str, any]:
        """
        Execute an action using Agent-S.
        
        Args:
            instruction: Natural language instruction for what to do
            max_steps: Maximum number of steps to execute (default: 15)
            step_delay: Delay between steps in seconds (default: 1.0)
        
        Returns:
            Dict with execution results:
            {
                "success": bool,
                "steps_taken": int,
                "completion_status": str,  # "done", "failed", "max_steps"
                "error": str or None,
                "logs": List[str]
            }
        """
        try:
            # Initialize agent if not already done
            self._initialize_agent()
            
            # Reset agent for new task
            self._agent.reset()
            
            logger.info(f"🎬 Executing action: {instruction}")
            
            execution_logs = []
            obs = {}
            
            for step in range(max_steps):
                try:
                    # Capture screenshot
                    screenshot_bytes = self._get_screenshot()
                    obs["screenshot"] = screenshot_bytes
                    
                    logger.info(f"🔄 Step {step + 1}/{max_steps}: Getting next action from agent...")
                    execution_logs.append(f"Step {step + 1}: Getting next action...")
                    
                    # Get next action from agent
                    info, code = self._agent.predict(instruction=instruction, observation=obs)
                    
                    # Check for completion
                    if "done" in code[0].lower():
                        logger.info(f"✅ Task completed successfully in {step + 1} steps")
                        execution_logs.append(f"Step {step + 1}: Task completed!")
                        return {
                            "success": True,
                            "steps_taken": step + 1,
                            "completion_status": "done",
                            "error": None,
                            "logs": execution_logs
                        }
                    
                    if "fail" in code[0].lower():
                        logger.warning(f"❌ Agent reported failure at step {step + 1}")
                        execution_logs.append(f"Step {step + 1}: Agent reported failure")
                        return {
                            "success": False,
                            "steps_taken": step + 1,
                            "completion_status": "failed",
                            "error": "Agent reported task failure",
                            "logs": execution_logs
                        }
                    
                    # Handle special commands
                    if "next" in code[0].lower():
                        execution_logs.append(f"Step {step + 1}: Skipping to next step")
                        continue
                    
                    if "wait" in code[0].lower():
                        logger.info("⏳ Agent requested wait...")
                        execution_logs.append(f"Step {step + 1}: Waiting...")
                        time.sleep(5)
                        continue
                    
                    # Execute the code
                    logger.info(f"⚡ Executing: {code[0][:100]}...")
                    execution_logs.append(f"Step {step + 1}: Executing action")
                    
                    time.sleep(step_delay)
                    exec(code[0])
                    time.sleep(step_delay)
                    
                except Exception as e:
                    logger.error(f"❌ Error at step {step + 1}: {e}")
                    execution_logs.append(f"Step {step + 1}: Error - {str(e)}")
                    return {
                        "success": False,
                        "steps_taken": step + 1,
                        "completion_status": "error",
                        "error": str(e),
                        "logs": execution_logs
                    }
            
            # Max steps reached without completion
            logger.warning(f"⚠️ Max steps ({max_steps}) reached without completion")
            execution_logs.append(f"Max steps ({max_steps}) reached")
            return {
                "success": False,
                "steps_taken": max_steps,
                "completion_status": "max_steps",
                "error": f"Task did not complete within {max_steps} steps",
                "logs": execution_logs
            }
        
        except Exception as e:
            logger.error(f"❌ Fatal error during execution: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "steps_taken": 0,
                "completion_status": "error",
                "error": str(e),
                "logs": [f"Fatal error: {str(e)}"]
            }


def create_executor_from_env() -> AgentSExecutor:
    """
    Create an AgentSExecutor instance from environment variables.
    
    Environment variables:
        AGENT_S_PROVIDER: LLM provider (default: openai)
        AGENT_S_MODEL: Model name (default: gpt-5-2025-08-07)
        AGENT_S_MODEL_URL: Custom API URL (optional)
        AGENT_S_MODEL_API_KEY: API key (optional)
        AGENT_S_MODEL_TEMPERATURE: Temperature (optional)
        AGENT_S_GROUNDING_PROVIDER: Grounding provider (default: huggingface)
        AGENT_S_GROUNDING_URL: Grounding URL (default: http://localhost:8080)
        AGENT_S_GROUNDING_API_KEY: Grounding API key (optional)
        AGENT_S_GROUNDING_MODEL: Grounding model (default: ui-tars-1.5-7b)
        AGENT_S_GROUNDING_WIDTH: Coordinate width (default: 1920)
        AGENT_S_GROUNDING_HEIGHT: Coordinate height (default: 1080)
        AGENT_S_MAX_TRAJECTORY_LENGTH: Max trajectory (default: 8)
        AGENT_S_ENABLE_REFLECTION: Enable reflection (default: true)
        AGENT_S_ENABLE_LOCAL_ENV: Enable local env (default: false)
        AGENT_S_PLATFORM: Platform (default: darwin)
    """
    import platform as platform_module
    
    # Detect platform
    platform_map = {
        "Darwin": "darwin",
        "Linux": "linux",
        "Windows": "windows"
    }
    default_platform = platform_map.get(platform_module.system(), "darwin")
    
    return AgentSExecutor(
        provider=os.getenv("AGENT_S_PROVIDER", "openai"),
        model=os.getenv("AGENT_S_MODEL", "gpt-5-2025-08-07"),
        model_url=os.getenv("AGENT_S_MODEL_URL", ""),
        model_api_key=os.getenv("AGENT_S_MODEL_API_KEY", ""),
        model_temperature=float(os.getenv("AGENT_S_MODEL_TEMPERATURE")) if os.getenv("AGENT_S_MODEL_TEMPERATURE") else None,
        ground_provider=os.getenv("AGENT_S_GROUNDING_PROVIDER", "huggingface"),
        ground_url=os.getenv("AGENT_S_GROUNDING_URL", "http://localhost:8080"),
        ground_api_key=os.getenv("AGENT_S_GROUNDING_API_KEY", ""),
        ground_model=os.getenv("AGENT_S_GROUNDING_MODEL", "ui-tars-1.5-7b"),
        grounding_width=int(os.getenv("AGENT_S_GROUNDING_WIDTH", "1920")),
        grounding_height=int(os.getenv("AGENT_S_GROUNDING_HEIGHT", "1080")),
        max_trajectory_length=int(os.getenv("AGENT_S_MAX_TRAJECTORY_LENGTH", "8")),
        enable_reflection=os.getenv("AGENT_S_ENABLE_REFLECTION", "true").lower() == "true",
        enable_local_env=os.getenv("AGENT_S_ENABLE_LOCAL_ENV", "false").lower() == "true",
        platform=os.getenv("AGENT_S_PLATFORM", default_platform),
    )


# Global executor instance (singleton)
_executor_instance: Optional[AgentSExecutor] = None


def get_executor() -> AgentSExecutor:
    """Get or create the global AgentSExecutor instance."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = create_executor_from_env()
    return _executor_instance

