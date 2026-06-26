"""
utils/flatten_for_compat.py

Converts a ReviewedUnitManifest (which may contain stacks) into a flat list of
Card-like dicts that the Unity PaperCaveManifestLoader can consume directly.

Stacks are expanded: each StackItem becomes its own top-level unit entry
with id = f"{stack.id}_item_{item.index}" and priority = "secondary".
The stack's whyThisUnit and styleHint are inherited by each expanded item.

Output format mirrors the UnitManifest JSON that unity_export.py writes, but
with type="card" for every entry and no "items" / "stackLabel" fields.
"""
from __future__ import annotations

from typing import Any


def flatten_stacks_for_compat(manifest_dict: dict) -> dict:
    """
    Takes the raw dict representation of a ReviewedUnitManifest and returns
    a new dict where every unit is type="card".

    Stack units are expanded into individual card units; single card units
    pass through unchanged.
    """
    flattened_units: list[dict] = []

    for unit in manifest_dict.get("units", []):
        if unit.get("type") == "stack":
            flattened_units.extend(_expand_stack(unit))
        else:
            flattened_units.append(unit)

    result = {k: v for k, v in manifest_dict.items() if k != "units"}
    result["units"] = flattened_units
    result["unitCount"] = len(flattened_units)
    result["flattenedFromStacks"] = True
    return result


def _expand_stack(stack: dict) -> list[dict]:
    """Converts a stack unit into a list of individual card units."""
    items: list[dict] = stack.get("items") or []
    style_hint: dict = stack.get("styleHint", {})
    why: str = stack.get("whyThisUnit", "")
    stack_id: str = stack.get("id", "unit_00")
    category: str = stack.get("category", "")

    expanded: list[dict] = []
    for item in items:
        card: dict[str, Any] = {
            "id": f"{stack_id}_item_{item.get('index', 0)}",
            "type": "card",
            "priority": "secondary",
            "title": item.get("title", ""),
            "category": category,
            "summary": "",
            "contentType": item.get("contentType", "text_panel"),
            "content": item.get("content", {}),
            "conceptualOrigin": "",
            "whyThisUnit": why,
            "styleHint": style_hint,
        }
        expanded.append(card)
    return expanded


if __name__ == "__main__":
    import json, sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python flatten_for_compat.py outputs/<paper_id>/07_reviewer_output.json")
        sys.exit(1)

    src = Path(sys.argv[1])
    data = json.loads(src.read_text(encoding="utf-8"))
    flat = flatten_stacks_for_compat(data)

    out = src.parent / "07_reviewer_output_flat.json"
    out.write_text(json.dumps(flat, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Flattened manifest written to {out}")
    print(f"  Original unit count: {data.get('unitCount', '?')}")
    print(f"  Flattened unit count: {flat['unitCount']}")
