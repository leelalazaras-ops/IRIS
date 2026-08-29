"""
Tests for utility tools.
"""

import pytest
from datetime import datetime
from iris.tools.utility import GetCurrentTimeTool, CalculateTool


class TestGetCurrentTimeTool:
    """Tests for GetCurrentTimeTool."""

    @pytest.mark.asyncio
    async def test_get_current_time(self):
        """Test getting current time."""
        tool = GetCurrentTimeTool()

        result = await tool.execute()

        assert result.success is True
        assert isinstance(result.content, dict)

        # Check expected keys
        assert "iso" in result.content
        assert "timestamp" in result.content
        assert "year" in result.content
        assert "month" in result.content
        assert "day" in result.content
        assert "hour" in result.content
        assert "minute" in result.content
        assert "second" in result.content

        # Verify types
        assert isinstance(result.content["iso"], str)
        assert isinstance(result.content["timestamp"], float)
        assert isinstance(result.content["year"], int)

        # Year should be reasonable (2020-2100)
        assert 2020 <= result.content["year"] <= 2100

        # Month should be 1-12
        assert 1 <= result.content["month"] <= 12

        # Day should be 1-31
        assert 1 <= result.content["day"] <= 31

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = GetCurrentTimeTool()

        assert tool.name == "get_current_time"
        assert "time" in tool.description.lower()
        assert len(tool.arguments) == 0


