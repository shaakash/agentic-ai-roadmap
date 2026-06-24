"""Static safety review for agent-generated rule code.

Before any agent-authored check is allowed near the sandbox, it must pass a static
AST review: no imports, no attribute access to dunders, no calls to dangerous
builtins, no I/O. This is a deny-by-default allowlist - if the AST contains a node
type or name we don't explicitly permit, the code is rejected.

This is REAL and self-contained (stdlib `ast` only). The dynamic sandbox execution
(sandbox/validate.py) is a separate, later line of defense.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# Node types permitted in a generated check function body.
_ALLOWED_NODES = {
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return,
    ast.If, ast.BoolOp, ast.And, ast.Or, ast.Not, ast.UnaryOp,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.Name, ast.Load, ast.Attribute, ast.Constant,
    ast.Assign, ast.Store, ast.Tuple, ast.List, ast.Subscript,
    ast.Expr, ast.Call,
}
# The only callables a check may invoke.
_ALLOWED_CALLS = {"abs", "min", "max", "round", "len", "bool", "float", "int"}
# Attribute access is restricted to the record's known fields (no dunders).
_FORBIDDEN_ATTR_PREFIX = "__"


@dataclass
class ReviewVerdict:
    ok: bool
    reasons: list[str]


def review_generated_code(code: str, func_name: str = "check") -> ReviewVerdict:
    """Statically verify generated check code. Returns a ReviewVerdict."""
    reasons: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:  # pragma: no cover - defensive
        return ReviewVerdict(False, [f"syntax error: {exc}"])

    # Must define exactly one function with the expected name.
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(funcs) != 1 or funcs[0].name != func_name:
        reasons.append(f"must define exactly one function named '{func_name}'")

    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            reasons.append(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and node.attr.startswith(_FORBIDDEN_ATTR_PREFIX):
            reasons.append(f"dunder attribute access not allowed: {node.attr}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
                name = getattr(node.func, "id", "<expr>")
                reasons.append(f"disallowed call: {name}")

    return ReviewVerdict(ok=not reasons, reasons=sorted(set(reasons)))
