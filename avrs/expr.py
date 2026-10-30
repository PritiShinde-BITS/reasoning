"""Constrained, pure-expression interpreter for program-aided pilot runs.

No exec/eval/imports/file/network access. This is a narrow mathematical DSL,
NOT a general Python sandbox and NOT a replacement for a formal reasoner.
"""
import ast
import math
import operator
from fractions import Fraction


class UnsupportedExpression(ValueError):
    pass


def _bounded_range(*args):
    r = range(*args)
    if len(r) > 2000:
        raise UnsupportedExpression("range too large")
    return list(r)


def _bounded_factorial(n):
    if not isinstance(n, int) or n < 0 or n > 100:
        raise UnsupportedExpression("factorial outside supported range")
    return math.factorial(n)


def _bounded_comb(n, k):
    if not all(isinstance(x, int) for x in (n, k)) or n < 0 or n > 200:
        raise UnsupportedExpression("comb outside supported range")
    return math.comb(n, k)


ALLOWED_FUNCS = {
    "abs": abs, "min": min, "max": max, "sum": sum, "len": len,
    "round": round, "all": all, "any": any, "sorted": sorted,
    "int": int, "float": float, "bool": bool, "str": str,
    "range": _bounded_range, "gcd": math.gcd, "lcm": math.lcm,
    "sqrt": math.sqrt, "factorial": _bounded_factorial,
    "comb": _bounded_comb, "Fraction": Fraction,
}
BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
COMPARE = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def _validate_result(value):
    if isinstance(value, (str, list, tuple, dict, set)) and len(value) > 2000:
        raise UnsupportedExpression("Result too large")
    if isinstance(value, int) and value.bit_length() > 4096:
        raise UnsupportedExpression("Integer too large")
    if isinstance(value, float) and not math.isfinite(value):
        raise UnsupportedExpression("Non-finite numeric result")
    return value


def safe_expression(expression: str, variables: dict):
    if not isinstance(expression, str) or len(expression) > 600:
        raise UnsupportedExpression("Invalid or long expression")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 160:
        raise UnsupportedExpression("Expression too complex")

    def visit(node, depth=0):
        if depth > 30:
            raise UnsupportedExpression("Expression nested too deeply")
        def ev(n):
            return visit(n, depth + 1)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (str, bytes)) and len(node.value) > 500:
                raise UnsupportedExpression("Literal too large")
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                raise UnsupportedExpression("Unsupported literal")
            return node.value
        if isinstance(node, ast.Name):
            if node.id in variables:
                return variables[node.id]
            raise UnsupportedExpression(f"Undefined variable: {node.id}")
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [ev(v) for v in node.elts]
            return tuple(values) if isinstance(node, ast.Tuple) else (set(values) if isinstance(node, ast.Set) else values)
        if isinstance(node, ast.Dict):
            return {ev(k): ev(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            if isinstance(node.op, ast.USub): return -v
            if isinstance(node.op, ast.UAdd): return +v
            if isinstance(node.op, ast.Not): return not v
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and (not isinstance(b, (int, float)) or abs(b) > 100):
                raise UnsupportedExpression("Exponent outside safe bounds")
            if isinstance(node.op, ast.Mult) and not isinstance(a, (int, float, Fraction)):
                raise UnsupportedExpression("Only numeric multiplication supported")
            return _validate_result(BINARY[type(node.op)](a, b))
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(ev(v) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(ev(v) for v in node.values)
        if isinstance(node, ast.Compare):
            prev = ev(node.left)
            for op, right in zip(node.ops, node.comparators):
                if type(op) not in COMPARE: raise UnsupportedExpression("Unsupported comparison")
                cur = ev(right)
                if not COMPARE[type(op)](prev, cur): return False
                prev = cur
            return True
        if isinstance(node, ast.IfExp):
            return ev(node.body if ev(node.test) else node.orelse)
        if isinstance(node, ast.Subscript):
            collection, idx = ev(node.value), ev(node.slice)
            if not isinstance(collection, (list, tuple, str, dict)):
                raise UnsupportedExpression("Unsupported indexed object")
            return collection[idx]
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCS:
                raise UnsupportedExpression("Only approved function calls allowed")
            if node.keywords:
                raise UnsupportedExpression("Keyword arguments not supported")
            args = [ev(arg) for arg in node.args]
            return _validate_result(ALLOWED_FUNCS[node.func.id](*args))
        raise UnsupportedExpression(f"Unsupported syntax: {type(node).__name__}")

    try:
        return _validate_result(visit(tree.body))
    except (ArithmeticError, ValueError, TypeError, IndexError, KeyError, OverflowError) as exc:
        raise UnsupportedExpression(str(exc)) from exc


def run_program(payload):
    steps = payload.get("steps")
    final = payload.get("answer_expr")
    if not isinstance(steps, list) or len(steps) > 12 or not isinstance(final, str):
        raise UnsupportedExpression("Expected steps list (<=12) and answer_expr string")
    variables = {}
    trace = []
    for step in steps:
        if not isinstance(step, dict): raise UnsupportedExpression("Step must be object")
        name, expr = step.get("name"), step.get("expr")
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise UnsupportedExpression("Invalid variable name")
        if name in ALLOWED_FUNCS or name in variables:
            raise UnsupportedExpression("Variable name repeated or reserved")
        value = safe_expression(expr, variables)
        variables[name] = value
        trace.append({"name": name, "expr": expr, "value": str(value)})
    result = safe_expression(final, variables)
    return {"answer": str(result), "trace": trace, "status": "ok"}
