"""
Tests for filesystem tools.
"""

import pytest
import tempfile
import os
from pathlib import Path
from iris.tools.filesystem import (
    ListDirectoryTool,
    CreateDirectoryTool,
    ReadFileTool,
    WriteFileTool,
    validate_path,
)


class TestPathValidation:
    """Tests for path validation function."""

    def test_validate_path_within_base(self, tmp_path):
        """Test validating path within base directory."""
        test_path = tmp_path / "subdir" / "file.txt"

        is_valid, error = validate_path(test_path, tmp_path)

        assert is_valid is True
        assert error is None

    def test_validate_path_outside_base(self, tmp_path):
        """Test validating path outside base directory."""
        outside_path = tmp_path.parent / "outside"

        is_valid, error = validate_path(outside_path, tmp_path, allow_absolute=False)

        assert is_valid is False
        assert "outside" in error

    def test_validate_path_with_traversal(self, tmp_path):
        """Test path validation blocks traversal."""
        traversal_path = tmp_path / ".." / ".." / "etc" / "passwd"

        is_valid, error = validate_path(traversal_path, tmp_path, allow_absolute=False)

        assert is_valid is False
        assert "outside" in error


class TestListDirectoryTool:
    """Tests for ListDirectoryTool."""

    @pytest.mark.asyncio
    async def test_list_directory_success(self, tmp_path):
        """Test listing directory contents."""
        # Create test structure
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()
        (tmp_path / "subdir").mkdir()

        # Change to tmp_path so relative path works
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            tool = ListDirectoryTool()
            result = await tool.execute(path=".")

            assert result.success is True
            assert isinstance(result.content, list)
            assert len(result.content) == 3

            names = [entry["name"] for entry in result.content]
            assert "file1.txt" in names
            assert "file2.txt" in names
            assert "subdir" in names

            # Check types
            subdir_entry = next(e for e in result.content if e["name"] == "subdir")
            assert subdir_entry["type"] == "directory"

            file_entry = next(e for e in result.content if e["name"] == "file1.txt")
            assert file_entry["type"] == "file"
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self):
        """Test listing nonexistent directory."""
        tool = ListDirectoryTool()

        result = await tool.execute(path="/nonexistent/path")

        assert result.success is False
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_list_file_not_directory(self, tmp_path):
        """Test listing a file instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.touch()

        tool = ListDirectoryTool()
        result = await tool.execute(path=str(file_path))

        assert result.success is False
        assert "not a directory" in result.error


class TestCreateDirectoryTool:
    """Tests for CreateDirectoryTool."""

    @pytest.mark.asyncio
    async def test_create_directory(self, tmp_path):
        """Test creating a directory."""
        new_dir = tmp_path / "newdir"

        tool = CreateDirectoryTool()
        result = await tool.execute(path=str(new_dir))

        assert result.success is True
        assert new_dir.exists()
        assert new_dir.is_dir()
        assert result.metadata["created"] is True

    @pytest.mark.asyncio
    async def test_create_nested_directory(self, tmp_path):
        """Test creating nested directories."""
        nested_dir = tmp_path / "level1" / "level2" / "level3"

        tool = CreateDirectoryTool()
        result = await tool.execute(path=str(nested_dir))

        assert result.success is True
        assert nested_dir.exists()
        assert nested_dir.is_dir()

    @pytest.mark.asyncio
    async def test_create_existing_directory(self, tmp_path):
        """Test creating already existing directory."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        tool = CreateDirectoryTool()
        result = await tool.execute(path=str(existing_dir))

        assert result.success is True
        assert result.metadata["already_exists"] is True

    @pytest.mark.asyncio
    async def test_create_directory_path_is_file(self, tmp_path):
        """Test creating directory where file exists."""
        file_path = tmp_path / "file.txt"
        file_path.touch()

        tool = CreateDirectoryTool()
        result = await tool.execute(path=str(file_path))

        assert result.success is False
        assert "not a directory" in result.error


