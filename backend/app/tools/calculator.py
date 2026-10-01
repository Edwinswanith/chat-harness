import ast
import math
import operator
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.contracts import ToolResult


class CalculatorArguments(BaseModel):
    expression: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")


class Calculator:
    name = "calculator"
    description = "Evaluate bounded arithmetic without eval or shell access."
    schema = CalculatorArguments
    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                 ast.Div: operator.truediv, ast.Mod: operator.mod}

    def evaluate(self, node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self.evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in self.operators:
            value = self.operators[type(node.op)](self.evaluate(node.left), self.evaluate(node.right))
        else:
            raise ValueError("Only numbers, parentheses, +, -, *, / and % are allowed")
        if not math.isfinite(value) or abs(value) > 1e15:
            raise ValueError("Arithmetic result exceeds limits")
        return value

    async def execute(self, scope, run, arguments):
        tree = ast.parse(arguments.expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 100:
            raise ValueError("Expression exceeds complexity limit")
        return ToolResult(status="success", data={"value": self.evaluate(tree.body)})
