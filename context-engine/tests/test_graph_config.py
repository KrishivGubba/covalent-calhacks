"""
Test suite for the GraphConfig utility class.

This module contains tests for:
- Config loading from YAML
- Default values when config is missing
- All threshold accessor methods
- Edge cases at threshold boundaries
"""

import os
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from graph_config import GraphConfig, get_graph_config


def setup_test_config(config_content: dict) -> str:
    """
    Create a temporary config file for testing.

    Args:
        config_content: The full config dict to write.

    Returns:
        Path to the temporary config file.
    """
    fd, path = tempfile.mkstemp(suffix=".yml")
    with os.fdopen(fd, "w") as f:
        yaml.dump(config_content, f)
    return path


def cleanup_test_config(path: str) -> None:
    """Remove temporary config file."""
    try:
        os.unlink(path)
    except OSError:
        pass


def test_load_config_from_yaml():
    """Test that config loads correctly from YAML file."""
    print("\n" + "=" * 50)
    print("Testing config load from YAML:")
    print("=" * 50)

    GraphConfig.reset_instance()

    config_content = {
        "graph_construction": {
            "confidence_thresholds": {
                "perfect_fit": 0.90,
                "good_fit": 0.75,
                "uncertain": 0.55,
                "poor_fit": 0.35,
            },
            "max_depth": 15,
            "bootstrap": {"enabled": False},
            "split": {
                "min_categories_to_split": 5,
                "min_data_entries_to_split": 10,
            },
        }
    }

    config_path = setup_test_config(config_content)
    try:
        config = GraphConfig(config_path)

        assert config.get_threshold("perfect_fit") == 0.90, "perfect_fit should be 0.90"
        assert config.get_threshold("good_fit") == 0.75, "good_fit should be 0.75"
        assert config.get_threshold("uncertain") == 0.55, "uncertain should be 0.55"
        assert config.get_threshold("poor_fit") == 0.35, "poor_fit should be 0.35"
        assert config.get_max_depth() == 15, "max_depth should be 15"
        assert config.is_bootstrap_enabled() is False, "bootstrap should be disabled"
        assert config.get_split_min_categories() == 5, "min_categories should be 5"
        assert config.get_split_min_entries() == 10, "min_entries should be 10"

        print("Config loaded values:")
        print(f"  perfect_fit: {config.get_threshold('perfect_fit')}")
        print(f"  good_fit: {config.get_threshold('good_fit')}")
        print(f"  uncertain: {config.get_threshold('uncertain')}")
        print(f"  poor_fit: {config.get_threshold('poor_fit')}")
        print(f"  max_depth: {config.get_max_depth()}")
        print(f"  bootstrap_enabled: {config.is_bootstrap_enabled()}")
        print(f"  min_categories: {config.get_split_min_categories()}")
        print(f"  min_entries: {config.get_split_min_entries()}")
        print("Config loaded correctly from YAML")
    finally:
        cleanup_test_config(config_path)
        GraphConfig.reset_instance()


def test_default_values_when_config_missing():
    """Test that default values are used when config file is missing."""
    print("\n" + "=" * 50)
    print("Testing default values when config missing:")
    print("=" * 50)

    GraphConfig.reset_instance()

    # Use a non-existent path
    config = GraphConfig("/nonexistent/path/config.yml")

    assert config.get_threshold("perfect_fit") == 0.85, "default perfect_fit should be 0.85"
    assert config.get_threshold("good_fit") == 0.70, "default good_fit should be 0.70"
    assert config.get_threshold("uncertain") == 0.50, "default uncertain should be 0.50"
    assert config.get_threshold("poor_fit") == 0.30, "default poor_fit should be 0.30"
    assert config.get_max_depth() == 10, "default max_depth should be 10"
    assert config.is_bootstrap_enabled() is True, "default bootstrap should be enabled"
    assert config.get_split_min_categories() == 3, "default min_categories should be 3"
    assert config.get_split_min_entries() == 5, "default min_entries should be 5"

    print("Default values:")
    print(f"  perfect_fit: {config.get_threshold('perfect_fit')}")
    print(f"  good_fit: {config.get_threshold('good_fit')}")
    print(f"  uncertain: {config.get_threshold('uncertain')}")
    print(f"  poor_fit: {config.get_threshold('poor_fit')}")
    print(f"  max_depth: {config.get_max_depth()}")
    print(f"  bootstrap_enabled: {config.is_bootstrap_enabled()}")
    print(f"  min_categories: {config.get_split_min_categories()}")
    print(f"  min_entries: {config.get_split_min_entries()}")
    print("Default values applied correctly")

    GraphConfig.reset_instance()