class TestReadFileTool:
    """Tests for ReadFileTool."""

    @pytest.mark.asyncio
    async def test_read_file_success(self, tmp_path):
        """Test reading a file."""
        file_path = tmp_path / "test.txt"
        content = "Hello, IRIS!\nLine 2"
        file_path.write_text(content, encoding="utf-8")

        tool = ReadFileTool()
        result = await tool.execute(path=str(file_path))

        assert result.success is True
        assert result.content == content
        # File size from stat (may differ due to line endings on Windows)
        assert result.metadata["size"] == file_path.stat().st_size

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """Test reading nonexistent file."""
        tool = ReadFileTool()

        result = await tool.execute(path="/nonexistent/file.txt")

        assert result.success is False
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_read_directory_not_file(self, tmp_path):
        """Test reading a directory instead of file."""
        dir_path = tmp_path / "dir"
        dir_path.mkdir()

        tool = ReadFileTool()
        result = await tool.execute(path=str(dir_path))

        assert result.success is False
        assert "not a file" in result.error

    @pytest.mark.asyncio
    async def test_read_file_too_large(self, tmp_path):
        """Test reading file exceeding size limit."""
        file_path = tmp_path / "large.txt"

        # Create a file larger than MAX_FILE_SIZE
        tool = ReadFileTool()
        large_size = tool.MAX_FILE_SIZE + 1000

        with open(file_path, "wb") as f:
            f.write(b"x" * large_size)

        result = await tool.execute(path=str(file_path))

        assert result.success is False
        assert "too large" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_binary_file(self, tmp_path):
        """Test reading binary file fails with decode error."""
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(b"\x80\x81\x82\x83")

        tool = ReadFileTool()
        result = await tool.execute(path=str(file_path))

        assert result.success is False
        assert "not valid UTF-8" in result.error


class TestWriteFileTool:
    """Tests for WriteFileTool."""

    @pytest.mark.asyncio
    async def test_write_file_success(self, tmp_path):
        """Test writing a file."""
        file_path = tmp_path / "output.txt"
        content = "Test content"

        tool = WriteFileTool()
        result = await tool.execute(path=str(file_path), content=content)

        assert result.success is True
        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == content

    @pytest.mark.asyncio
    async def test_write_file_creates_parents(self, tmp_path):
        """Test writing file creates parent directories."""
        file_path = tmp_path / "level1" / "level2" / "file.txt"
        content = "Nested file"

        tool = WriteFileTool()
        result = await tool.execute(path=str(file_path), content=content)

        assert result.success is True
        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == content

    @pytest.mark.asyncio
    async def test_write_file_no_overwrite(self, tmp_path):
        """Test writing fails when file exists and overwrite=False."""
        file_path = tmp_path / "existing.txt"
        file_path.write_text("Original content")

        tool = WriteFileTool()
        result = await tool.execute(
            path=str(file_path),
            content="New content",
            overwrite=False
        )

        assert result.success is False
        assert "already exists" in result.error
        # Original content should remain
        assert file_path.read_text() == "Original content"

    @pytest.mark.asyncio
    async def test_write_file_with_overwrite(self, tmp_path):
        """Test writing with overwrite=True replaces file."""
        file_path = tmp_path / "existing.txt"
        file_path.write_text("Original content")

        tool = WriteFileTool()
        result = await tool.execute(
            path=str(file_path),
            content="New content",
            overwrite=True
        )

        assert result.success is True
        assert file_path.read_text() == "New content"
        assert result.metadata["overwritten"] is True

    @pytest.mark.asyncio
    async def test_write_empty_file(self, tmp_path):
        """Test writing empty file."""
        file_path = tmp_path / "empty.txt"

        tool = WriteFileTool()
        result = await tool.execute(path=str(file_path), content="")

        assert result.success is True
        assert file_path.exists()
        assert file_path.read_text() == ""
