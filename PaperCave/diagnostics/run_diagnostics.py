#!/usr/bin/env python3
"""
PaperCave/diagnostics/run_diagnostics.py

Runs diagnostics on the figure extraction system for all papers.
1. Parses PDF text to find all expected figure captions.
2. Identifies extracted figures.
3. Matches extracted figures back onto the PDF page using OpenCV template matching.
4. Performs spatial position checks (heuristics) comparing figure bounding box to caption.
5. Saves diagnostic JSON files.
6. Generates a comprehensive side-by-side HTML report.
"""

import os
import re
import json
import io
import argparse
from pathlib import Path
import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image

# Setup Paths
DIAGNOSTICS_DIR = Path(__file__).parent
PAPERS_DIR = DIAGNOSTICS_DIR.parent / "papers"
VISUAL_REPORT_DIR = DIAGNOSTICS_DIR / "visual_report"

# Ensure directories exist
DIAGNOSTICS_DIR.mkdir(exist_ok=True)
VISUAL_REPORT_DIR.mkdir(exist_ok=True)

# Caption regex matching (same as image_extractor.py)
_CAPTION_START = re.compile(
    r"^\s*(?:[Ff]ig\.?\s*|[Ff]igure\s+|[Ff]igura\s+|FIG\.?\s*|FIGURE\s+|FIGURA\s+)(\d+(?:\([a-zA-Z]\))?|\d+[a-zA-Z]?)(?:[:.\-\u2013\u2014]|\s+[A-Z\"'\[({\*•]|\s*$)"
)

