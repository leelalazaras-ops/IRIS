"""
Basic import test to verify package installation.
"""
import pytest


def test_iris_import():
    """Test that the iris package can be imported."""
    import iris
    assert iris.__version__ == "0.1.0"


def test_core_import():
    """Test that iris.core can be imported."""
    from iris import core
    assert core.__version__ == "0.1.0"


def test_all_modules_import():
    """Test that all submodules can be imported."""
    from iris import ai, voice, tools, memory, vision, web, ui, security

    # If imports succeed without errors, the test passes
    assert True


def test_cli_import():
    """Test that the CLI module can be imported."""
    from iris.core import cli
    assert callable(cli.main)
