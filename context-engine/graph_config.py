"""
Graph configuration utility for the context tree construction algorithm.

This module provides a singleton GraphConfig class that loads configuration
from model_config.yml and provides easy access to threshold values and
graph construction settings.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import yaml


class GraphConfig:
    """
    Singleton configuration class for graph construction settings.

    Loads configuration from model_config.yml and provides accessor methods
    for all graph construction parameters with sensible defaults.
    """

    _instance: Optional["GraphConfig"] = None

    # Default values used when config is missing
    DEFAULTS = {
        "confidence_thresholds": {
            "perfect_fit": 0.85,
            "good_fit": 0.70,
            "uncertain": 0.50,
            "poor_fit": 0.30,
        },
        "max_depth": 10,
        "bootstrap": {
            "enabled": True,
        },
        "split": {
            "min_categories_to_split": 3,
            "min_data_entries_to_split": 5,
        },
    }

    def __new__(cls, config_path: Optional[str] = None) -> "GraphConfig":
        """
        Create or return the singleton instance.

        Args:
            config_path: Optional path to config file. If provided on first call,
                        it will be used. Subsequent calls ignore this parameter.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration.

        Args:
            config_path: Optional path to the config file. Defaults to
                        model_config.yml in the parent directory.
        """
        if self._initialized:
            return

        self._initialized = True
        self._config = {}

        if config_path is None:
            # Default to model_config.yml in parent directory (or bundle root when frozen)
            if getattr(sys, 'frozen', False):
                config_path = Path(sys._MEIPASS) / "model_config.yml"
            else:
                current_dir = Path(__file__).parent
                config_path = current_dir.parent / "model_config.yml"
        else:
            config_path = Path(config_path)

        self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to the configuration file.
        """
        try:
            if config_path.exists():
                with open(config_path, "r") as f:
                    full_config = yaml.safe_load(f)
                    self._config = full_config.get("graph_construction", {})
        except (yaml.YAMLError, IOError):
            # If loading fails, use defaults
            self._config = {}

    def _get_nested(self, keys: list, default=None):
        """
        Get a nested value from the config.

        Args:
            keys: List of keys to traverse.
            default: Default value if key path doesn't exist.

        Returns:
            The value at the key path or the default.
        """
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def _get_default_nested(self, keys: list):
        """Get a nested value from the defaults."""
        current = self.DEFAULTS
        for key in keys:
            current = current[key]
        return current

    def get_threshold(self, name: str) -> float:
        """
        Get a confidence threshold by name.

        Args:
            name: The threshold name (perfect_fit, good_fit, uncertain, poor_fit).

        Returns:
            The threshold value as a float.

        Raises:
            KeyError: If the threshold name is not recognized.
        """
        if name not in self.DEFAULTS["confidence_thresholds"]:
            raise KeyError(f"Unknown threshold name: {name}")

        value = self._get_nested(
            ["confidence_thresholds", name],
            self._get_default_nested(["confidence_thresholds", name])
        )
        return float(value)

    def get_max_depth(self) -> int:
        """
        Get the maximum tree depth.

        Returns:
            Maximum depth of the tree (root = depth 0).
        """
        value = self._get_nested(["max_depth"], self.DEFAULTS["max_depth"])
        return int(value)

    def is_bootstrap_enabled(self) -> bool:
        """
        Check if bootstrap mode is enabled.

        Returns:
            True if auto-create first node from root is enabled.
        """
        value = self._get_nested(
            ["bootstrap", "enabled"],
            self._get_default_nested(["bootstrap", "enabled"])
        )
        return bool(value)

    def get_split_min_categories(self) -> int:
        """
        Get minimum categories required before considering a split.

        Returns:
            Minimum number of categories before split consideration.
        """
        value = self._get_nested(
            ["split", "min_categories_to_split"],
            self._get_default_nested(["split", "min_categories_to_split"])
        )
        return int(value)

    def get_split_min_entries(self) -> int:
        """
        Get minimum data entries required before considering a split.

        Returns:
            Minimum total data entries before split consideration.
        """
        value = self._get_nested(
            ["split", "min_data_entries_to_split"],
            self._get_default_nested(["split", "min_data_entries_to_split"])
        )
        return int(value)

    def should_insert_directly(self, confidence: float) -> bool:
        """
        Check if data should be inserted directly without LLM validation.

        Args:
            confidence: The confidence score (0.0 to 1.0).

        Returns:
            True if confidence >= perfect_fit threshold.
        """
        return confidence >= self.get_threshold("perfect_fit")

    def should_validate_with_llm(self, confidence: float) -> bool:
        """
        Check if LLM validation is needed for the given confidence.

        Args:
            confidence: The confidence score (0.0 to 1.0).

        Returns:
            True if confidence >= uncertain but < perfect_fit threshold.
        """
        uncertain = self.get_threshold("uncertain")
        perfect_fit = self.get_threshold("perfect_fit")
        return uncertain <= confidence < perfect_fit

    def needs_restructure(self, confidence: float) -> bool:
        """
        Check if a structural change (new node) is likely needed.

        Args:
            confidence: The confidence score (0.0 to 1.0).

        Returns:
            True if confidence < uncertain threshold.
        """
        return confidence < self.get_threshold("uncertain")

    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance (primarily for testing).

        This allows creating a new instance with different configuration.
        """
        cls._instance = None


# Module-level instance for easy import
_config_instance: Optional[GraphConfig] = None


def get_graph_config(config_path: Optional[str] = None) -> GraphConfig:
    """
    Get the graph configuration singleton instance.

    Args:
        config_path: Optional path to config file (only used on first call).

    Returns:
        The GraphConfig singleton instance.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = GraphConfig(config_path)
    return _config_instance