def extract_captions_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Scans PDF and extracts all captions matching figure patterns.
    Returns list of dicts: {fig_num, page_num (1-based), rect (x0,y0,x1,y1), text}
    """
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
            m = _CAPTION_START.match(text)
            if m:
                fig_num = (m.group(1) or "").upper()
                caption_rect = fitz.Rect(b[0], b[1], b[2], b[3])
                caption_text = text
                
                # Look ahead for multi-line caption continuations
                j = i + 1
                while j < len(text_blocks):
                    # Stop if current caption text already ends with a period
                    if caption_text.strip().endswith('.'):
                        break
                    # Stop if caption rectangle is getting too tall
                    if caption_rect.height > 75:
                        break
                        
                    next_b = text_blocks[j]
                    dy = next_b[1] - caption_rect.y1
                    if 0 <= dy < 15 and (next_b[0] < caption_rect.x1 + 20 and next_b[2] > caption_rect.x0 - 20):
                        # Stop if next block starts with uppercase and current ends with typical punctuation
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
                    "page_num": page_num,
                    "rect": [caption_rect.x0, caption_rect.y0, caption_rect.x1, caption_rect.y1],
                    "text": caption_text
                })
                i = j
            else:
                i += 1
                
    doc.close()
    return captions

def find_extracted_figures(paper_folder: Path) -> dict[str, Path]:
    """
    Finds all FIG_*.png and TAB_*.png in the paper folder.
    Returns dict mapping figure key (e.g. 'FIG_1', 'TAB_3_1') to image Path.
    """
    figs = {}
    for p in paper_folder.glob("FIG_*.png"):
        m = re.match(r"^(FIG_[a-zA-Z0-9_]+)\.png$", p.name)
        if m:
            fig_key = m.group(1).upper()
            figs[fig_key] = p
            
    for p in paper_folder.glob("TAB_*.png"):
        m = re.match(r"^(TAB_[a-zA-Z0-9_]+)\.png$", p.name)
        if m:
            fig_key = m.group(1).upper()
            figs[fig_key] = p
            
    return figs

def evaluate_layout_heuristics(fig_rect: list, caption_rect: list, page_width: float, page_height: float) -> tuple[str, str]:
    """
    Evaluates the spatial relationship between the figure rect and caption rect.
    Returns (status, notes) where status is 'ok', 'warning', or 'error'.
    """
    fx0, fy0, fx1, fy1 = fig_rect
    cx0, cy0, cx1, cy1 = caption_rect
    
    # 1. Overlap Check
    # Intersect rect
    ix0 = max(fx0, cx0)
    iy0 = max(fy0, cy0)
    ix1 = min(fx1, cx1)
    iy1 = min(fy1, cy1)
    
    if ix0 < ix1 and iy0 < iy1:
        # Overlap area
        overlap_area = (ix1 - ix0) * (iy1 - iy0)
        fig_area = (fx1 - fx0) * (fy1 - fy0)
        if overlap_area / fig_area > 0.05:
            return "error", "Figure overlaps with the caption text (more than 5%)."
            
    # 2. Vertical Distance Check
    # Standard: figure is above caption or below caption in vertical flow
    is_above = fy1 <= cy0 + 15
    is_below = fy0 >= cy1 - 15
    
    if not is_above and not is_below:
        # Figure is side-by-side or horizontally aligned
        return "warning", "Figure is side-by-side with caption, not above or below."
        
    vertical_distance = 0
    if is_above:
        vertical_distance = cy0 - fy1
    else:
        vertical_distance = fy0 - cy1
        
    if vertical_distance > 450:
        return "warning", f"Figure is very far vertically from its caption ({vertical_distance:.1f} pts)."
        
    # 3. Horizontal alignment / Column alignment
    # Check if they overlap horizontally
    hx0 = max(fx0, cx0)
    hx1 = min(fx1, cx1)
    has_horizontal_overlap = hx0 < hx1
    
    if not has_horizontal_overlap:
        # They are in completely different horizontal sections (different columns)
        return "error", "Figure and caption are in different columns (no horizontal overlap)."
        
    return "ok", "Layout looks valid (figure is aligned vertically with caption)."

def run_diagnostics_for_paper(paper_folder: Path, pdf_path: Path) -> dict:
    """
    Performs verification steps for a single paper.
    """
    print(f"Analyzing {paper_folder.name}...")
    
    # 1. Extract captions
    expected_captions = extract_captions_from_pdf(pdf_path)
    expected_nums = [c["fig_num"] for c in expected_captions]
    
    # 2. Find extracted figures
    extracted_figs = find_extracted_figures(paper_folder)
    
    # Build list of unique figure keys extracted
    extracted_keys = list(extracted_figs.keys())
    
    # Determine missing figures
    # A figure is missing if its core number (e.g. '3' from '3_1' or '3') is not in the extracted keys
    missing_figs = []
    for num in expected_nums:
        # Check if any extracted key starts with this figure number
        found = False
        for key in extracted_keys:
            if key == num or key.startswith(f"{num}_"):
                found = True
                break
        if not found:
            missing_figs.append(num)
            
    doc = fitz.open(str(pdf_path))
    details = []
    
    # Keep track of pages we need to render for the report
    pages_to_render = set()
    
    # Match extracted figures to pages
    for fig_key, fig_path in sorted(extracted_figs.items()):
        # Find which expected figure number this corresponds to
        parts = fig_key.split("_")
        if len(parts) > 2:
            base_num = f"{parts[0]}_{parts[1]}"
        else:
            base_num = fig_key
        
        caption_info = None
        for cap in expected_captions:
            if cap["fig_num"] == base_num:
                caption_info = cap
                break
        
        if not caption_info:
            details.append({
                "fig_key": fig_key,
                "fig_num": base_num,
                "page": 1,
                "caption_text": "No matching caption found in PDF text search.",
                "caption_bbox": [0, 0, 0, 0],
                "match_found": False,
                "match_score": 0.0,
                "matched_bbox": [0, 0, 0, 0],
                "heuristic_status": "error",
                "heuristic_notes": "No caption matching this figure number was found in text."
            })
            continue
            
        page_num = caption_info["page_num"]
        pages_to_render.add(page_num)
        page = doc[page_num - 1]
        
        # Render page at 2x scale (144 DPI)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        page_img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            page_img_np = cv2.cvtColor(page_img_np, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            page_img_np = cv2.cvtColor(page_img_np, cv2.COLOR_RGB2BGR)
            
        # Load figure image
        fig_img = cv2.imread(str(fig_path))
        if fig_img is None:
            details.append({
                "fig_key": fig_key,
                "fig_num": base_num,
                "page": page_num,
                "caption_text": caption_info["text"],
                "caption_bbox": caption_info["rect"],
                "match_found": False,
                "match_score": 0.0,
                "matched_bbox": [0, 0, 0, 0],
                "heuristic_status": "error",
                "heuristic_notes": f"Could not read figure file: {fig_path.name}"
            })
            continue
            
        # Convert to grayscale for template matching
        page_gray = cv2.cvtColor(page_img_np, cv2.COLOR_BGR2GRAY)
        fig_gray = cv2.cvtColor(fig_img, cv2.COLOR_BGR2GRAY)
        
        # Match template
        h_fig, w_fig = fig_gray.shape
        if h_fig > page_gray.shape[0] or w_fig > page_gray.shape[1]:
            details.append({
                "fig_key": fig_key,
                "fig_num": base_num,
                "page": page_num,
                "caption_text": caption_info["text"],
                "caption_bbox": caption_info["rect"],
                "match_found": False,
                "match_score": 0.0,
                "matched_bbox": [0, 0, 0, 0],
                "heuristic_status": "error",
                "heuristic_notes": f"Extracted figure dimensions ({w_fig}x{h_fig}) exceed page size."
            })
            continue
            
        res = cv2.matchTemplate(page_gray, fig_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        match_found = max_val >= 0.85
        
        # Bounding box in PDF coordinates (1x scale)
        fx0 = max_loc[0] / 2.0
        fy0 = max_loc[1] / 2.0
        fx1 = (max_loc[0] + w_fig) / 2.0
        fy1 = (max_loc[1] + h_fig) / 2.0
        matched_bbox = [fx0, fy0, fx1, fy1]
        
        if match_found:
            heuristic_status, heuristic_notes = evaluate_layout_heuristics(
                matched_bbox, caption_info["rect"], page.rect.width, page.rect.height
            )
        else:
            heuristic_status = "error"
            heuristic_notes = f"Figure not found on page {page_num} (best match score: {max_val:.2f})."
            
        details.append({
            "fig_key": fig_key,
            "fig_num": base_num,
            "page": page_num,
            "caption_text": caption_info["text"],
            "caption_bbox": caption_info["rect"],
            "match_found": match_found,
            "match_score": float(max_val),
            "matched_bbox": matched_bbox,
            "heuristic_status": heuristic_status,
            "heuristic_notes": heuristic_notes
        })
        
    # Render marked pages
    marked_pages = {}
    for p_num in pages_to_render:
        page = doc[p_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        page_img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            page_img_np = cv2.cvtColor(page_img_np, cv2.COLOR_RGBA2BGR)
        else:
            page_img_np = cv2.cvtColor(page_img_np, cv2.COLOR_RGB2BGR)
            
        for det in details:
            if det["page"] != p_num: continue
            cx0, cy0, cx1, cy1 = [int(val * 2) for val in det["caption_bbox"]]
            cv2.rectangle(page_img_np, (cx0, cy0), (cx1, cy1), (255, 127, 0), 2)
            if det["match_found"]:
                fx0, fy0, fx1, fy1 = [int(val * 2) for val in det["matched_bbox"]]
                color = (0, 255, 0) if det["heuristic_status"] == "ok" else (0, 255, 255) if det["heuristic_status"] == "warning" else (0, 0, 255)
                cv2.rectangle(page_img_np, (fx0, fy0), (fx1, fy1), color, 2)
        
        out_name = f"{paper_folder.name}_p{p_num}_marked.png"
        cv2.imwrite(str(VISUAL_REPORT_DIR / out_name), page_img_np)
        marked_pages[str(p_num)] = out_name
        
    doc.close()
    
    return {
        "paper_id": paper_folder.name,
        "pdf_name": pdf_path.name,
        "status": "errors" if any(d["heuristic_status"] != "ok" for d in details) else "ok",
        "marked_pages": marked_pages,
        "details": details
    }

def generate_html_report(results: list[dict]):
    html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>PaperCave Report</title>
    <style>
        body { font-family: sans-serif; background: #121212; color: #e0e0e0; padding: 20px; }
        .paper-section { background: #1e1e1e; padding: 20px; margin-bottom: 20px; border-radius: 8px; }
        .status-ok { color: #81c784; } .status-warning { color: #ffd54f; } .status-error { color: #e57373; }
        .side-by-side { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 10px; }
        .image-container { max-width: 450px; }
        .image-container img { max-width: 100%; border: 1px solid #444; }
    </style>
</head>
<body><h1>Diagnostics Report</h1>"""
    
    for r in results:
        paper_id = r["paper_id"]
        html_content += f'<div class="paper-section"><h2>Paper: {paper_id}</h2>'
        for det in r["details"]:
            
            if marked_page_img:
                html_content += f"""
                    <div class="image-container">
                        <img src="visual_report/{marked_page_img}" alt="Marked Page {det['page']}">
                        <div class="image-label">PDF Page {det['page']} (Cyan = Caption, Bounding Box = Figure)</div>
                    </div>
                """
            else:
                html_content += """
                    <div class="image-container" style="display:flex; align-items:center; justify-content:center; height:150px; color:#555;">
                        No page visual available
                    </div>
                """
                
            html_content += f"""
                    <div class="image-container">
                        <img src="{extracted_img_path}" alt="Extracted {det['fig_key']}">
                        <div class="image-label">Extracted image: {det['fig_key']}.png</div>
                    </div>
                </div>
            </div>
            """
            
        html_content += """
        </div>
        """
        
    html_content += """
    </div>
</body>
</html>
"""
    
    report_path = DIAGNOSTICS_DIR / "report.html"
    report_path.write_text(html_content, encoding="utf-8")
    print(f"\nHTML Diagnostic report successfully written to {report_path}")

def main():
    parser = argparse.ArgumentParser(description="Image Extraction Diagnostics Tool")
    parser.add_argument("--paper", default=None, help="Filter to only run diagnostics on papers containing this string.")
    args = parser.parse_args()
    
    # 1. Discover papers
    papers = []
    for entry in sorted(PAPERS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        # Find PDF
        pdfs = sorted(entry.glob("*.pdf"))
        if not pdfs:
            continue
            
        if args.paper:
            if args.paper.lower() not in entry.name.lower():
                continue
                
        papers.append((entry, pdfs[0]))
        
    if not papers:
        print("No papers discovered for diagnostics.")
        return
        
    results = []
    for paper_folder, pdf_path in papers:
        try:
            res = run_diagnostics_for_paper(paper_folder, pdf_path)
            results.append(res)
        except Exception as e:
            print(f"Error analyzing {paper_folder.name}: {e}")
            import traceback
            traceback.print_exc()
            
    if results:
        generate_html_report(results)

if __name__ == "__main__":
    main()
