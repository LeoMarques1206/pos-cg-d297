#!/usr/bin/env python3
"""
PaperCave/diagnostics/app.py

Flask Backend for the interactive bounding box editor.
Serves paper lists, page rendering API, and handles saving manual bounding box corrections.
Now updated to support editable captions, guided sessions, figure/image counts, and study report exports.
"""

import os
import json
import random
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, abort
import fitz  # PyMuPDF
import sys
import queue
import threading
import time
import subprocess
from datetime import datetime

# Setup Paths
DIAGNOSTICS_DIR = Path(__file__).parent
PAPERS_DIR = DIAGNOSTICS_DIR.parent / "papers"

# Ensure directories exist
DIAGNOSTICS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

# --- Background Pipeline Running State & Logic ---
class PipelineJob:
    def __init__(self, paper_ids, simulate, from_step, simple_mode):
        self.paper_ids = paper_ids
        self.simulate = simulate
        self.from_step = from_step
        self.simple_mode = simple_mode
        self.current_index = 0
        self.total_papers = len(paper_ids)
        self.log_queue = queue.Queue()
        self.status = "running"  # "running", "completed", "failed"
        self.start_time = time.time()
        self.current_paper_start_time = time.time()
        self.current_paper_id = ""
        self.elapsed_time = 0.0
        self.estimated_remaining = 0.0
        self.thread = None
        self.cancelled = False
        self.current_process = None
        self.failed_papers = []

current_job = None

def run_simulated_paper(paper_id, job):
    import random
    
    job.log_queue.put(f"[SIMULATOR] Iniciando extração simulada para: {paper_id}")
    time.sleep(0.5)
    
    steps = [
        ("Reader", "extraindo texto do PDF"),
        ("Vision Analyst", "analisando FIG*.png pré-extraídas"),
        ("Summarizer", "gerando resumo do paper"),
        ("Extractor", "extraindo entidades"),
        ("Mapper/Reviewer", "mapeando componentes e validando")
    ]
    
    for idx, (agent_name, task_desc) in enumerate(steps, 1):
        if job.cancelled:
            return False
        job.log_queue.put(f"  +- [{idx}/6] {agent_name} — {task_desc}...")
        time.sleep(1.0)
        job.log_queue.put(f"  +- ✓ done ({random.randint(1, 3)}s)")
        
    if job.cancelled:
        return False
        
    out_dir = PAPERS_DIR.parent / "outputs" / paper_id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    mock_manifest = {
        "paperTitle": paper_id.replace("_", " ").title(),
        "centralContribution": "Esta contribuição foi gerada por meio de uma execução simulada para economizar tokens.",
        "unitCount": 2,
        "units": [
            {
                "unit_id": "unit_01",
                "display_name": "Simulated Asset 1",
                "description": "Primeiro ativo mockado.",
                "whyThisUnit": "Raciocínio simulado",
                "contentType": "figure",
                "content_ref": "FIG_1.png"
            },
            {
                "unit_id": "unit_02",
                "display_name": "Simulated Asset 2",
                "description": "Segundo ativo mockado.",
                "whyThisUnit": "Raciocínio simulado",
                "contentType": "figure",
                "content_ref": "FIG_2.png"
            }
        ],
        "objectScores": [
            {"suggestedName": "Simulated Asset 1", "score": 0.98, "confidence": "high", "feedback": ""},
            {"suggestedName": "Simulated Asset 2", "score": 0.95, "confidence": "high", "feedback": ""}
        ],
        "totalAttempts": 1,
        "assembledFromMultipleAttempts": False
    }
    
    # Save files to mark paper as processed
    with open(out_dir / "06_mapper_output.json", "w", encoding="utf-8") as f:
        json.dump(mock_manifest, f, indent=2, ensure_ascii=False)
        
    for step in ["01_reader_output", "03_vision_insights", "04_summarizer_output", "05_extractor_output"]:
        with open(out_dir / f"{step}.json", "w", encoding="utf-8") as f:
            json.dump({"simulated": True}, f)
            
    # Mock export to Unity
    job.log_queue.put(f"  [SIMULATOR] Exportando ativos para Assets/PaperCaveData/{paper_id}/...")
    time.sleep(0.5)
    try:
        from utils.unity_asset_exporter import export_assets_to_unity
        export_assets_to_unity(
            paper_id=paper_id,
            paper_folder=PAPERS_DIR / paper_id,
            unity_project_root=PAPERS_DIR.parent.parent
        )
        job.log_queue.put("  [SIMULATOR] ✓ Exportação Unity finalizada com sucesso!")
    except Exception as e:
        job.log_queue.put(f"  [SIMULATOR] ✗ Exportação Unity falhou: {e}")
        
    job.log_queue.put(f"[SIMULATOR] Finalizado paper: {paper_id}")
    return True