def test_partial_config_uses_defaults():
    """Test that missing keys use defaults while present keys are used."""
    print("\n" + "=" * 50)
    print("Testing partial config with defaults:")
    print("=" * 50)

    GraphConfig.reset_instance()

    # Only provide some values
    config_content = {
        "graph_construction": {
            "confidence_thresholds": {
                "perfect_fit": 0.95,
                # good_fit, uncertain, poor_fit missing
            },
            "max_depth": 20,
            # bootstrap and split missing
        }
    }

    config_path = setup_test_config(config_content)
    try:
        config = GraphConfig(config_path)

        # Custom values
        assert config.get_threshold("perfect_fit") == 0.95, "perfect_fit should be 0.95"
        assert config.get_max_depth() == 20, "max_depth should be 20"

        # Default values
        assert config.get_threshold("good_fit") == 0.70, "good_fit should default to 0.70"
        assert config.get_threshold("uncertain") == 0.50, "uncertain should default to 0.50"
        assert config.get_threshold("poor_fit") == 0.30, "poor_fit should default to 0.30"
        assert config.is_bootstrap_enabled() is True, "bootstrap should default to enabled"
        assert config.get_split_min_categories() == 3, "min_categories should default to 3"
        assert config.get_split_min_entries() == 5, "min_entries should default to 5"

        print("Mixed custom and default values applied correctly")
    finally:
        cleanup_test_config(config_path)
        GraphConfig.reset_instance()


def test_get_threshold_invalid_name():
    """Test that get_threshold raises KeyError for invalid names."""
    print("\n" + "=" * 50)
    print("Testing get_threshold with invalid name:")
    print("=" * 50)

    GraphConfig.reset_instance()
    config = GraphConfig("/nonexistent/path/config.yml")

    try:
        config.get_threshold("invalid_threshold_name")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        print(f"Correctly raised KeyError: {e}")

    GraphConfig.reset_instance()


def test_should_insert_directly():
    """Test should_insert_directly threshold logic."""
    print("\n" + "=" * 50)
    print("Testing should_insert_directly:")
    print("=" * 50)

    GraphConfig.reset_instance()
    config = GraphConfig("/nonexistent/path/config.yml")

    # Default perfect_fit is 0.85
    test_cases = [
        (0.90, True, "above threshold"),
        (0.85, True, "exactly at threshold"),
        (0.84, False, "below threshold"),
        (0.50, False, "well below threshold"),
        (1.0, True, "maximum confidence"),
        (0.0, False, "minimum confidence"),
    ]

    for confidence, expected, description in test_cases:
        result = config.should_insert_directly(confidence)
        assert result == expected, f"should_insert_directly({confidence}) should be {expected} ({description})"
        print(f"  confidence={confidence}: {result} ({description})")

    print("should_insert_directly threshold logic correct")
    GraphConfig.reset_instance()


