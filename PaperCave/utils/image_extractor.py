"""
utils/image_extractor.py
Canonical figure extraction from academic paper PDFs.

Extracts figures using a Caption-Driven approach. It locates captions in the PDF text,
defines the figure region (above or below the caption) by grouping vector drawings and
physical images, renders the region as a high-quality print, and slices any germinated
sub-figures horizontally and vertically using a grid-aware layout analysis.
"""
import re
import fitz  # pymupdf
from pathlib import Path
from PIL import Image
import io

MIN_WIDTH  = 80
MIN_HEIGHT = 80
MAX_CAPTION_CHARS = 500   # truncate very long captions

_CAPTION_START = re.compile(
    r"^\s*(?:[Ff]ig\.?\s*|[Ff]igure\s+|[Ff]igura\s+|FIG\.?\s*|FIGURE\s+|FIGURA\s+)(\d+(?:\([a-zA-Z]\))?|\d+[a-zA-Z]?)(?:[:.\-\u2013\u2014]|\s+[A-Z\"'\[({\*•]|\s*$)"
)

# ── Column-Aware Page Analysis Helper Functions ──────────────────────────────

def are_captions_in_same_column(cap1_rect, cap2_rect, page_width: float) -> bool:
    mid_x = page_width / 2
    cap1_left = cap1_rect.x1 < mid_x + 30
    cap1_right = cap1_rect.x0 > mid_x - 30
    cap2_left = cap2_rect.x1 < mid_x + 30
    cap2_right = cap2_rect.x0 > mid_x - 30
    
    # If either spans across the middle flow (full-width), they share vertical context
    if (not cap1_left and not cap1_right) or (not cap2_left and not cap2_right):
        return True
        
    # If one is left and the other is right, they are in different columns
    if (cap1_left and cap2_right) or (cap1_right and cap2_left):
        return False
        
    return True


def is_in_same_column(rect, caption_rect, page_width: float) -> bool:
    mid_x = page_width / 2
    cap_left = caption_rect.x1 < mid_x + 30
    cap_right = caption_rect.x0 > mid_x - 30
    
    # Full-width caption can match components anywhere horizontally
    if not cap_left and not cap_right:
        return True
        
    rect_left = rect.x1 < mid_x + 10
    rect_right = rect.x0 > mid_x - 10
    
    if cap_left:
        # Caption is left, ignore right-column components
        return not rect_right
    if cap_right:
        # Caption is right, ignore left-column components
        return not rect_left
        
    return True

# ── Symmetry-Aware Grid Slicing ──────────────────────────────────────────────