def run_real_paper(paper_id, job):
    job.log_queue.put(f"[PIPELINE] Iniciando pipeline de agentes real para: {paper_id}")
    
    cmd = [sys.executable, str(PAPERS_DIR.parent / "main.py"), "run", "--paper", paper_id]
    if job.from_step:
        cmd.extend(["--from-step", job.from_step])
    if job.simple_mode:
        cmd.append("--simple")
        
    job.log_queue.put(f"[PIPELINE] Executando comando: {' '.join(cmd)}")
    
    if job.cancelled:
        return False
        
    try:
        # Pass non-interactive environment variables to bypass prompt
        env = os.environ.copy()
        env["PAPERCAVE_NON_INTERACTIVE"] = "1"
        if getattr(job, "force_fresh", False):
            env["PAPERCAVE_FORCE_FRESH"] = "1"
            
        # Use errors="replace" to prevent UnicodeDecodeError crashes when reading em-dashes or other cp1252 characters
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(PAPERS_DIR.parent),
            env=env
        )
        job.current_process = process
        
        for line in iter(process.stdout.readline, ""):
            if job.cancelled:
                try:
                    process.terminate()
                except Exception:
                    pass
                return False
            if line:
                job.log_queue.put(line.strip())
                
        process.stdout.close()
        code = process.wait()
        
        job.current_process = None
        
        if code == 0:
            job.log_queue.put(f"[PIPELINE] ✓ Paper {paper_id} concluído com código 0.")
            return True
        else:
            job.log_queue.put(f"[PIPELINE] ✗ Pipeline falhou com código de erro {code}.")
            return False
    except Exception as e:
        job.log_queue.put(f"[PIPELINE] ✗ Erro crítico ao invocar subprocesso: {e}")
        job.current_process = None
        return False

def background_pipeline_runner(job):
    for i, paper_id in enumerate(job.paper_ids):
        if job.cancelled:
            break
            
        job.current_index = i
        job.current_paper_id = paper_id
        job.current_paper_start_time = time.time()
        job.log_queue.put(f"\n=================== PROCESSANDO PAPER [{i+1}/{job.total_papers}]: {paper_id} ===================")
        
        # Automatic retries on failure (up to 3 attempts)
        max_attempts = 1 if job.simulate else 3
        success = False
        
        for attempt in range(1, max_attempts + 1):
            if job.cancelled:
                break
                
            if attempt > 1:
                job.log_queue.put(f"\n[PIPELINE] ⚠️ Tentativa {attempt}/{max_attempts} para o paper: {paper_id}...")
                time.sleep(2.0)
                
            if job.simulate:
                success = run_simulated_paper(paper_id, job)
            else:
                success = run_real_paper(paper_id, job)
                
            if success:
                break
                
        if not success:
            if job.cancelled:
                job.log_queue.put(f"[CONTROL] Processamento cancelado para o paper: {paper_id}")
                break
            else:
                job.log_queue.put(f"[ERRO] Paper '{paper_id}' falhou após {max_attempts} tentativas. Pulando...")
                job.failed_papers.append(paper_id)
                
    if job.cancelled:
        job.status = "failed"
        job.log_queue.put("\n[CANCELADO] O processamento em lote foi interrompido pelo usuário.")
    else:
        job.current_index = job.total_papers
        job.estimated_remaining = 0.0
        if job.failed_papers:
            job.status = "failed"
            job.log_queue.put(f"\n[FALHA] Processamento finalizado. Papers com falhas: {', '.join(job.failed_papers)}")
        else:
            job.status = "completed"
            job.log_queue.put("\n[SUCESSO] Processamento em lote concluído para todos os papers!")

# Serve dashboard.html at root
@app.route("/")
def index():
    return send_from_directory(DIAGNOSTICS_DIR / "templates", "dashboard.html")

# Serve index.html (bounding box editor) at /editor
@app.route("/editor")
def editor():
    return send_from_directory(DIAGNOSTICS_DIR / "templates", "index.html")

# Serve other static files
@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory(DIAGNOSTICS_DIR / "static", path)

# Serve files from the papers directory (specifically extracted figures)
@app.route("/papers/<paper_id>/<filename>")
def serve_paper_file(paper_id, filename):
    paper_dir = PAPERS_DIR / paper_id
    if not paper_dir.exists():
        abort(404)
    if not filename.endswith(".png") and not filename.endswith(".txt"):
        abort(403)
    return send_from_directory(paper_dir, filename)

