"""Discover tunable parameters from trader Python files via AST parsing.

Scans module-level ALL_CAPS numeric assignments (int/float) and provides
a utility to create modified copies with overridden values.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def discover_parameters(trader_path: str) -> list[dict[str, object]]:
    """Return module-level numeric constants from a trader .py file.

    Looks for patterns like:
        GAMMA = 0.06
        GAMMA: float = 0.06
    where the name is ALL_CAPS and value is int or float.
    """
    source = Path(trader_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    params: list[dict[str, object]] = []

    for node in ast.iter_child_nodes(tree):
        # Plain assignment: NAME = value
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, (int, float))
                    and target.id.isupper()
                    and not target.id.startswith("_")
                ):
                    params.append({
                        "name": target.id,
                        "default_value": node.value.value,
                        "type": "int" if isinstance(node.value.value, int) else "float",
                        "line": node.lineno,
                    })
        # Annotated assignment: NAME: type = value
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.value is not None
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, (int, float))
                and node.target.id.isupper()
                and not node.target.id.startswith("_")
            ):
                params.append({
                    "name": node.target.id,
                    "default_value": node.value.value,
                    "type": "int" if isinstance(node.value.value, int) else "float",
                    "line": node.lineno,
                })

    return params


def create_modified_trader(
    trader_path: str,
    overrides: dict[str, int | float],
    output_path: str,
) -> None:
    """Write a copy of the trader file with parameter values replaced."""
    source = Path(trader_path).read_text(encoding="utf-8")
    lines = source.split("\n")

    params = discover_parameters(trader_path)
    param_by_name = {str(p["name"]): p for p in params}

    for name, new_value in overrides.items():
        if name not in param_by_name:
            continue
        line_idx = int(param_by_name[name]["line"]) - 1
        line = lines[line_idx]

        # Match: NAME (optional :type) = numeric_value (optional comment)
        pattern = rf"^(\s*{re.escape(name)}\s*(?::\s*\S+\s*)?=\s*)([\d.eE+\-]+)(.*)"
        match = re.match(pattern, line)
        if match:
            prefix = match.group(1)
            suffix = match.group(3)
            if param_by_name[name]["type"] == "int":
                val_str = str(int(new_value))
            else:
                val_str = str(float(new_value))
            lines[line_idx] = prefix + val_str + suffix

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
