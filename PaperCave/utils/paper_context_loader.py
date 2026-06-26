"""
utils/paper_context_loader.py
Loads all context needed before the Mapper runs:
  - Available paper figures (FIG1.png, FIG2.png, ...)
  - Figure captions extracted from the PDF text
  - Asset catalog (optional — from assets/catalog.md)
  - Visual style guide (mandatory — from assets/visual_style.md)

The context is injected into the Mapper task description via
_build_map_task_description(), replacing the placeholders defined
in prompts/tasks.yaml under the `map` key.
"""
import re
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent

# Matches FIG1.png, FIG_1.png, FIG2a.jpg, FIG_2a.jpg, FIG10.PNG, etc.
# The underscore separator is optional to support both FIG1 and FIG_1 conventions.
_FIG_PATTERN = re.compile(r"^FIG_?(\d+(?:_[0-9a-z]+)?)\.(png|jpg|jpeg)$", re.IGNORECASE)

# Matches "Fig. 3", "Figure 3", "Fig 3:", "Figura 3." in PDF text
_CAPTION_PATTERN = re.compile(
    r"(?:Fig\.?\s*|Figure\s+|Figura\s+)(\d+[a-z]?)[\.\:\s]+([^\n]{10,250})",
    re.IGNORECASE,
)


def scan_available_figures(paper_folder: Path) -> list[str]:
    """
    Returns a sorted list of figure IDs available in the paper folder.
    E.g. ['FIG1', 'FIG2', 'FIG3a', 'FIG3b']
    """
    figures = []
    for f in sorted(paper_folder.iterdir()):
        if f.is_file() and _FIG_PATTERN.match(f.name):
            fig_id = f"FIG{_FIG_PATTERN.match(f.name).group(1).upper()}"
            figures.append(fig_id)
    return figures


def extract_figure_captions(text: str, figure_ids: list[str]) -> dict[str, str]:
    """
    Extracts captions for each figure ID from the raw PDF text.
    Only captures captions for figures that are in figure_ids.
    Supports sub-figures (e.g. FIG1_1 gets caption of FIG1).
    Returns {FIG1_1: "caption text...", FIG2: "caption text...", ...}
    """
    captions: dict[str, str] = {}
    for match in _CAPTION_PATTERN.finditer(text):
        num    = match.group(1).upper()
        base_key = f"FIG{num}"
        text_m = match.group(2).strip()
        for fid in figure_ids:
            fid_base = fid.split("_")[0]
            if fid_base == base_key and fid not in captions:
                captions[fid] = text_m[:200]
    return captions


def load_paper_context(paper_folder: Path) -> dict:
    """
    Loads all injection context for the Mapper task.

    Returns a dict with:
      paper_folder:       Path                — the paper folder path
      available_figures:  list[str]          — ['FIG1', 'FIG2', ...]
      figure_captions:    dict[str, str]      — {FIG1: caption, ...} (empty until Reader runs)
      asset_catalog:      str | None          — content of assets/catalog.md or None
      visual_style:       str                 — content of assets/visual_style.md (mandatory)
    """
    available_figures = scan_available_figures(paper_folder)

    # Asset catalog (optional)
    catalog_path = BASE_DIR / "assets" / "catalog.md"
    asset_catalog = catalog_path.read_text(encoding="utf-8") if catalog_path.exists() else None

    # Visual style guide (mandatory — warn but don't crash if missing)
    style_path = BASE_DIR / "assets" / "visual_style.md"
    if style_path.exists():
        visual_style = style_path.read_text(encoding="utf-8")
    else:
        visual_style = (
            "Visual style: sci-fi educational aesthetic. "
            "Use blues (#00D4FF), golden (#FFB800 for contribution), "
            "neon green (#00FF88 for metrics), coral red (#FF4444 for problems)."
        )

    return {
        "paper_folder":      paper_folder,
        "available_figures": available_figures,
        "figure_captions":   {},   # populated later via update_figure_captions()
        "asset_catalog":     asset_catalog,
        "visual_style":      visual_style,
    }


def update_figure_captions(context: dict, pdf_text: str) -> None:
    """
    Populates context["figure_captions"] in-place after the PDF has been read.
    Preferentially loads from paper_folder/captions.txt if it exists.
    Otherwise falls back to extracting from pdf_text.
    """
    paper_folder = context.get("paper_folder")
    captions_txt_path = paper_folder / "captions.txt" if paper_folder else None
    
    if captions_txt_path and captions_txt_path.exists():
        try:
            content = captions_txt_path.read_text(encoding="utf-8")
            lines = [l.strip() for l in content.split("\n")]
            captions = {}
            
            i = 0
            while i < len(lines):
                filename = lines[i]
                m = _FIG_PATTERN.match(filename)
                if m:
                    fig_id = f"FIG{m.group(1).upper()}"
                    if i + 1 < len(lines):
                        caption_text = lines[i+1]
                        captions[fig_id] = caption_text
                        i += 3
                        continue
                i += 1
                
            if captions:
                context["figure_captions"] = captions
                return
        except Exception:
            pass
            
    # Fallback to regex-based extraction from PDF text
    context["figure_captions"] = extract_figure_captions(
        pdf_text, context["available_figures"]
    )


def _build_map_task_description(tp: dict, context: dict, card_count: int = 5) -> str:
    """
    Builds the final Mapper task description by injecting:
      - Card count
      - Available figures list (with captions when known)
      - Asset catalog (or a note that none is available)
      - Visual style guide

    Replaces the placeholders in tasks.yaml `map.description`:
      {card_count}
      {available_figures}
      {asset_catalog_section}
      {visual_style_section}
    """
    base = tp["map"]["description"]

    # ── Figures section ───────────────────────────────────────────────────────
    figs = context.get("available_figures", [])
    caps = context.get("figure_captions", {})

    if figs:
        lines = []
        for fig in figs:
            cap = caps.get(fig, "")
            lines.append(f"  - {fig}: {cap}" if cap else f"  - {fig}: (no caption extracted)")
        figures_text = "The following figures are available as FIG*.png files in the paper folder:\n" + "\n".join(lines)
    else:
        figures_text = (
            "No FIG*.png figures found in the paper folder. "
            "Do not use contentType='figure' for any card."
        )

    # ── Asset catalog section ─────────────────────────────────────────────────
    catalog = context.get("asset_catalog")
    if catalog:
        asset_text = (
            "AVAILABLE ASSETS IN THE UNITY PROJECT:\n"
            "The following assets are pre-installed and can be referenced by their exact name "
            "in the card's `content.assetReference` field. Use the exact name as shown in the catalog.\n\n"
            + catalog
        )
    else:
        asset_text = (
            "No asset catalog found (assets/catalog.md not present). "
            "For figure cards, use the figure ID (e.g., 'FIG1') as content.assetReference."
        )

    # ── Visual style section ──────────────────────────────────────────────────
    style_text = "VISUAL STYLE GUIDE:\n" + context.get("visual_style", "")

    return (
        base
        .replace("{card_count}",            str(card_count))
        .replace("{available_figures}",    figures_text)
        .replace("{asset_catalog_section}", asset_text)
        .replace("{visual_style_section}",  style_text)
    )
