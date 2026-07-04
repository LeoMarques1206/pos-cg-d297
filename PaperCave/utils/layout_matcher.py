import os
import re
import cv2
import fitz
import numpy as np
from pathlib import Path

# Caption regex matching (same as image_extractor.py)
_CAPTION_START = re.compile(
    r"^\s*(?:[Ff]ig\.?|[Ff]igure|[Ff]igura|FIG\.?|FIGURE|FIGURA)\s*(\d+(?:\([a-zA-Z]\))?|\d+[a-zA-Z]?|[IVXLC]+)(?:\s*[:.\-\u2013\u2014]|\s+[A-Z\"'\[({\*•]|\s*$)"
)
_TAB_CAPTION_START = re.compile(
    r"^\s*(?:[Tt]able|[Tt]abela|TABLE|TABELA)\s*(\d+(?:\([a-zA-Z]\))?|\d+[a-zA-Z]?|[IVXLC]+)(?:\s*[:.\-\u2013\u2014]|\s+[A-Z\"'\[({\*•]|\s*$)"
)

def extract_captions_from_pdf(pdf_path: Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    captions = []
    
    for page_num, page in enumerate(doc, 1):
        try:
            blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
            text_blocks = [b for b in blocks if b[6] == 0]
        except Exception:
            continue
            
        i = 0
        while i < len(text_blocks):
            b = text_blocks[i]
            text = b[4].replace("\n", " ").strip()
            
            # Match figure or table captions
            m_fig = _CAPTION_START.match(text)
            m_tab = _TAB_CAPTION_START.match(text)
            
            m = m_fig or m_tab
            
            if m:
                if m_fig:
                    fig_num = (m.group(1) or "").upper()
                    is_table = False
                else:
                    fig_num = (m.group(1) or "").upper()
                    is_table = True
                    
                caption_rect = fitz.Rect(b[0], b[1], b[2], b[3])
                caption_text = text
                
                # Look ahead for multi-line caption continuations
                j = i + 1
                while j < len(text_blocks):
                    if caption_text.strip().endswith('.'):
                        break
                    if caption_rect.height > 75:
                        break
                        
                    next_b = text_blocks[j]
                    dy = next_b[1] - caption_rect.y1
                    if 0 <= dy < 15 and (next_b[0] < caption_rect.x1 + 20 and next_b[2] > caption_rect.x0 - 20):
                        next_text = next_b[4].replace("\n", " ").strip()
                        if next_text and next_text[0].isupper() and caption_text.strip().endswith(('.', '!', '?')):
                            break
                            
                        caption_rect.include_point(fitz.Point(next_b[0], next_b[1]))
                        caption_rect.include_point(fitz.Point(next_b[2], next_b[3]))
                        caption_text += " " + next_text
                        j += 1
                    else:
                        break
                        
                caption_text = re.sub(r"\s{2,}", " ", caption_text).strip()
                captions.append({
                    "fig_num": fig_num,
                    "is_table": is_table,
                    "rect": [caption_rect.x0, caption_rect.y0, caption_rect.x1, caption_rect.y1],
                    "text": caption_text,
                    "page_num": page_num
                })
                i = j
            else:
                i += 1
                
    doc.close()
    return captions


def find_extracted_figures(paper_folder: Path) -> dict[str, dict]:
    """
    Finds all FIG_*.png and TAB_*.png in the paper folder.
    Returns dict mapping canonical 'suffix' key to a dict with file path and type.
    Example: 
      '1' -> {'path': Path('.../FIG_1.png'), 'type': 'figure'}
      'TAB_1' -> {'path': Path('.../TAB_1.png'), 'type': 'table'}
    """
    figs = {}
    for p in paper_folder.glob("FIG_*.png"):
        m = re.match(r"^FIG_([a-zA-Z0-9_]+)\.png$", p.name)
        if m:
            key_suffix = m.group(1).upper()
            figs[("figure", key_suffix)] = {"path": p, "type": "figure"}
            
    for p in paper_folder.glob("TAB_*.png"):
        m = re.match(r"^TAB_([a-zA-Z0-9_]+)\.png$", p.name)
        if m:
            key_suffix = m.group(1).upper()
            figs[("table", key_suffix)] = {"path": p, "type": "table"}
            
    return figs


def evaluate_layout_heuristics(fig_rect: list, caption_rect: list) -> tuple[str, str]:
    fx0, fy0, fx1, fy1 = fig_rect
    cx0, cy0, cx1, cy1 = caption_rect
    
    # 1. Overlap Check
    ix0 = max(fx0, cx0)
    iy0 = max(fy0, cy0)
    ix1 = min(fx1, cx1)
    iy1 = min(fy1, cy1)
    
    if ix0 < ix1 and iy0 < iy1:
        overlap_area = (ix1 - ix0) * (iy1 - iy0)
        fig_area = (fx1 - fx0) * (fy1 - fy0)
        if overlap_area / fig_area > 0.05:
            return "error", "Figure overlaps with the caption text (more than 5%)."
            
    # 2. Vertical Distance Check
    is_above = fy1 <= cy0 + 15
    is_below = fy0 >= cy1 - 15
    
    if not is_above and not is_below:
        return "warning", "Figure is side-by-side with caption, not above or below."
        
    vertical_distance = 0
    if is_above:
        vertical_distance = cy0 - fy1
    else:
        vertical_distance = fy0 - cy1
        
    if vertical_distance > 450:
        return "warning", f"Figure is very far vertically from its caption ({vertical_distance:.1f} pts)."
        
    # 3. Horizontal alignment
    hx0 = max(fx0, cx0)
    hx1 = min(fx1, cx1)
    if hx0 >= hx1:
        return "error", "Figure and caption are in different columns (no horizontal overlap)."
        
    return "ok", "Layout looks valid."


def find_image_layouts_in_pdf(paper_folder: Path, pdf_path: Path) -> dict:
    """
    Matches extracted figures (FIG_*.png and TAB_*.png) back to the PDF using OpenCV.
    Returns the JSON-compatible structure with precise bounding boxes.
    """
    # 1. Load Expected Captions by parsing the PDF directly to get bounding boxes
    expected_captions = extract_captions_from_pdf(pdf_path)
    expected_nums = [(c["fig_num"], c["is_table"]) for c in expected_captions]
    
    # 2. Find extracted PNGs
    extracted_figs = find_extracted_figures(paper_folder)
    extracted_keys = list(extracted_figs.keys())
    
    # 3. Find missing items
    missing_figs = []
    for num, is_tab in expected_nums:
        found = False
        for key_type, key_num in extracted_keys:
            if (key_type == "table") == is_tab:
                if key_num == num or key_num.startswith(f"{num}_"):
                    found = True
                    break
        if not found:
            prefix = "TAB_" if is_tab else ""
            missing_figs.append(f"{prefix}{num}")
            
    doc = fitz.open(str(pdf_path))
    details = []
    
    for (fig_type, base_num), fig_info in sorted(extracted_figs.items()):
        fig_path = fig_info["path"]
        is_table = fig_type == "table"
        fig_key = base_num
        
        parts = fig_key.split("_")
        base_num = parts[0] if len(parts) > 1 else fig_key
        
        # Match with caption
        caption_info = None
        for cap in expected_captions:
            if cap["fig_num"] == base_num and cap["is_table"] == is_table:
                caption_info = cap
                break
                
        if not caption_info:
            details.append({
                "fig_key": fig_key,
                "fig_num": base_num,
                "is_table": is_table,
                "page": 1,
                "caption_text": "Not found in captions.txt",
                "caption_bbox": None,
                "match_found": False,
                "matched_bbox": None,
                "heuristic_status": "error",
                "heuristic_notes": "No matching caption found."
            })
            continue
            
        page_num = caption_info["page_num"]
        page = doc[page_num - 1]
        
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        page_img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            page_img_np = cv2.cvtColor(page_img_np, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            page_img_np = cv2.cvtColor(page_img_np, cv2.COLOR_RGB2BGR)
            
        fig_img = cv2.imread(str(fig_path))
        if fig_img is None:
            details.append({
                "fig_key": fig_key,
                "fig_num": base_num,
                "is_table": is_table,
                "page": page_num,
                "caption_text": caption_info["text"],
                "caption_bbox": caption_info["rect"],
                "match_found": False,
                "matched_bbox": None,
                "heuristic_status": "error",
                "heuristic_notes": f"Could not read figure file: {fig_path.name}"
            })
            continue
            
        page_gray = cv2.cvtColor(page_img_np, cv2.COLOR_BGR2GRAY)
        fig_gray = cv2.cvtColor(fig_img, cv2.COLOR_BGR2GRAY)
        
        h_fig, w_fig = fig_gray.shape
        if h_fig > page_gray.shape[0] or w_fig > page_gray.shape[1]:
            details.append({
                "fig_key": fig_key,
                "fig_num": base_num,
                "is_table": is_table,
                "page": page_num,
                "caption_text": caption_info["text"],
                "caption_bbox": caption_info["rect"],
                "match_found": False,
                "matched_bbox": None,
                "heuristic_status": "error",
                "heuristic_notes": "Figure dimensions exceed page size."
            })
            continue
            
        res = cv2.matchTemplate(page_gray, fig_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        match_found = max_val >= 0.85
        
        fx0 = max_loc[0] / 2.0
        fy0 = max_loc[1] / 2.0
        fx1 = (max_loc[0] + w_fig) / 2.0
        fy1 = (max_loc[1] + h_fig) / 2.0
        matched_bbox = [fx0, fy0, fx1, fy1]
        
        if match_found:
            h_stat, h_notes = evaluate_layout_heuristics(matched_bbox, caption_info["rect"])
        else:
            h_stat = "error"
            h_notes = f"Template match failed (score: {max_val:.2f})"
            matched_bbox = None # Reset bbox on failure so it doesn't render garbage
            
        details.append({
            "fig_key": fig_key,
            "fig_num": base_num,
            "is_table": is_table,
            "page": page_num,
            "caption_text": caption_info["text"],
            "caption_bbox": caption_info["rect"],
            "match_found": match_found,
            "match_score": float(max_val),
            "matched_bbox": matched_bbox,
            "heuristic_status": h_stat,
            "heuristic_notes": h_notes
        })
        
    doc.close()
    
    # Restore the full expected dictionary structure that the UI counts rely on
    return {
        "paper_id": paper_folder.name,
        "pdf_name": pdf_path.name,
        "status": "errors" if any(d["heuristic_status"] != "ok" for d in details) else "ok",
        "summary": f"Processed {len(details)} images.",
        "figures_expected": expected_nums,
        "figures_extracted": extracted_keys,
        "missing_figures": missing_figs,
        "marked_pages": {}, # Deprecated visual report
        "details": details
    }