@app.route("/api/papers")
def list_papers():
    """
    Lists all papers with their diagnostic status and distinct figure vs image counts.
    """
    papers_list = []
    for entry in sorted(PAPERS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        
        pdfs = sorted(entry.glob("*.pdf"))
        if not pdfs:
            continue
            
        paper_id = entry.name
        
        extracted_path = DIAGNOSTICS_DIR / f"extracted_{paper_id}.json"
        correct_path = DIAGNOSTICS_DIR / f"correct_{paper_id}.json"
        
        has_extracted = extracted_path.exists()
        has_correct = correct_path.exists()
        
        status = "unknown"
        summary = "No diagnostics run yet."
        image_count = 0
        figure_count = 0
        
        if has_extracted:
            try:
                with open(extracted_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    status = data.get("status", "unknown")
                    summary = data.get("summary", "")
                    
                    # Image count is all extracted sub-figures (e.g. FIG_3_1, FIG_3_2)
                    images = data.get("figures_extracted", [])
                    image_count = len(images)
                    
                    # Figure count is distinct figure numbers (e.g. FIG_3)
                    figures = set()
                    for img in images:
                        figures.add(img.split("_")[0])
                    figure_count = len(figures)
            except Exception as e:
                status = "error"
                summary = f"Error reading extracted JSON: {e}"
                
        fully_processed = (PAPERS_DIR.parent / "outputs" / paper_id / "06_mapper_output.json").exists()
        
        papers_list.append({
            "paper_id": paper_id,
            "pdf_name": pdfs[0].name,
            "status": status,
            "summary": summary,
            "image_count": image_count,
            "figure_count": figure_count,
            "has_correct": has_correct,
            "fully_processed": fully_processed
        })
        
    return jsonify(papers_list)

@app.route("/api/paper/<paper_id>")
def get_paper_details(paper_id):
    """
    Returns the extracted figure data and the corrected figure/caption data (if any).
    Migrates old coordinate JSONs on-the-fly to separate figures and captions.
    """
    extracted_path = DIAGNOSTICS_DIR / f"extracted_{paper_id}.json"
    correct_path = DIAGNOSTICS_DIR / f"correct_{paper_id}.json"
    
    if not extracted_path.exists():
        # Run diagnostics on-the-fly if needed
        paper_folder = PAPERS_DIR / paper_id
        pdfs = sorted(paper_folder.glob("*.pdf"))
        if not pdfs:
            return jsonify({"error": "Paper folder or PDF not found."}), 404
        try:
            from run_diagnostics import run_diagnostics_for_paper
            extracted_data = run_diagnostics_for_paper(paper_folder, pdfs[0])
        except Exception as e:
            return jsonify({"error": f"Failed to run diagnostics: {e}"}), 500
    else:
        with open(extracted_path, "r", encoding="utf-8") as f:
            extracted_data = json.load(f)
            
    correct_data = None
    if correct_path.exists():
        try:
            with open(correct_path, "r", encoding="utf-8") as f:
                correct_data = json.load(f)
                
            # --- Format Migration Logic ---
            # If the loaded JSON maps directly to an array of items, it's the old format.
            # We migrate it to separate 'figures' and 'captions' lists under pages.
            if correct_data and "pages" in correct_data:
                migrated = False
                for page_num, content in list(correct_data["pages"].items()):
                    if isinstance(content, list):
                        migrated = True
                        figures = []
                        captions = []
                        for item in content:
                            # If it has fig_key, it's a figure
                            if "fig_key" in item:
                                figures.append(item)
                            elif "fig_num" in item:
                                captions.append(item)
                            else:
                                # Default to figure
                                figures.append({
                                    "fig_key": item.get("fig_key", "UNLABELED"),
                                    "bbox": item.get("bbox", [0, 0, 0, 0])
                                })
                        
                        # Populate automatic captions as starting points if no manual captions exist yet
                        for det in extracted_data.get("details", []):
                            if str(det["page"]) == str(page_num):
                                f_num = det["fig_num"]
                                if not any(c.get("fig_num") == f_num for c in captions):
                                    captions.append({
                                        "fig_num": f_num,
                                        "bbox": det["caption_bbox"]
                                    })
                                    
                        correct_data["pages"][page_num] = {
                            "figures": figures,
                            "captions": captions
                        }
                if migrated:
                    # Save back the migrated format
                    with open(correct_path, "w", encoding="utf-8") as f:
                        json.dump(correct_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error migrating correct JSON: {e}")
            
    # Get total page count of PDF
    pdf_path = PAPERS_DIR / paper_id / extracted_data["pdf_name"]
    page_count = 0
    page_dimensions = {}
    if pdf_path.exists():
        try:
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            for i, page in enumerate(doc, 1):
                page_dimensions[str(i)] = {
                    "width": page.rect.width,
                    "height": page.rect.height
                }
            doc.close()
        except Exception:
            pass
            
    return jsonify({
        "extracted": extracted_data,
        "correct": correct_data,
        "page_count": page_count,
        "page_dimensions": page_dimensions
    })

@app.route("/api/paper/<paper_id>/page/<int:page_num>/render")
def render_pdf_page(paper_id, page_num):
    paper_folder = PAPERS_DIR / paper_id
    pdfs = sorted(paper_folder.glob("*.pdf"))
    if not pdfs:
        abort(404)
        
    try:
        doc = fitz.open(str(pdfs[0]))
        if page_num < 1 or page_num > len(doc):
            doc.close()
            abort(400)
            
        page = doc[page_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        doc.close()
        
        from flask import Response
        return Response(img_bytes, mimetype="image/png")
    except Exception as e:
        return jsonify({"error": f"Failed to render page: {e}"}), 500

@app.route("/api/paper/<paper_id>/save_correct", methods=["POST"])
def save_corrected_bboxes(paper_id):
    req_data = request.get_json()
    if not req_data:
        return jsonify({"error": "Missing JSON body."}), 400
        
    correct_path = DIAGNOSTICS_DIR / f"correct_{paper_id}.json"
    with open(correct_path, "w", encoding="utf-8") as f:
        json.dump(req_data, f, indent=2, ensure_ascii=False)
        
    # Mark status as corrected
    extracted_path = DIAGNOSTICS_DIR / f"extracted_{paper_id}.json"
    if extracted_path.exists():
        try:
            with open(extracted_path, "r", encoding="utf-8") as f:
                ext_data = json.load(f)
            ext_data["status"] = "corrected"
            with open(extracted_path, "w", encoding="utf-8") as f:
                json.dump(ext_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
            
    return jsonify({"success": True, "message": f"Corrected bboxes saved for {paper_id}."})

@app.route("/api/random_page")
def get_random_page():
    candidates = []
    for extracted_file in DIAGNOSTICS_DIR.glob("extracted_*.json"):
        try:
            with open(extracted_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            paper_id = data.get("paper_id")
            
            page_figs = {}
            for det in data.get("details", []):
                p_num = str(det["page"])
                page_figs[p_num] = page_figs.get(p_num, 0) + 1
                
            for p_num, count in page_figs.items():
                weight = int(count ** 1.5 * 10)
                candidates.append({
                    "paper_id": paper_id,
                    "page_num": int(p_num),
                    "fig_count": count,
                    "weight": weight
                })
        except Exception:
            pass
            
    if not candidates:
        for entry in PAPERS_DIR.iterdir():
            if entry.is_dir() and sorted(entry.glob("*.pdf")):
                return jsonify({"paper_id": entry.name, "page_num": 1, "fig_count": 0})
        abort(404)
        
    population = candidates
    weights = [c["weight"] for c in population]
    choice = random.choices(population, weights=weights, k=1)[0]
    
    return jsonify({
        "paper_id": choice["paper_id"],
        "page_num": choice["page_num"],
        "fig_count": choice["fig_count"]
    })

@app.route("/api/calibration_session")
def get_calibration_session():
    """
    Curates a list of ~12 pages across multiple papers showing various properties:
    - Multiple figures (composite pages)
    - Warning/Error layout anomalies
    - Standard successful cases
    """
    composite_pages = []
    error_pages = []
    standard_pages = []
    
    for extracted_file in DIAGNOSTICS_DIR.glob("extracted_*.json"):
        try:
            with open(extracted_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            paper_id = data.get("paper_id")
            
            # Map page -> details
            pages_map = {}
            for det in data.get("details", []):
                p_num = det["page"]
                if p_num not in pages_map:
                    pages_map[p_num] = []
                pages_map[p_num].append(det)
                
            for p_num, dets in pages_map.items():
                fig_count = len(dets)
                has_warnings = any(d["heuristic_status"] != "ok" for d in dets)
                
                info = {
                    "paper_id": paper_id,
                    "page_num": p_num,
                    "fig_count": fig_count,
                    "has_warnings": has_warnings,
                    "reason": ""
                }
                
                if fig_count >= 2:
                    info["reason"] = f"Composite layout ({fig_count} images)"
                    composite_pages.append(info)
                elif has_warnings:
                    info["reason"] = f"Layout warning/error: {dets[0]['heuristic_notes']}"
                    error_pages.append(info)
                else:
                    info["reason"] = "Standard single figure"
                    standard_pages.append(info)
        except Exception:
            pass
            
    # Sample lists to make it diverse
    random.shuffle(composite_pages)
    random.shuffle(error_pages)
    random.shuffle(standard_pages)
    
    session_list = []
    session_list.extend(composite_pages[:4])
    session_list.extend(error_pages[:4])
    session_list.extend(standard_pages[:4])
    
    # Shuffle the final session list so it is a good mix
    random.shuffle(session_list)
    
    # Limit to max 12 items
    return jsonify(session_list[:12])


def calculate_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    
    interWidth = max(0, xB - xA)
    interHeight = max(0, yB - yA)
    interArea = interWidth * interHeight
    
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBAArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    
    unionArea = float(boxAArea + boxBAArea - interArea)
    if unionArea == 0:
        return 0.0
    return interArea / unionArea


@app.route("/api/export_report", methods=["POST"])
def export_comparative_report():
    """
    Analyzes automated diagnostics vs manual bounding boxes.
    Generates study_cases_report.md and study_cases_report.html
    containing advanced mathematical indicators and natural language descriptions.
    """
    total_papers_analyzed = 0
    total_pages_verified = 0
    total_pages_corrected = 0
    
    total_auto_figs = 0
    total_corrected_figs = 0
    total_verified_figs = 0
    
    studies = []
    
    for correct_file in DIAGNOSTICS_DIR.glob("correct_*.json"):
        try:
            with open(correct_file, "r", encoding="utf-8") as f:
                correct_data = json.load(f)
            paper_id = correct_data.get("paper_id")
            
            extracted_path = DIAGNOSTICS_DIR / f"extracted_{paper_id}.json"
            if not extracted_path.exists():
                continue
                
            with open(extracted_path, "r", encoding="utf-8") as f:
                extracted_data = json.load(f)
                
            # Migration logic for old format JSONs in report compiler
            if correct_data and "pages" in correct_data:
                for page_num, content in list(correct_data["pages"].items()):
                    if isinstance(content, list):
                        figures = []
                        captions = []
                        for item in content:
                            if "fig_key" in item:
                                figures.append(item)
                            elif "fig_num" in item:
                                captions.append(item)
                            else:
                                figures.append({
                                    "fig_key": item.get("fig_key", "UNLABELED"),
                                    "bbox": item.get("bbox", [0, 0, 0, 0])
                                })
                        for det in extracted_data.get("details", []):
                            if str(det["page"]) == str(page_num):
                                f_num = det["fig_num"]
                                if not any(c.get("fig_num") == f_num for c in captions):
                                    captions.append({
                                        "fig_num": f_num,
                                        "bbox": det["caption_bbox"]
                                    })
                        correct_data["pages"][page_num] = {
                            "figures": figures,
                            "captions": captions
                        }
                        
            total_papers_analyzed += 1
            paper_cases = []
            
            # Map page_num -> page content
            for page_num, content in correct_data.get("pages", {}).items():
                page_num_int = int(page_num)
                
                # Check if it was modified compared to automatic extractions
                page_figures_corrected = content.get("figures", [])
                page_captions_corrected = content.get("captions", [])
                
                # Retrieve automatic figures/captions for this page
                page_details_original = [d for d in extracted_data.get("details", []) if d["page"] == page_num_int]
                
                is_page_edited = False
                case_details = []
                
                # Compare Figures
                for fig in page_figures_corrected:
                    fig_key = fig.get("fig_key")
                    c_bbox = fig.get("bbox")
                    
                    # Find original detail matching this key
                    orig = None
                    for det in page_details_original:
                        if det["fig_key"] == fig_key:
                            orig = det
                            break
                            
                    if orig and orig["match_found"]:
                        o_bbox = orig["matched_bbox"]
                        iou = calculate_iou(o_bbox, c_bbox)
                        
                        if iou == 1.0:
                            total_verified_figs += 1
                            desc = f"Validação direta: a extração automática da figura coincide perfeitamente com a correção humana."
                            status = "verified"
                        else:
                            is_page_edited = True
                            total_corrected_figs += 1
                            
                            # Math shift calculations
                            cx0, cy0, cx1, cy1 = c_bbox
                            ox0, oy0, ox1, oy1 = o_bbox
                            
                            shift_x = ((cx0 + cx1)/2) - ((ox0 + ox1)/2)
                            shift_y = ((cy0 + cy1)/2) - ((oy0 + oy1)/2)
                            
                            w_o, h_o = ox1 - ox0, oy1 - oy0
                            w_c, h_c = cx1 - cx0, cy1 - cy0
                            
                            area_o = w_o * h_o
                            area_c = w_c * h_c
                            area_change = ((area_c - area_o) / area_o) * 100 if area_o > 0 else 0
                            
                            status = "corrected"
                            
                            # Natural language description
                            desc = f"Ajuste de coordenadas (IoU: {iou:.2f}). A caixa original foi deslocada horizontalmente em {shift_x:+.1f} pontos e verticalmente em {shift_y:+.1f} pontos. "
                            desc += f"A largura mudou de {w_o:.1f} para {w_c:.1f} e a altura de {h_o:.1f} para {h_c:.1f} (variação de área: {area_change:+.1f}%). "
                            
                            # Reason estimation
                            reasons = []
                            if shift_y < -5:
                                reasons.append("a imagem estava ligeiramente cortada no topo")
                            elif shift_y > 5:
                                reasons.append("a base da imagem original incluiu texto indesejado")
                            if area_change > 10:
                                reasons.append("a caixa automática omitiu rótulos de eixos ou legendas internas")
                            elif area_change < -10:
                                reasons.append("foram removidas margens em branco ou caixas de texto externas")
                                
                            if reasons:
                                desc += "A correção foi necessária porque: " + " e ".join(reasons) + "."
                            else:
                                desc += "Ajuste de enquadramento fino realizado manualmente."
                    else:
                        is_page_edited = True
                        total_corrected_figs += 1
                        status = "created"
                        desc = f"Falso Negativo: Figura não detectada pelo extrator automático. Caixa criada manualmente em {c_bbox}."
                        
                    case_details.append({
                        "type": "figure",
                        "key": fig_key,
                        "status": status,
                        "desc": desc,
                        "original_bbox": orig["matched_bbox"] if (orig and orig["match_found"]) else None,
                        "corrected_bbox": c_bbox
                    })
                    
                # Compare Captions
                for cap in page_captions_corrected:
                    fig_num = cap.get("fig_num")
                    c_bbox = cap.get("bbox")
                    
                    # Find original detail matching this fig_num
                    orig = None
                    for det in page_details_original:
                        if det["fig_num"] == fig_num:
                            orig = det
                            break
                            
                    if orig:
                        o_bbox = orig["caption_bbox"]
                        iou = calculate_iou(o_bbox, c_bbox)
                        
                        if iou == 1.0:
                            desc = "Legenda validada: o texto e a posição da legenda automática estão corretos."
                            status = "verified"
                        else:
                            is_page_edited = True
                            status = "corrected"
                            
                            cx0, cy0, cx1, cy1 = c_bbox
                            ox0, oy0, ox1, oy1 = o_bbox
                            
                            shift_x = ((cx0 + cx1)/2) - ((ox0 + ox1)/2)
                            shift_y = ((cy0 + cy1)/2) - ((oy0 + oy1)/2)
                            
                            w_o, h_o = ox1 - ox0, oy1 - oy0
                            w_c, h_c = cx1 - cx0, cy1 - cy0
                            
                            area_change = (((w_c * h_c) - (w_o * h_o)) / (w_o * h_o)) * 100 if (w_o * h_o) > 0 else 0
                            
                            desc = f"Ajuste da legenda (IoU: {iou:.2f}). A caixa de legenda foi deslocada por ({shift_x:+.1f}, {shift_y:+.1f}) pontos. "
                            desc += f"A dimensão foi alterada em {area_change:+.1f}%. "
                            
                            if abs(shift_y) > 10:
                                desc += "A correção foi motivada por um erro do extrator em capturar linhas adicionais de legendas multi-linha."
                            else:
                                desc += "Ajuste fino de limites horizontais ou verticais para evitar cortes nas letras."
                    else:
                        is_page_edited = True
                        status = "created"
                        desc = f"Legenda criada manualmente na posição {c_bbox}."
                        
                    case_details.append({
                        "type": "caption",
                        "key": fig_num,
                        "status": status,
                        "desc": desc,
                        "original_bbox": orig["caption_bbox"] if orig else None,
                        "corrected_bbox": c_bbox
                    })
                    
                # Look for Deleted Figures (Falsos Positivos)
                for orig in page_details_original:
                    if orig["match_found"]:
                        fig_key = orig["fig_key"]
                        if not any(f.get("fig_key") == fig_key for f in page_figures_corrected):
                            is_page_edited = True
                            status = "deleted"
                            desc = f"Falso Positivo: Bounding box de figura automática ({fig_key}) foi deletada pois continha texto ou elemento não-figura (ex: tabelas ou linhas divisórias)."
                            case_details.append({
                                "type": "figure",
                                "key": fig_key,
                                "status": status,
                                "desc": desc,
                                "original_bbox": orig["matched_bbox"],
                                "corrected_bbox": None
                            })
                            
                if is_page_edited:
                    total_pages_corrected += 1
                else:
                    total_pages_verified += 1
                    
                paper_cases.append({
                    "page_num": page_num_int,
                    "edited": is_page_edited,
                    "details": case_details
                })
                
            studies.append({
                "paper_id": paper_id,
                "cases": paper_cases
            })
        except Exception as e:
            print(f"Error compiling case study for {correct_file.name}: {e}")
            
    # Generate Markdown File Content
    md_content = f"""# Relatório de Diagnóstico Comparativo - Extração de Imagens

Este relatório documenta as métricas matemáticas e análises textuais comparativas entre a extração automatizada de figuras/legendas do script `image_extractor.py` e as correções realizadas manualmente por um revisor humano no Editor de Diagnóstico.

## 📊 Estatísticas Gerais

* **Total de Papers Analisados**: {total_papers_analyzed}
* **Total de Páginas Verificadas (Corretas de Fábrica)**: {total_pages_verified}
* **Total de Páginas Corrigidas (Com Erros)**: {total_pages_corrected}
* **Taxa de Acerto Automático por Página**: {(total_pages_verified / (total_pages_verified + total_pages_corrected) * 100) if (total_pages_verified + total_pages_corrected) > 0 else 0:.1f}%
* **Total de Figuras Verificadas/Corretas**: {total_verified_figs}
* **Total de Figuras Ajustadas/Criadas/Deletadas**: {total_corrected_figs}

---

## 🔍 Detalhamento por Caso de Estudo

"""
    
    for study in studies:
        paper_id = study["paper_id"]
        md_content += f"### Paper: {paper_id}\n\n"
        
        for case in study["cases"]:
            status_str = "CORRIGIDA" if case["edited"] else "VALIDADA (Sem alterações)"
            md_content += f"#### Página {case['page_num']} ({status_str})\n\n"
            
            for d in case["details"]:
                type_badge = d["type"].upper()
                status_badge = d["status"].upper()
                md_content += f"* **[{type_badge}] Key: {d['key']}** | Status: **{status_badge}**\n"
                md_content += f"  * *Descrição*: {d['desc']}\n"
                if d['original_bbox']:
                    md_content += f"  * *Coordenadas Originais (PDF)*: `[x0: {d['original_bbox'][0]:.1f}, y0: {d['original_bbox'][1]:.1f}, x1: {d['original_bbox'][2]:.1f}, y1: {d['original_bbox'][3]:.1f}]`\n"
                if d['corrected_bbox']:
                    md_content += f"  * *Coordenadas Corrigidas (PDF)*: `[x0: {d['corrected_bbox'][0]:.1f}, y0: {d['corrected_bbox'][1]:.1f}, x1: {d['corrected_bbox'][2]:.1f}, y1: {d['corrected_bbox'][3]:.1f}]`\n"
                md_content += "\n"
            md_content += "---\n\n"
            
    # Write MD Report
    md_report_path = DIAGNOSTICS_DIR / "study_cases_report.md"
    md_report_path.write_text(md_content, encoding="utf-8")
    
    # Generate HTML File Content (with full pages side by side)
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>PaperCave - Bounding Box Study Case Report</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 24px; }}
        h1, h2, h3, h4 {{ color: white; }}
        .header {{ border-bottom: 2px solid #333; padding-bottom: 12px; margin-bottom: 24px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }}
        .stat-card {{ background-color: #1e1e24; border-radius: 8px; padding: 16px; border-left: 4px solid #6366f1; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }}
        .stat-val {{ font-size: 1.8em; font-weight: 700; color: white; margin-top: 8px; }}
        .paper-section {{ background-color: #1a1a1f; border-radius: 8px; padding: 20px; margin-bottom: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
        .page-card {{ background-color: #24242b; border-radius: 6px; padding: 16px; margin-bottom: 20px; border: 1px solid #333; }}
        .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 0.8em; font-weight: bold; margin-left: 8px; }}
        .badge-edited {{ background-color: #f59e0b; color: black; }}
        .badge-verified {{ background-color: #10b981; color: white; }}
        .item-row {{ background-color: #1e1e24; border-radius: 4px; padding: 12px; margin-top: 10px; border-left: 3px solid #6366f1; }}
        .item-row.caption {{ border-left-color: #06b6d4; }}
        .item-row.deleted {{ border-left-color: #ef4444; }}
        .side-by-side {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 15px; }}
        .viewport {{ position: relative; max-width: 450px; background-color: #fff; border-radius: 4px; overflow: hidden; border: 1px solid #444; }}
        .viewport img {{ display: block; width: 100%; height: auto; }}
        .desc-box {{ flex: 1; min-width: 300px; padding: 16px; background-color: #141419; border-radius: 6px; border: 1px solid #2d2d35; font-size: 0.95em; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Relatório de Casos de Estudo de Extração</h1>
        <p>Documento de calibração comparando extração automática e validação humana.</p>
    </div>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div>Papers Analisados</div>
            <div class="stat-val">{total_papers_analyzed}</div>
        </div>
        <div class="stat-card" style="border-left-color: #10b981;">
            <div>Páginas Sem Alterações</div>
            <div class="stat-val">{total_pages_verified}</div>
        </div>
        <div class="stat-card" style="border-left-color: #f59e0b;">
            <div>Páginas Corrigidas</div>
            <div class="stat-val">{total_pages_corrected}</div>
        </div>
        <div class="stat-card" style="border-left-color: #06b6d4;">
            <div>Figuras Validadas</div>
            <div class="stat-val">{total_verified_figs}</div>
        </div>
    </div>
"""
    
    for study in studies:
        paper_id = study["paper_id"]
        html_content += f"""
        <div class="paper-section">
            <h2>Paper: {paper_id}</h2>
        """
        
        for case in study["cases"]:
            badge_class = "badge-edited" if case["edited"] else "badge-verified"
            badge_text = "CORRIGIDA" if case["edited"] else "VALIDADA"
            
            # Show the visual page crop if page had edits
            html_content += f"""
            <div class="page-card">
                <h3>Página {case["page_num"]} <span class="badge {badge_class}">{badge_text}</span></h3>
                <div class="side-by-side">
            """
            
            # Display rendered page
            html_content += f"""
                    <div class="viewport">
                        <img src="/api/paper/{paper_id}/page/{case["page_num"]}/render" alt="Pág {case["page_num"]}">
                    </div>
                    <div class="desc-box">
                        <h4>Métricas e Descrições</h4>
            """
            
            for d in case["details"]:
                class_type = d["type"]
                if d["status"] == "deleted":
                    class_type = "deleted"
                html_content += f"""
                        <div class="item-row {class_type}">
                            <strong>[{d["type"].upper()}] Key: {d["key"]}</strong> (Status: {d["status"].upper()})
                            <p style="margin: 6px 0; color: #ccc;">{d["desc"]}</p>
                """
                if d["original_bbox"]:
                    html_content += f'<small style="display:block; color:#888;">Orig: [{", ".join(f"{v:.1f}" for v in d["original_bbox"])}]</small>'
                if d["corrected_bbox"]:
                    html_content += f'<small style="display:block; color:#888;">Corr: [{", ".join(f"{v:.1f}" for v in d["corrected_bbox"])}]</small>'
                html_content += "</div>"
                
            html_content += """
                    </div>
                </div>
            </div>
            """
            
        html_content += "</div>"
        
    html_content += """
</body>
</html>
"""
    
    html_report_path = DIAGNOSTICS_DIR / "study_cases_report.html"
    html_report_path.write_text(html_content, encoding="utf-8")
    
    # --- OPTIONAL: Disabled-by-default LLM Analysis route trigger ---
    # (Triggered if 'run_llm=true' is passed and GEMINI_API_KEY environment variable exists)
    llm_triggered = request.args.get("run_llm", "false").lower() == "true"
    llm_analysis_msg = ""
    if llm_triggered:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            llm_analysis_msg = "LLM analysis skipped: GEMINI_API_KEY environment variable is not defined."
        else:
            try:
                # Use standard Google Generative AI to analyze
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                
                prompt = f"""
Você é um especialista em visão computacional e engenharia de software trabalhando em um script Python que extrai figuras e tabelas de PDFs acadêmicos (usando PyMuPDF).
Com base no relatório de discrepâncias de coordenadas abaixo, que foi compilado após calibração humana comparando caixas automáticas e corretas, analise as falhas sistemáticas do nosso algoritmo.
Sugira alterações concretas nas regras de Heurísticas de Layout (alinhamentos de coluna, limites verticais de corte, manuseio de caixas de legenda multi-linha).

Relatório de discrepâncias:
{md_content[:8000]}
"""
                response = model.generate_content(prompt)
                feedback_path = DIAGNOSTICS_DIR / "llm_feedback.txt"
                feedback_path.write_text(response.text, encoding="utf-8")
                llm_analysis_msg = f"LLM analysis completed and saved to diagnostics/llm_feedback.txt"
            except Exception as e:
                llm_analysis_msg = f"LLM analysis failed: {e}"
                
    return jsonify({
        "success": True,
        "message": "Report successfully exported.",
        "md_path": str(md_report_path),
        "html_path": str(html_report_path),
        "stats": {
            "total_papers": total_papers_analyzed,
            "verified_pages": total_pages_verified,
            "corrected_pages": total_pages_corrected,
            "accuracy_percentage": (total_pages_verified / (total_pages_verified + total_pages_corrected) * 100) if (total_pages_verified + total_pages_corrected) > 0 else 0
        },
        "llm_msg": llm_analysis_msg
    })


# --- Unified Dashboard APIs ---

@app.route("/api/assets_status")
def get_assets_status():
    assets_dir = PAPERS_DIR.parent.parent / "Assets" / "PaperCaveData"
    if not assets_dir.exists():
        return jsonify([])
        
    folders = []
    for entry in assets_dir.iterdir():
        if entry.is_dir():
            if entry.name == "_Prefabs":
                continue
                
            mtime = os.path.getmtime(entry)
            mdate = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            files_count = len(list(entry.glob("*")))
            
            folders.append({
                "folder_name": entry.name,
                "modification_date": mdate,
                "timestamp": mtime,
                "files_count": files_count
            })
            
    folders.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify(folders)

@app.route("/api/run_pipeline", methods=["POST"])
def run_pipeline():
    global current_job
    if current_job and current_job.status == "running":
        return jsonify({"error": "A pipeline job is already running."}), 400
        
    req_data = request.get_json()
    if not req_data or "papers" not in req_data:
        return jsonify({"error": "Missing papers list in request body."}), 400
        
    paper_ids = req_data["papers"]
    simulate = req_data.get("simulate", True)
    from_step = req_data.get("from_step")
    simple_mode = req_data.get("simple_mode", False)
    
    # Normalize from_step
    force_fresh = False
    if from_step == "none":
        from_step = None
        force_fresh = True
    elif from_step == "auto" or from_step == "" or from_step is None:
        from_step = None
        
    current_job = PipelineJob(paper_ids, simulate, from_step, simple_mode)
    current_job.force_fresh = force_fresh
    
    t = threading.Thread(target=background_pipeline_runner, args=(current_job,), daemon=True)
    current_job.thread = t
    t.start()
    
    return jsonify({"success": True, "message": "Pipeline started.", "total_papers": len(paper_ids)})

@app.route("/api/stream_pipeline")
def stream_pipeline():
    def event_stream():
        global current_job
        if not current_job:
            yield "data: {\"event\": \"idle\"}\n\n"
            return
            
        while True:
            try:
                log_line = current_job.log_queue.get(timeout=0.2)
                yield f"data: {json.dumps({'event': 'log', 'text': log_line}, ensure_ascii=False)}\n\n"
            except queue.Empty:
                pass
                
            elapsed = time.time() - current_job.start_time
            if current_job.status == "running":
                current_job.elapsed_time = elapsed
                
                # Dynamic time estimation based on progress
                i = current_job.current_index
                if i > 0:
                    avg_time = elapsed / i
                    papers_left = current_job.total_papers - i
                    current_paper_elapsed = time.time() - current_job.current_paper_start_time
                    remaining_for_current = max(0, avg_time - current_paper_elapsed)
                    remaining_for_others = avg_time * (papers_left - 1)
                    current_job.estimated_remaining = remaining_for_current + remaining_for_others
                else:
                    default_time = (6.0 if current_job.simulate else 150.0) * current_job.total_papers
                    current_job.estimated_remaining = max(0, default_time - elapsed)
            
            progress_data = {
                "event": "progress",
                "status": current_job.status,
                "current_index": current_job.current_index,
                "total_papers": current_job.total_papers,
                "current_paper_id": current_job.current_paper_id,
                "elapsed_time": int(current_job.elapsed_time),
                "estimated_remaining": int(current_job.estimated_remaining)
            }
            
            yield f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n"
            
            if current_job.status != "running" and current_job.log_queue.empty():
                final_data = {
                    "event": "finished",
                    "status": current_job.status,
                    "elapsed_time": int(current_job.elapsed_time)
                }
                yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
                break
                
    from flask import Response
    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/cancel_pipeline", methods=["POST"])
def cancel_pipeline():
    global current_job
    if not current_job or current_job.status != "running":
        return jsonify({"error": "No running pipeline job found."}), 400
        
    current_job.cancelled = True
    current_job.status = "failed"
    current_job.log_queue.put("\n[CANCELADO] Cancelamento solicitado pelo usuário. Interrompendo pipeline...")
    
    # Terminate active process if running
    if current_job.current_process:
        try:
            current_job.log_queue.put("[SISTEMA] Encerrando subprocesso da pipeline...")
            current_job.current_process.terminate()
            current_job.current_process.wait(timeout=1.5)
        except Exception:
            try:
                current_job.current_process.kill()
            except Exception:
                pass
                
    return jsonify({"success": True, "message": "Pipeline cancellation requested."})

@app.route("/api/export_unity/<paper_id>", methods=["POST"])
def export_unity(paper_id):
    try:
        from utils.unity_asset_exporter import export_assets_to_unity
        export_assets_to_unity(
            paper_id=paper_id,
            paper_folder=PAPERS_DIR / paper_id,
            unity_project_root=PAPERS_DIR.parent.parent
        )
        return jsonify({"success": True, "message": f"Successfully exported {paper_id} to Unity."})
    except Exception as e:
        return jsonify({"error": f"Failed to export: {str(e)}"}), 500


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PaperCave Diagnostics Web Server")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the Flask server on.")
    args = parser.parse_args()
    
    print(f"Starting PaperCave Diagnostics server on http://127.0.0.1:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=True)
