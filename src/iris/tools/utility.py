"""
Utility tools for IRIS.

Provides utility functions like time and safe calculation.
"""

import ast
import math
import operator
from datetime import datetime
from typing import Any
from iris.tools.base import Tool, ToolArgument, ToolResult


class GetCurrentTimeTool(Tool):
    """Get the current date and time."""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "Get the current date and time in ISO format"

    @property
    def arguments(self) -> list[ToolArgument]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        """Execute time retrieval."""
        try:
            now = datetime.now()

            return ToolResult(
                success=True,
                content={
                    "iso": now.isoformat(),
                    "timestamp": now.timestamp(),
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                },
                metadata={"timezone": "local"}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Failed to get current time: {str(e)}"
            )


class CalculateTool(Tool):
    """
    Safe arithmetic calculator using AST parsing.

    Supports basic arithmetic operations and common math functions
    without using eval().
    """

    # Safe math functions from the math module
    SAFE_FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        # Math module functions
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "ceil": math.ceil,
        "floor": math.floor,
        "pi": math.pi,
        "e": math.e,
    }

    # Safe operators
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    @property
    def name(self) -> str:
        return "calculate"

    @property
    def description(self) -> str:
        return "Safely evaluate arithmetic expressions with basic math functions"

    @property
    def arguments(self) -> list[ToolArgument]:
        return [
            ToolArgument(
                name="expression",
                type=str,
                description="Mathematical expression to evaluate",
            )
        ]

    def _evaluate_node(self, node: ast.AST) -> Any:
        """
        Recursively evaluate an AST node safely.

        Args:
            node: AST node to evaluate

        Returns:
            Evaluation result

        Raises:
            ValueError: If node type is not allowed
        """
        if isinstance(node, ast.Constant):
            # Python 3.8+ uses ast.Constant for literals
            return node.value
        elif isinstance(node, ast.BinOp):
            # Binary operation (e.g., 1 + 2)
            left = self._evaluate_node(node.left)
            right = self._evaluate_node(node.right)
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Operator not allowed: {op_type.__name__}")
            return self.SAFE_OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            # Unary operation (e.g., -5)
            operand = self._evaluate_node(node.operand)
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Operator not allowed: {op_type.__name__}")
            return self.SAFE_OPERATORS[op_type](operand)
        elif isinstance(node, ast.Call):
            # Function call (e.g., sqrt(4))
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            if func_name not in self.SAFE_FUNCTIONS:
                raise ValueError(f"Function not allowed: {func_name}")

            func = self.SAFE_FUNCTIONS[func_name]
            args = [self._evaluate_node(arg) for arg in node.args]

            return func(*args)
        elif isinstance(node, ast.Name):
            # Variable reference (only allow pi and e)
            if node.id in self.SAFE_FUNCTIONS:
                return self.SAFE_FUNCTIONS[node.id]
            raise ValueError(f"Variable not allowed: {node.id}")
        elif isinstance(node, ast.Expression):
            # Top-level expression wrapper
            return self._evaluate_node(node.body)
        elif isinstance(node, ast.List):
            # List literal (for functions like sum, min, max)
            return [self._evaluate_node(item) for item in node.elts]
        else:
            raise ValueError(f"Node type not allowed: {type(node).__name__}")

    async def execute(self, **kwargs) -> ToolResult:
        """Execute safe calculation."""
        expression = kwargs["expression"].strip()

        if not expression:
            return ToolResult(
                success=False,
                content=None,
                error="Expression cannot be empty"
            )

        try:
            # Parse the expression into an AST
            tree = ast.parse(expression, mode="eval")

            # Evaluate the AST safely
            result = self._evaluate_node(tree)

            # Convert result to standard Python types
            if isinstance(result, (int, float)):
                result_value = result
            elif isinstance(result, list):
                result_value = result
            else:
                result_value = float(result)

            return ToolResult(
                success=True,
                content=result_value,
                metadata={
                    "expression": expression,
                    "result_type": type(result_value).__name__,
                }
            )

        except ZeroDivisionError:
            return ToolResult(
                success=False,
                content=None,
                error="Division by zero"
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Invalid expression: {str(e)}"
            )
        except SyntaxError:
            return ToolResult(
                success=False,
                content=None,
                error="Invalid syntax in expression"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content=None,
                error=f"Calculation failed: {str(e)}"
            )