def test_should_validate_with_llm():
    """Test should_validate_with_llm threshold logic."""
    print("\n" + "=" * 50)
    print("Testing should_validate_with_llm:")
    print("=" * 50)

    GraphConfig.reset_instance()
    config = GraphConfig("/nonexistent/path/config.yml")

    # Default: uncertain=0.50, perfect_fit=0.85
    # Should validate when: uncertain <= confidence < perfect_fit
    test_cases = [
        (0.90, False, "above perfect_fit"),
        (0.85, False, "exactly at perfect_fit (insert directly)"),
        (0.84, True, "below perfect_fit, above uncertain"),
        (0.70, True, "good_fit range"),
        (0.50, True, "exactly at uncertain threshold"),
        (0.49, False, "below uncertain threshold"),
        (0.30, False, "at poor_fit"),
        (0.0, False, "minimum confidence"),
    ]

    for confidence, expected, description in test_cases:
        result = config.should_validate_with_llm(confidence)
        assert result == expected, f"should_validate_with_llm({confidence}) should be {expected} ({description})"
        print(f"  confidence={confidence}: {result} ({description})")

    print("should_validate_with_llm threshold logic correct")
    GraphConfig.reset_instance()


def test_needs_restructure():
    """Test needs_restructure threshold logic."""
    print("\n" + "=" * 50)
    print("Testing needs_restructure:")
    print("=" * 50)

    GraphConfig.reset_instance()
    config = GraphConfig("/nonexistent/path/config.yml")

    # Default uncertain is 0.50
    # needs_restructure when confidence < uncertain
    test_cases = [
        (0.90, False, "high confidence"),
        (0.85, False, "at perfect_fit"),
        (0.50, False, "exactly at uncertain (does not need restructure)"),
        (0.49, True, "just below uncertain"),
        (0.30, True, "at poor_fit"),
        (0.0, True, "minimum confidence"),
    ]

    for confidence, expected, description in test_cases:
        result = config.needs_restructure(confidence)
        assert result == expected, f"needs_restructure({confidence}) should be {expected} ({description})"
        print(f"  confidence={confidence}: {result} ({description})")

    print("needs_restructure threshold logic correct")
    GraphConfig.reset_instance()


def test_threshold_boundary_exactly_at_values():
    """Test edge cases exactly at threshold boundary values."""
    print("\n" + "=" * 50)
    print("Testing exact boundary values:")
    print("=" * 50)

    GraphConfig.reset_instance()
    config = GraphConfig("/nonexistent/path/config.yml")

    # At exactly 0.85 (perfect_fit)
    assert config.should_insert_directly(0.85) is True, "0.85 should insert directly"
    assert config.should_validate_with_llm(0.85) is False, "0.85 should NOT validate with LLM"
    assert config.needs_restructure(0.85) is False, "0.85 should NOT need restructure"
    print("  At 0.85: insert_directly=True, validate_llm=False, restructure=False")

    # At exactly 0.50 (uncertain)
    assert config.should_insert_directly(0.50) is False, "0.50 should NOT insert directly"
    assert config.should_validate_with_llm(0.50) is True, "0.50 should validate with LLM"
    assert config.needs_restructure(0.50) is False, "0.50 should NOT need restructure"
    print("  At 0.50: insert_directly=False, validate_llm=True, restructure=False")

    # Just below uncertain (0.4999...)
    assert config.should_insert_directly(0.499) is False, "0.499 should NOT insert directly"
    assert config.should_validate_with_llm(0.499) is False, "0.499 should NOT validate with LLM"
    assert config.needs_restructure(0.499) is True, "0.499 should need restructure"
    print("  At 0.499: insert_directly=False, validate_llm=False, restructure=True")

    print("Boundary edge cases handled correctly")
    GraphConfig.reset_instance()


def test_singleton_pattern():
    """Test that GraphConfig maintains singleton behavior."""
    print("\n" + "=" * 50)
    print("Testing singleton pattern:")
    print("=" * 50)

    GraphConfig.reset_instance()

    config1 = GraphConfig("/nonexistent/path/config.yml")
    config2 = GraphConfig("/different/path/config.yml")  # Path ignored

    assert config1 is config2, "Should be the same instance"
    print("Singleton pattern verified")

    GraphConfig.reset_instance()


