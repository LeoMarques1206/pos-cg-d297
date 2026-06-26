"""
utils/unity_export.py

Copies the final pipeline output (manifest.json + referenced FIG_*.png images)
into Assets/PaperCaveData/{paper_id}/ so the Unity Editor can load them.

Stacks are preserved as-is in the manifest; Unity's PaperCaveSceneBuilder3D
handles them natively via type="stack" units.

Usage:
  python -m utils.unity_export <paper_id>
  python -m utils.unity_export <paper_id> --assets-root ../Assets

  # or import and call directly:
  from utils.unity_export import export_to_unity
  export_to_unity(paper_id="my_paper_2024")
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path


def export_to_unity(
    paper_id: str,
    outputs_root: Path | None = None,
    assets_root: Path | None = None,
    paper_folder: Path | None = None,
    verbose: bool = True,
) -> Path:
    """
    Copies manifest.json + referenced FIG_*.png files into Unity's
    Assets/PaperCaveData/{paper_id}/ directory.

    Returns the path to the written manifest.json.
    """
    outputs_root = outputs_root or Path("outputs")
    assets_root  = assets_root  or (Path(__file__).parent.parent.parent / "Assets")

    reviewer_output = outputs_root / paper_id / "07_reviewer_output.json"
    if not reviewer_output.exists():
        raise FileNotFoundError(
            f"No reviewer output found at {reviewer_output}.\n"
            f"Run the crew.py pipeline first."
        )

    manifest_dict = json.loads(reviewer_output.read_text(encoding="utf-8"))
    flat_manifest = _strip_unity_irrelevant(manifest_dict)

    # Destination folders
    dest_root   = assets_root / "PaperCaveData" / paper_id
    dest_images = dest_root / "images"
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_images.mkdir(parents=True, exist_ok=True)

    # Write manifest.json
    manifest_path = dest_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(flat_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if verbose:
        print(f"  [unity_export] Manifest written: {manifest_path}")
        print(f"  [unity_export] Units in manifest: {flat_manifest.get('unitCount', '?')}")

    # Copy FIG_*.png files referenced in the manifest
    copied, missing = _copy_figures(flat_manifest, paper_id, paper_folder, dest_images, verbose)

    if verbose:
        print(f"  [unity_export] Images copied: {copied}, not found: {missing}")
        print(f"  [unity_export] Done → {dest_root}")

    return manifest_path


def _strip_unity_irrelevant(manifest: dict) -> dict:
    """Remove fields that only serve the Python pipeline and have no function in Unity."""
    m = copy.deepcopy(manifest)

    for key in ("objectScores", "totalAttempts", "assembledFromMultipleAttempts",
                "implementationNotes", "flattenedFromStacks"):
        m.pop(key, None)

    for unit in m.get("units", []):
        for key in ("conceptualOrigin", "whyThisUnit"):
            unit.pop(key, None)
        if isinstance(unit.get("styleHint"), dict):
            unit["styleHint"].pop("colorName", None)
        for item in unit.get("items") or []:
            for key in ("conceptualOrigin", "whyThisUnit"):
                item.pop(key, None)

    return m


def _copy_figures(
    manifest: dict,
    paper_id: str,
    paper_folder: Path | None,
    dest_images: Path,
    verbose: bool,
) -> tuple[int, int]:
    """
    Finds all assetReference values (e.g. "FIG1") in the manifest, resolves
    them to FIG_*.png filenames, and copies them from the paper folder.
    """
    # Collect all unique asset references (flat units and stack items)
    refs: set[str] = set()
    for unit in manifest.get("units", []):
        content = unit.get("content") or {}
        ref = content.get("assetReference")
        if ref:
            refs.add(ref)
        for item in unit.get("items") or []:
            item_content = item.get("content") or {}
            item_ref = item_content.get("assetReference")
            if item_ref:
                refs.add(item_ref)

    if not refs:
        return 0, 0

    # Search locations for the PNG files
    search_dirs: list[Path] = []
    if paper_folder and paper_folder.is_dir():
        search_dirs.append(paper_folder)
    search_dirs.append(Path("papers") / paper_id)

    copied = 0
    missing = 0
    for ref in sorted(refs):
        # assetReference is like "FIG1" or "FIG_1"; normalise to FIG_N.png
        normalised = ref.replace("FIG", "FIG_").replace("FIG__", "FIG_")
        filename = normalised + ".png" if not normalised.endswith(".png") else normalised

        src: Path | None = None
        for d in search_dirs:
            candidate = d / filename
            if candidate.is_file():
                src = candidate
                break
            # Also try without underscore: FIG1.png
            candidate2 = d / (ref + ".png")
            if candidate2.is_file():
                src = candidate2
                break

        if src is None:
            if verbose:
                print(f"  [unity_export] WARNING: {filename} not found — skipping.")
            missing += 1
        else:
            shutil.copy2(src, dest_images / filename)
            if verbose:
                print(f"  [unity_export] Copied: {filename}")
            copied += 1

    return copied, missing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export Paper Cave pipeline output to Unity Assets/PaperCaveData/.",
    )
    parser.add_argument(
        "paper_id",
        help="Paper folder name (e.g. my_paper_2024)",
    )
    parser.add_argument(
        "--outputs-root",
        default="outputs",
        help="Path to the outputs/ directory (default: outputs/)",
    )
    parser.add_argument(
        "--assets-root",
        default=None,
        help="Path to the Unity Assets/ directory (default: auto-detected as ../Assets/)",
    )
    parser.add_argument(
        "--paper-folder",
        default=None,
        help="Path to the paper folder containing FIG_*.png files (default: papers/<paper_id>/)",
    )
    args = parser.parse_args()

    export_to_unity(
        paper_id=args.paper_id,
        outputs_root=Path(args.outputs_root),
        assets_root=Path(args.assets_root) if args.assets_root else None,
        paper_folder=Path(args.paper_folder) if args.paper_folder else None,
        verbose=True,
    )
