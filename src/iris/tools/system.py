"""
System information tools for IRIS.

Provides read-only system information with security considerations.
"""

import os
import platform
from pathlib import Path
from iris.tools.base import Tool, ToolArgument, ToolResult


# Sensitive environment variable patterns to exclude
SENSITIVE_ENV_PATTERNS = [
    "KEY", "TOKEN", "PASSWORD", "SECRET", "AUTH", "CREDENTIAL",
    "API", "PRIVATE", "CERT", "PASSPHRASE", "SESSION"
]


def is_sensitive_env_var(name: str) -> bool:
    """
    Check if an environment variable name suggests sensitive content.

    Args:
        name: Environment variable name

    Returns:
        True if the variable name contains sensitive patterns
    """
    upper_name = name.upper()
    return any(pattern in upper_name for pattern in SENSITIVE_ENV_PATTERNS)


class GetSystemInfoTool(Tool):
    """Get basic system information."""

    @property
    def name(self) -> str:
        return "get_system_info"

    @property
    def description(self) -> str:
        return "Get operating system and Python version information"

    @property
    def arguments(self) -> list[ToolArgument]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        """Execute system info retrieval."""
        try:
            info = {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "processor": platform.processor() or "Unknown",
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
            }

            return ToolResult(
                success=True,
                content=info,
                metadata={"tool": "get_system_info"}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to get system info: {str(e)}"
            )


class GetCurrentDirectoryTool(Tool):
    """Get the current working directory."""

    @property
    def name(self) -> str:
        return "get_current_directory"

    @property
    def description(self) -> str:
        return "Get the current working directory path"

    @property
    def arguments(self) -> list[ToolArgument]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        """Execute current directory retrieval."""
        try:
            cwd = Path.cwd()

            return ToolResult(
                success=True,
                content=str(cwd),
                metadata={
                    "absolute_path": str(cwd.resolve()),
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to get current directory: {str(e)}"
            )


class GetEnvironmentInfoTool(Tool):
    """Get sanitized environment information."""

    @property
    def name(self) -> str:
        return "get_environment_info"

    @property
    def description(self) -> str:
        return "Get non-sensitive environment variables"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(
                name="include_all",
                type=bool,
                description="Include all variables (still filters sensitive ones)",
                required=False,
                default=False,
            )
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute environment info retrieval."""
        include_all = kwargs.get("include_all", False)

        try:
            # Common non-sensitive environment variables
            common_vars = [
                "PATH", "HOME", "USER", "USERNAME", "SHELL",
                "LANG", "LC_ALL", "TERM", "EDITOR",
                "PWD", "OLDPWD", "HOSTNAME", "LOGNAME",
            ]

            env_info = {}
            filtered_count = 0

            if include_all:
                # Include all non-sensitive variables
                for key, value in os.environ.items():
                    if is_sensitive_env_var(key):
                        filtered_count += 1
                    else:
                        env_info[key] = value
            else:
                # Include only common safe variables
                for key in common_vars:
                    if key in os.environ:
                        env_info[key] = os.environ[key]

            return ToolResult(
                success=True,
                content=env_info,
                metadata={
                    "variable_count": len(env_info),
                    "filtered_count": filtered_count,
                    "include_all": include_all,
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to get environment info: {str(e)}"
            )