def test_module_level_get_graph_config():
    """Test the module-level get_graph_config function."""
    print("\n" + "=" * 50)
    print("Testing get_graph_config function:")
    print("=" * 50)

    GraphConfig.reset_instance()

    # Reset the module-level instance too
    import graph_config
    graph_config._config_instance = None

    config = get_graph_config()
    assert config is not None, "Should return a config instance"
    assert isinstance(config, GraphConfig), "Should be a GraphConfig instance"

    # Second call should return same instance
    config2 = get_graph_config()
    assert config is config2, "Should return the same instance"

    print("get_graph_config function works correctly")

    # Reset for next tests
    graph_config._config_instance = None
    GraphConfig.reset_instance()


def test_empty_graph_construction_section():
    """Test handling of empty graph_construction section."""
    print("\n" + "=" * 50)
    print("Testing empty graph_construction section:")
    print("=" * 50)

    GraphConfig.reset_instance()

    config_content = {
        "models": {"embedding": {}},
        "graph_construction": {},
    }

    config_path = setup_test_config(config_content)
    try:
        config = GraphConfig(config_path)

        # All should use defaults
        assert config.get_threshold("perfect_fit") == 0.85
        assert config.get_max_depth() == 10
        assert config.is_bootstrap_enabled() is True
        assert config.get_split_min_categories() == 3
        assert config.get_split_min_entries() == 5

        print("Empty graph_construction section uses all defaults")
    finally:
        cleanup_test_config(config_path)
        GraphConfig.reset_instance()


def test_no_graph_construction_section():
    """Test handling when graph_construction section is missing entirely."""
    print("\n" + "=" * 50)
    print("Testing missing graph_construction section:")
    print("=" * 50)

    GraphConfig.reset_instance()

    config_content = {
        "models": {"embedding": {}},
        "provider_settings": {},
    }

    config_path = setup_test_config(config_content)
    try:
        config = GraphConfig(config_path)

        # All should use defaults
        assert config.get_threshold("perfect_fit") == 0.85
        assert config.get_max_depth() == 10
        assert config.is_bootstrap_enabled() is True

        print("Missing graph_construction section uses all defaults")
    finally:
        cleanup_test_config(config_path)
        GraphConfig.reset_instance()


def test_return_types():
    """Test that all accessor methods return correct types."""
    print("\n" + "=" * 50)
    print("Testing return types:")
    print("=" * 50)

    GraphConfig.reset_instance()
    config = GraphConfig("/nonexistent/path/config.yml")

    assert isinstance(config.get_threshold("perfect_fit"), float), "Threshold should be float"
    assert isinstance(config.get_max_depth(), int), "max_depth should be int"
    assert isinstance(config.is_bootstrap_enabled(), bool), "bootstrap_enabled should be bool"
    assert isinstance(config.get_split_min_categories(), int), "min_categories should be int"
    assert isinstance(config.get_split_min_entries(), int), "min_entries should be int"
    assert isinstance(config.should_insert_directly(0.9), bool), "should_insert_directly should be bool"
    assert isinstance(config.should_validate_with_llm(0.7), bool), "should_validate_with_llm should be bool"
    assert isinstance(config.needs_restructure(0.3), bool), "needs_restructure should be bool"

    print("All return types correct")
    GraphConfig.reset_instance()


def run_all_tests():
    """Run all test suites."""
    print("\n" + "=" * 70)
    print("RUNNING ALL TESTS FOR GRAPH CONFIG")
    print("=" * 70)

    test_load_config_from_yaml()
    test_default_values_when_config_missing()
    test_partial_config_uses_defaults()
    test_get_threshold_invalid_name()
    test_should_insert_directly()
    test_should_validate_with_llm()
    test_needs_restructure()
    test_threshold_boundary_exactly_at_values()
    test_singleton_pattern()
    test_module_level_get_graph_config()
    test_empty_graph_construction_section()
    test_no_graph_construction_section()
    test_return_types()

    print("\n" + "=" * 70)
    print("ALL GRAPH CONFIG TESTS COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