def slice_block_vertically(img: Image.Image, min_blank_width: int, tolerance: int) -> list[Image.Image]:
    w, h = img.size
    img_rgb = img.convert("RGB")
    pixels = img_rgb.load()
    
    blank_cols = []
    for x in range(w):
        non_white = 0
        for y in range(h):
            r, g, b = pixels[x, y]
            if r < tolerance or g < tolerance or b < tolerance:
                non_white += 1
        # Noise-tolerant check: allows up to 1% of column pixels to be non-white
        blank_cols.append(non_white <= max(1, int(0.01 * h)))
        
    gaps = []
    in_gap = False
    start = 0
    for i in range(w):
        if blank_cols[i]:
            if not in_gap:
                start = i
                in_gap = True
        else:
            if in_gap:
                gaps.append((start, i, i - start))
                in_gap = False
    if in_gap:
        gaps.append((start, w, w - start))
        
    valid_gaps = [g for g in gaps if g[0] > 5 and g[1] < w - 5 and g[2] >= min_blank_width]
    if not valid_gaps:
        return [img]
        
    parts = []
    prev_x = 0
    split_points = [g[0] + g[2]//2 for g in valid_gaps] + [w]
    
    # Pre-check all parts for safety
    for sx in split_points:
        pw = sx - prev_x
        # If any cell is too small or aspect ratio is extreme, reject slicing
        if pw < 50:
            return [img]
        aspect = pw / h
        if aspect < 0.22 or aspect > 4.5:
            return [img]
        prev_x = sx
        
    # Slicing is safe, crop columns
    prev_x = 0
    for sx in split_points:
        parts.append(img.crop((prev_x, 0, sx, h)))
        prev_x = sx
    return parts


def slice_block_horizontally(img: Image.Image, min_blank_height: int, tolerance: int) -> list[Image.Image]:
    w, h = img.size
    img_rgb = img.convert("RGB")
    pixels = img_rgb.load()
    
    blank_rows = []
    for y in range(h):
        non_white = 0
        for x in range(w):
            r, g, b = pixels[x, y]
            if r < tolerance or g < tolerance or b < tolerance:
                non_white += 1
        blank_rows.append(non_white <= max(1, int(0.01 * w)))
        
    gaps = []
    in_gap = False
    start = 0
    for i in range(h):
        if blank_rows[i]:
            if not in_gap:
                start = i
                in_gap = True
        else:
            if in_gap:
                gaps.append((start, i, i - start))
                in_gap = False
    if in_gap:
        gaps.append((start, h, h - start))
        
    valid_gaps = [g for g in gaps if g[0] > 5 and g[1] < h - 5 and g[2] >= min_blank_height]
    if not valid_gaps:
        return [img]
        
    parts = []
    prev_y = 0
    split_points = [g[0] + g[2]//2 for g in valid_gaps] + [h]
    
    # Pre-check all parts for safety
    for sy in split_points:
        ph = sy - prev_y
        if ph < 50:
            return [img]
        aspect = w / ph
        if aspect < 0.22 or aspect > 4.5:
            return [img]
        prev_y = sy
        
    # Slicing is safe, crop rows
    prev_y = 0
    for sy in split_points:
        parts.append(img.crop((0, prev_y, w, sy)))
        prev_y = sy
    return parts


def slice_block(img: Image.Image, min_blank_width: int = 5, tolerance: int = 245) -> list[Image.Image]:
    w, h = img.size
    if w < 150 or h < 150:
        return [img]
        
    img_rgb = img.convert("RGB")
    pixels = img_rgb.load()
    
    # Calculate non-white pixel density to identify graphs/charts
    non_white_count = 0
    for x in range(w):
        for y in range(h):
            r, g, b = pixels[x, y]
            if r < tolerance or g < tolerance or b < tolerance:
                non_white_count += 1
    density = non_white_count / (w * h)
    
    # Graphs and sparse diagrams have low density (< 20%) and should not be sliced
    if density < 0.20:
        return [img]
        
    blank_cols = []
    for x in range(w):
        non_white = 0
        for y in range(h):
            r, g, b = pixels[x, y]
            if r < tolerance or g < tolerance or b < tolerance:
                non_white += 1
        blank_cols.append(non_white <= max(1, int(0.01 * h)))
        
    blank_rows = []
    for y in range(h):
        non_white = 0
        for x in range(w):
            r, g, b = pixels[x, y]
            if r < tolerance or g < tolerance or b < tolerance:
                non_white += 1
        blank_rows.append(non_white <= max(1, int(0.01 * w)))
        
    def find_gaps(is_blank, length):
        gaps = []
        in_gap = False
        start = 0
        for i in range(length):
            if is_blank[i]:
                if not in_gap:
                    start = i
                    in_gap = True
            else:
                if in_gap:
                    gaps.append((start, i, i - start))
                    in_gap = False
        if in_gap:
            gaps.append((start, length, length - start))
        return gaps
        
    col_gaps = find_gaps(blank_cols, w)
    row_gaps = find_gaps(blank_rows, h)
    
    # Filter gaps (ignore margins)
    valid_col_gaps = [g for g in col_gaps if g[0] > 5 and g[1] < w - 5 and g[2] >= min_blank_width]
    valid_row_gaps = [g for g in row_gaps if g[0] > 5 and g[1] < h - 5 and g[2] >= min_blank_width]
    
    # Slicing decisions
    if not valid_col_gaps and not valid_row_gaps:
        return [img]
        
    # If both are present, slice horizontally (rows) first, then vertically per row
    if valid_row_gaps and valid_col_gaps:
        row_images = []
        prev_y = 0
        split_y = [g[0] + g[2]//2 for g in valid_row_gaps] + [h]
        for sy in split_y:
            row_img = img.crop((0, prev_y, w, sy))
            row_images.append(row_img)
            prev_y = sy
            
        final_cells = []
        for r_img in row_images:
            final_cells.extend(slice_block_vertically(r_img, min_blank_width, tolerance))
        return final_cells
        
    elif valid_col_gaps:
        return slice_block_vertically(img, min_blank_width, tolerance)
    else:
        return slice_block_horizontally(img, min_blank_width, tolerance)


def _split_germinated_image(image_bytes: bytes, min_blank_width: int = 5, tolerance: int = 245) -> list[bytes]:
    """
    Tries to slice a composite/germinated image into sub-figures based on grid layout analysis.
    Returns a list of image bytes for each slice. If no slice is performed, returns [image_bytes].
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        parts = slice_block(img, min_blank_width, tolerance)
        if len(parts) <= 1:
            return [image_bytes]
            
        out_bytes_list = []
        for p in parts:
            out = io.BytesIO()
            p.save(out, format="PNG")
            out_bytes_list.append(out.getvalue())
        return out_bytes_list
    except Exception:
        return [image_bytes]


# ── Cleanup ────────────────────────────────────────────────────────────────────

def _clear_figures(paper_folder: Path, verbose: bool) -> None:
    """Remove all FIG_*.png and captions.txt from the paper folder."""
    to_remove = set(paper_folder.glob("FIG*.png"))
    if verbose and to_remove:
        print(f"    Removendo {len(to_remove)} FIG*.png anteriores.")
    for f in to_remove:
        f.unlink()
    cap = paper_folder / "captions.txt"
    if cap.exists():
        cap.unlink()


# ── Main public function ───────────────────────────────────────────────────────

def extract_figures_from_pdf(
    paper_folder: Path,
    pdf_path: Path,
    min_width: int = MIN_WIDTH,
    min_height: int = MIN_HEIGHT,
    verbose: bool = True,
) -> dict[str, str]:
    """
    Extract figures and graphs from a PDF using a Caption-Driven layout analysis.
    Renders high-quality regions encompassing drawings and physical images.
    Saves to paper_folder:
      - FIG_<N>.png / FIG_<N>_<X>.png
      - captions.txt
    Returns dict mapping fig_number string → caption text.
    """
    _clear_figures(paper_folder, verbose)

    doc = fitz.open(str(pdf_path))
    captions: dict[str, str] = {}
    
    for page_num, page in enumerate(doc, 1):
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []
        try:
            images = page.get_image_info(hashes=False)
        except Exception:
            images = []
            
        # Extract and sort text blocks to find captions
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        text_blocks = [b for b in blocks if b[6] == 0]
        
        captions_on_page = []
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
                    next_b = text_blocks[j]
                    dy = next_b[1] - caption_rect.y1
                    if 0 <= dy < 15 and (next_b[0] < caption_rect.x1 + 20 and next_b[2] > caption_rect.x0 - 20):
                        caption_rect.include_point(fitz.Point(next_b[0], next_b[1]))
                        caption_rect.include_point(fitz.Point(next_b[2], next_b[3]))
                        caption_text += " " + next_b[4].replace("\n", " ").strip()
                        j += 1
                    else:
                        break
                caption_text = re.sub(r"\s{2,}", " ", caption_text).strip()
                captions_on_page.append({
                    "fig_num": fig_num,
                    "rect": caption_rect,
                    "text": caption_text
                })
                i = j
            else:
                i += 1
                
        # Process each caption
        for cap in captions_on_page:
            fig_num = cap["fig_num"]
            caption_rect = cap["rect"]
            caption_text = cap["text"]
            
            # Determine the search band ABOVE the caption
            y_max_above = caption_rect.y0 - 2
            y_min_above = 40
            for other_cap in captions_on_page:
                if other_cap != cap:
                    if are_captions_in_same_column(caption_rect, other_cap["rect"], page.rect.width):
                        or_rect = other_cap["rect"]
                        if or_rect.y1 < caption_rect.y0:
                            y_min_above = max(y_min_above, or_rect.y1)
                        
            above_rects = []
            for d in drawings:
                dr = d["rect"]
                # Ignore full-page border lines or backgrounds
                if dr.width > page.rect.width - 40 and dr.height > page.rect.height - 40:
                    continue
                if dr.width > page.rect.width - 60 and dr.height < 5:
                    continue
                if dr.y0 >= y_min_above and dr.y1 <= y_max_above + 5:
                    if is_in_same_column(dr, caption_rect, page.rect.width):
                        above_rects.append(dr)
            for img in images:
                ir = fitz.Rect(img["bbox"])
                if ir.y0 >= y_min_above and ir.y1 <= y_max_above + 5:
                    if is_in_same_column(ir, caption_rect, page.rect.width):
                        above_rects.append(ir)
                    
            union_rect = None
            if above_rects:
                union_rect = fitz.Rect(above_rects[0])
                for r in above_rects[1:]:
                    union_rect.include_point(fitz.Point(r.x0, r.y0))
                    union_rect.include_point(fitz.Point(r.x1, r.y1))
                # Add horizontal/vertical padding
                union_rect.x0 = max(0, union_rect.x0 - 5)
                union_rect.y0 = max(y_min_above, union_rect.y0 - 5)
                union_rect.x1 = min(page.rect.width, union_rect.x1 + 5)
                union_rect.y1 = min(caption_rect.y0 - 2, union_rect.y1 + 5)
            else:
                # Try finding components BELOW the caption (typical for tables)
                y_min_below = caption_rect.y1 + 2
                y_max_below = page.rect.height - 40
                for other_cap in captions_on_page:
                    if other_cap != cap:
                        if are_captions_in_same_column(caption_rect, other_cap["rect"], page.rect.width):
                            or_rect = other_cap["rect"]
                            if or_rect.y0 > caption_rect.y1:
                                y_max_below = min(y_max_below, or_rect.y0)
                            
                below_rects = []
                for d in drawings:
                    dr = d["rect"]
                    if dr.width > page.rect.width - 40 and dr.height > page.rect.height - 40:
                        continue
                    if dr.width > page.rect.width - 60 and dr.height < 5:
                        continue
                    if dr.y0 >= y_min_below - 5 and dr.y1 <= y_max_below:
                        if is_in_same_column(dr, caption_rect, page.rect.width):
                            below_rects.append(dr)
                for img in images:
                    ir = fitz.Rect(img["bbox"])
                    if ir.y0 >= y_min_below - 5 and ir.y1 <= y_max_below:
                        if is_in_same_column(ir, caption_rect, page.rect.width):
                            below_rects.append(ir)
                        
                if below_rects:
                    union_rect = fitz.Rect(below_rects[0])
                    for r in below_rects[1:]:
                        union_rect.include_point(fitz.Point(r.x0, r.y0))
                        union_rect.include_point(fitz.Point(r.x1, r.y1))
                    union_rect.x0 = max(0, union_rect.x0 - 5)
                    union_rect.y0 = max(caption_rect.y1 + 2, union_rect.y0 - 5)
                    union_rect.x1 = min(page.rect.width, union_rect.x1 + 5)
                    union_rect.y1 = min(y_max_below, union_rect.y1 + 5)
                    
            if not union_rect or union_rect.width < 10 or union_rect.height < 10:
                # Fallback to the region above the caption
                union_rect = fitz.Rect(
                    max(0, caption_rect.x0 - 20),
                    max(40, caption_rect.y0 - 220),
                    min(page.rect.width, caption_rect.x1 + 20),
                    caption_rect.y0 - 2
                )
                
            try:
                # Render using clip at 2x scale (144 DPI)
                pix = page.get_pixmap(clip=union_rect, matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
            except Exception as e:
                if verbose:
                    print(f"    [Extractor] Erro ao renderizar FIG_{fig_num}: {e}")
                continue
                
            parts = _split_germinated_image(img_bytes)
            
            if len(parts) == 1:
                dest = paper_folder / f"FIG_{fig_num}.png"
                dest.write_bytes(parts[0])
                captions[fig_num] = caption_text
                if verbose:
                    print(f"    FIG_{fig_num}.png  (pág.{page_num})  {caption_text[:72]}")
            else:
                for idx, part_bytes in enumerate(parts, 1):
                    sub_fig_num = f"{fig_num}_{idx}"
                    dest = paper_folder / f"FIG_{sub_fig_num}.png"
                    dest.write_bytes(part_bytes)
                    captions[sub_fig_num] = caption_text
                    if verbose:
                        print(f"    FIG_{sub_fig_num}.png  (composta/cortada, pág.{page_num})  {caption_text[:72]}")
                        
    doc.close()
    
    if captions:
        lines = []
        for num in sorted(captions, key=lambda x: (len(x), x)):
            lines.append(f"FIG_{num}.png")
            lines.append(captions[num])
            lines.append("")
        (paper_folder / "captions.txt").write_text(
            "\n".join(lines), encoding="utf-8"
        )
        
    if verbose:
        print(f"    Total: {len(captions)} figura(s) extraída(s).")
        
    return captions


# ── Legacy shim ────────────────────────────────────────────────────────────────

def load_image_bytes(raw_dir: Path, raw_filename: str) -> bytes:
    return (raw_dir / raw_filename).read_bytes()
