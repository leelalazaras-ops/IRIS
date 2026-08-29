"""
Filesystem tools for IRIS.

Provides safe filesystem operations with path validation and security boundaries.
"""

from pathlib import Path
from typing import Optional
from iris.tools.base import Tool, ToolArgument, ToolResult


class FilesystemError(Exception):
    """Exception for filesystem operation errors."""
    pass


def validate_path(path: Path, base_dir: Optional[Path] = None, allow_absolute: bool = True) -> tuple[bool, Optional[str]]:
    """
    Validate a path for safety.

    Args:
        path: Path to validate
        base_dir: Base directory to restrict operations to (default: cwd)
        allow_absolute: Whether to allow absolute paths outside base_dir

    Returns:
        Tuple of (is_valid, error_message)
    """
    if base_dir is None:
        base_dir = Path.cwd()

    try:
        # Resolve to absolute path
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()

        # If allow_absolute is True, allow any valid path
        if allow_absolute:
            return True, None

        # Check if path is within base directory
        try:
            resolved_path.relative_to(resolved_base)
        except ValueError:
            return False, f"Path '{path}' is outside the allowed directory"

        return True, None

    except (OSError, RuntimeError) as e:
        return False, f"Path validation failed: {str(e)}"


class ListDirectoryTool(Tool):
    """List contents of a directory."""

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return "List files and directories in the specified path"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(
                name="path",
                type=str,
                description="Directory path to list (relative or absolute)",
                required=False,
                default=".",
            )
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute directory listing."""
        path_str = kwargs.get("path", ".")

        try:
            path = Path(path_str)

            # Validate path
            is_valid, error_msg = validate_path(path)
            if not is_valid:
                return ToolResult(
                    success=False,
                    content=None,
                    error=error_msg
                )

            # Check if path exists and is a directory
            if not path.exists():
                return ToolResult(
                    success=False,
                    content=None,
                    error=f"Path does not exist: {path}"
                )

            if not path.is_dir():
                return ToolResult(
                    success=False,
                    content=None,
                    error=f"Path is not a directory: {path}"
                )

            # List directory contents
            entries = []
            for entry in sorted(path.iterdir()):
                entries.append({
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "path": str(entry),
                })

            return ToolResult(
                success=True,
                content=entries,
                metadata={
                    "path": str(path.resolve()),
                    "count": len(entries)
                }
            )

        except PermissionError:
            return ToolResult(
                success=False,
                content=None,
                error=f"Permission denied: {path_str}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to list directory: {str(e)}"
            )


class CreateDirectoryTool(Tool):
    """Create a directory (with parents if needed)."""

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return "Create a directory, including parent directories if needed"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(
                name="path",
                type=str,
                description="Directory path to create",
            )
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute directory creation."""
        path_str = kwargs["path"]

        try:
            path = Path(path_str)

            # Validate path
            is_valid, error_msg = validate_path(path)
            if not is_valid:
                return ToolResult(
                    success=False,
                    content=None,
                    error=error_msg
                )

            # Check if already exists
            if path.exists():
                if path.is_dir():
                    return ToolResult(
                        success=True,
                        content=str(path.resolve()),
                        metadata={"already_exists": True}
                    )
                else:
                    return ToolResult(
                        success=False,
                        content=None,
                        error=f"Path exists but is not a directory: {path}"
                    )

            # Create directory
            path.mkdir(parents=True, exist_ok=True)

            return ToolResult(
                success=True,
                content=str(path.resolve()),
                metadata={"created": True}
            )

        except PermissionError:
            return ToolResult(
                success=False,
                content=None,
                error=f"Permission denied: {path_str}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to create directory: {str(e)}"
            )


class ReadFileTool(Tool):
    """Read contents of a text file."""

    # Maximum file size to read (10 MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a text file"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(
                name="path",
                type=str,
                description="File path to read",
            )
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute file reading."""
        path_str = kwargs["path"]

        try:
            path = Path(path_str)

            # Validate path
            is_valid, error_msg = validate_path(path)
            if not is_valid:
                return ToolResult(
                    success=False,
                    content=None,
                    error=error_msg
                )

            # Check if path exists
            if not path.exists():
                return ToolResult(
                    success=False,
                    content=None,
                    error=f"File does not exist: {path}"
                )

            # Check if it's a file
            if not path.is_file():
                return ToolResult(
                    success=False,
                    content=None,
                    error=f"Path is not a file: {path}"
                )

            # Check file size
            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return ToolResult(
                    success=False,
                    content=None,
                    error=f"File too large: {file_size} bytes (max {self.MAX_FILE_SIZE})"
                )

            # Read file contents
            content = path.read_text(encoding="utf-8")

            return ToolResult(
                success=True,
                content=content,
                metadata={
                    "path": str(path.resolve()),
                    "size": file_size,
                }
            )

        except PermissionError:
            return ToolResult(
                success=False,
                content=None,
                error=f"Permission denied: {path_str}"
            )
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                content=None,
                error=f"File is not valid UTF-8 text: {path_str}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to read file: {str(e)}"
            )


class WriteFileTool(Tool):
    """Write contents to a text file."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write text content to a file"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(
                name="path",
                type=str,
                description="File path to write to",
            ),
            ToolArgument(
                name="content",
                type=str,
                description="Content to write to the file",
            ),
            ToolArgument(
                name="overwrite",
                type=bool,
                description="Whether to overwrite existing file",
                required=False,
                default=False,
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """Execute file writing."""
        path_str = kwargs["path"]
        content = kwargs["content"]
        overwrite = kwargs.get("overwrite", False)

        try:
            path = Path(path_str)

            # Validate path
            is_valid, error_msg = validate_path(path)
            if not is_valid:
                return ToolResult(
                    success=False,
                    content=None,
                    error=error_msg
                )

            # Check if file exists and overwrite is False
            if path.exists() and not overwrite:
                return ToolResult(
                    success=False,
                    content=None,
                    error=f"File already exists (use overwrite=True to replace): {path}"
                )

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            path.write_text(content, encoding="utf-8")

            return ToolResult(
                success=True,
                content=str(path.resolve()),
                metadata={
                    "bytes_written": len(content.encode("utf-8")),
                    "overwritten": path.exists() and overwrite,
                }
            )

        except PermissionError:
            return ToolResult(
                success=False,
                content=None,
                error=f"Permission denied: {path_str}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to write file: {str(e)}"
            )