class TestCalculateTool:
    """Tests for CalculateTool."""

    @pytest.mark.asyncio
    async def test_calculate_basic_addition(self):
        """Test basic addition."""
        tool = CalculateTool()

        result = await tool.execute(expression="2 + 3")

        assert result.success is True
        assert result.content == 5

    @pytest.mark.asyncio
    async def test_calculate_basic_subtraction(self):
        """Test basic subtraction."""
        tool = CalculateTool()

        result = await tool.execute(expression="10 - 3")

        assert result.success is True
        assert result.content == 7

    @pytest.mark.asyncio
    async def test_calculate_multiplication(self):
        """Test multiplication."""
        tool = CalculateTool()

        result = await tool.execute(expression="4 * 5")

        assert result.success is True
        assert result.content == 20

    @pytest.mark.asyncio
    async def test_calculate_division(self):
        """Test division."""
        tool = CalculateTool()

        result = await tool.execute(expression="20 / 4")

        assert result.success is True
        assert result.content == 5.0

    @pytest.mark.asyncio
    async def test_calculate_floor_division(self):
        """Test floor division."""
        tool = CalculateTool()

        result = await tool.execute(expression="7 // 2")

        assert result.success is True
        assert result.content == 3

    @pytest.mark.asyncio
    async def test_calculate_modulo(self):
        """Test modulo operation."""
        tool = CalculateTool()

        result = await tool.execute(expression="10 % 3")

        assert result.success is True
        assert result.content == 1

    @pytest.mark.asyncio
    async def test_calculate_power(self):
        """Test exponentiation."""
        tool = CalculateTool()

        result = await tool.execute(expression="2 ** 8")

        assert result.success is True
        assert result.content == 256

    @pytest.mark.asyncio
    async def test_calculate_complex_expression(self):
        """Test complex expression with multiple operations."""
        tool = CalculateTool()

        result = await tool.execute(expression="(2 + 3) * 4 - 10 / 2")

        assert result.success is True
        assert result.content == 15.0

    @pytest.mark.asyncio
    async def test_calculate_with_negation(self):
        """Test unary negation."""
        tool = CalculateTool()

        result = await tool.execute(expression="-5 + 10")

        assert result.success is True
        assert result.content == 5

    @pytest.mark.asyncio
    async def test_calculate_sqrt_function(self):
        """Test sqrt function."""
        tool = CalculateTool()

        result = await tool.execute(expression="sqrt(16)")

        assert result.success is True
        assert result.content == 4.0

    @pytest.mark.asyncio
    async def test_calculate_pow_function(self):
        """Test pow function."""
        tool = CalculateTool()

        result = await tool.execute(expression="pow(2, 10)")

        assert result.success is True
        assert result.content == 1024

    @pytest.mark.asyncio
    async def test_calculate_sin_function(self):
        """Test sin function."""
        tool = CalculateTool()

        result = await tool.execute(expression="sin(0)")

        assert result.success is True
        assert abs(result.content) < 0.0001  # Should be approximately 0

    @pytest.mark.asyncio
    async def test_calculate_log_function(self):
        """Test log function."""
        tool = CalculateTool()

        result = await tool.execute(expression="log(e)")

        assert result.success is True
        assert abs(result.content - 1.0) < 0.0001  # log(e) = 1

    @pytest.mark.asyncio
    async def test_calculate_pi_constant(self):
        """Test pi constant."""
        tool = CalculateTool()

        result = await tool.execute(expression="pi * 2")

        assert result.success is True
        assert abs(result.content - 6.283185307) < 0.0001

    @pytest.mark.asyncio
    async def test_calculate_e_constant(self):
        """Test e constant."""
        tool = CalculateTool()

        result = await tool.execute(expression="e")

        assert result.success is True
        assert abs(result.content - 2.718281828) < 0.0001

    @pytest.mark.asyncio
    async def test_calculate_min_function(self):
        """Test min function."""
        tool = CalculateTool()

        result = await tool.execute(expression="min([1, 5, 3, 9, 2])")

        assert result.success is True
        assert result.content == 1

    @pytest.mark.asyncio
    async def test_calculate_max_function(self):
        """Test max function."""
        tool = CalculateTool()

        result = await tool.execute(expression="max([1, 5, 3, 9, 2])")

        assert result.success is True
        assert result.content == 9

    @pytest.mark.asyncio
    async def test_calculate_sum_function(self):
        """Test sum function."""
        tool = CalculateTool()

        result = await tool.execute(expression="sum([1, 2, 3, 4, 5])")

        assert result.success is True
        assert result.content == 15

    @pytest.mark.asyncio
    async def test_calculate_division_by_zero(self):
        """Test division by zero returns error."""
        tool = CalculateTool()

        result = await tool.execute(expression="10 / 0")

        assert result.success is False
        assert "division by zero" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_invalid_syntax(self):
        """Test invalid syntax returns error."""
        tool = CalculateTool()

        result = await tool.execute(expression="2 + * 3")

        assert result.success is False
        assert "syntax" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_rejects_eval(self):
        """Test that eval is rejected."""
        tool = CalculateTool()

        result = await tool.execute(expression="eval('2 + 3')")

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_rejects_exec(self):
        """Test that exec is rejected."""
        tool = CalculateTool()

        result = await tool.execute(expression="exec('print(123)')")

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_rejects_import(self):
        """Test that imports are rejected."""
        tool = CalculateTool()

        result = await tool.execute(expression="__import__('os')")

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_rejects_unknown_function(self):
        """Test that unknown functions are rejected."""
        tool = CalculateTool()

        result = await tool.execute(expression="unknown_func(5)")

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_rejects_variable_access(self):
        """Test that variable access is rejected."""
        tool = CalculateTool()

        result = await tool.execute(expression="some_variable + 5")

        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_empty_expression(self):
        """Test empty expression returns error."""
        tool = CalculateTool()

        result = await tool.execute(expression="")

        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_calculate_whitespace_expression(self):
        """Test whitespace-only expression returns error."""
        tool = CalculateTool()

        result = await tool.execute(expression="   ")

        assert result.success is False
        assert "empty" in result.error.lower()

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = CalculateTool()

        assert tool.name == "calculate"
        assert "arithmetic" in tool.description.lower()
        assert len(tool.arguments) == 1
        assert tool.arguments[0].name == "expression"
        assert tool.arguments[0].type == str
