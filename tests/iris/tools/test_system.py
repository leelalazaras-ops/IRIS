"""
Tests for system tools.
"""

import pytest
import platform
import os
from pathlib import Path
from iris.tools.system import (
    GetSystemInfoTool,
    GetCurrentDirectoryTool,
    GetEnvironmentInfoTool,
    is_sensitive_env_var,
)


class TestSensitiveEnvVarDetection:
    """Tests for sensitive environment variable detection."""

    def test_sensitive_patterns(self):
        """Test detection of sensitive environment variables."""
        assert is_sensitive_env_var("API_KEY") is True
        assert is_sensitive_env_var("SECRET_TOKEN") is True
        assert is_sensitive_env_var("DB_PASSWORD") is True
        assert is_sensitive_env_var("AWS_SECRET_ACCESS_KEY") is True
        assert is_sensitive_env_var("OAUTH_TOKEN") is True
        assert is_sensitive_env_var("PRIVATE_KEY") is True
        assert is_sensitive_env_var("AUTH_CREDENTIAL") is True

    def test_non_sensitive_patterns(self):
        """Test non-sensitive variables are not flagged."""
        assert is_sensitive_env_var("PATH") is False
        assert is_sensitive_env_var("HOME") is False
        assert is_sensitive_env_var("USER") is False
        assert is_sensitive_env_var("LANG") is False
        assert is_sensitive_env_var("EDITOR") is False

    def test_case_insensitive(self):
        """Test detection is case-insensitive."""
        assert is_sensitive_env_var("api_key") is True
        assert is_sensitive_env_var("Api_Key") is True
        assert is_sensitive_env_var("secret_token") is True


class TestGetSystemInfoTool:
    """Tests for GetSystemInfoTool."""

    @pytest.mark.asyncio
    async def test_get_system_info(self):
        """Test getting system information."""
        tool = GetSystemInfoTool()

        result = await tool.execute()

        assert result.success is True
        assert isinstance(result.content, dict)

        # Check expected keys
        assert "platform" in result.content
        assert "platform_release" in result.content
        assert "platform_version" in result.content
        assert "architecture" in result.content
        assert "python_version" in result.content
        assert "python_implementation" in result.content

        # Verify values are sensible
        assert result.content["platform"] in ["Windows", "Linux", "Darwin", "Java"]
        assert len(result.content["python_version"]) > 0

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = GetSystemInfoTool()

        assert tool.name == "get_system_info"
        assert "system" in tool.description.lower()
        assert len(tool.arguments) == 0


class TestGetCurrentDirectoryTool:
    """Tests for GetCurrentDirectoryTool."""

    @pytest.mark.asyncio
    async def test_get_current_directory(self):
        """Test getting current directory."""
        tool = GetCurrentDirectoryTool()

        result = await tool.execute()

        assert result.success is True
        assert isinstance(result.content, str)

        # Should be a valid path
        current_dir = Path(result.content)
        assert current_dir.exists()
        assert current_dir.is_dir()

        # Should match Python's cwd
        assert Path(result.content) == Path.cwd()

    @pytest.mark.asyncio
    async def test_current_directory_metadata(self):
        """Test metadata includes absolute path."""
        tool = GetCurrentDirectoryTool()

        result = await tool.execute()

        assert result.success is True
        assert "absolute_path" in result.metadata
        assert Path(result.metadata["absolute_path"]).is_absolute()

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = GetCurrentDirectoryTool()

        assert tool.name == "get_current_directory"
        assert "directory" in tool.description.lower()
        assert len(tool.arguments) == 0


class TestGetEnvironmentInfoTool:
    """Tests for GetEnvironmentInfoTool."""

    @pytest.mark.asyncio
    async def test_get_environment_info_common(self, monkeypatch):
        """Test getting common environment variables."""
        # Set some test environment variables
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        monkeypatch.setenv("HOME", "/home/test")
        monkeypatch.setenv("USER", "testuser")

        tool = GetEnvironmentInfoTool()
        result = await tool.execute(include_all=False)

        assert result.success is True
        assert isinstance(result.content, dict)

        # Should include common non-sensitive variables
        if "PATH" in os.environ:
            assert "PATH" in result.content
        if "HOME" in os.environ:
            assert "HOME" in result.content

        # Metadata
        assert "variable_count" in result.metadata
        assert result.metadata["include_all"] is False

    @pytest.mark.asyncio
    async def test_get_environment_info_filters_sensitive(self, monkeypatch):
        """Test that sensitive variables are filtered."""
        # Set sensitive and non-sensitive variables
        monkeypatch.setenv("SAFE_VAR", "safe_value")
        monkeypatch.setenv("API_KEY", "secret123")
        monkeypatch.setenv("SECRET_TOKEN", "verysecret")

        tool = GetEnvironmentInfoTool()
        result = await tool.execute(include_all=True)

        assert result.success is True
        assert isinstance(result.content, dict)

        # Non-sensitive should be included
        assert "SAFE_VAR" in result.content

        # Sensitive should be filtered
        assert "API_KEY" not in result.content
        assert "SECRET_TOKEN" not in result.content

        # Should track filtered count
        assert result.metadata["filtered_count"] >= 2

    @pytest.mark.asyncio
    async def test_get_environment_info_include_all(self, monkeypatch):
        """Test include_all parameter."""
        monkeypatch.setenv("CUSTOM_VAR", "custom_value")

        tool = GetEnvironmentInfoTool()

        # With include_all=False, custom var not included
        result1 = await tool.execute(include_all=False)
        assert "CUSTOM_VAR" not in result1.content

        # With include_all=True, custom var included
        result2 = await tool.execute(include_all=True)
        assert "CUSTOM_VAR" in result2.content

    @pytest.mark.asyncio
    async def test_get_environment_info_no_secrets_leaked(self, monkeypatch):
        """Test that no secrets are ever leaked."""
        # Set various sensitive patterns
        sensitive_vars = [
            "MY_API_KEY",
            "SECRET_VALUE",
            "PASSWORD",
            "AUTH_TOKEN",
            "PRIVATE_KEY",
            "CREDENTIAL",
        ]

        for var in sensitive_vars:
            monkeypatch.setenv(var, f"secret_{var}")

        tool = GetEnvironmentInfoTool()
        result = await tool.execute(include_all=True)

        assert result.success is True

        # None of the sensitive variables should appear
        for var in sensitive_vars:
            assert var not in result.content

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = GetEnvironmentInfoTool()

        assert tool.name == "get_environment_info"
        assert "environment" in tool.description.lower()
        assert len(tool.arguments) == 1
        assert tool.arguments[0].name == "include_all"
        assert tool.arguments[0].type == bool
        assert tool.arguments[0].required is False
