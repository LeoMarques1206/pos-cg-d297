#!/usr/bin/env python3
"""
PaperCave/diagnostics/export_pdf_report.py

Standalone script to compile all manual bounding box corrections (including those edited outside guided mode)
into a comprehensive study case PDF report containing side-by-side images with drawn bounding boxes,
mathematical indicators, and detailed textual descriptions.
"""

import os
import re
import json
from pathlib import Path
import fitz  # PyMuPDF
import cv2
import numpy as np

# Setup Paths
DIAGNOSTICS_DIR = Path(__file__).parent
PAPERS_DIR = DIAGNOSTICS_DIR.parent / "papers"
OUTPUT_PDF_PATH = DIAGNOSTICS_DIR / "study_cases_report.pdf"

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

def main():
    print("=== PaperCave PDF Comparative Report Generator ===")
    
    # 1. Discover all papers with correct_*.json
    correct_files = sorted(list(DIAGNOSTICS_DIR.glob("correct_*.json")))
    if not correct_files:
        print("No human corrections found (correct_*.json). Please run diagnostics and save edits in the UI.")
        return
        
    print(f"Found {len(correct_files)} human-corrected configuration files.")
    
    # Create output PDF
    pdf_out = fitz.open()
    
    # Track statistics
    total_papers = 0
    total_pages_verified = 0
    total_pages_corrected = 0
    total_figs_verified = 0
    total_figs_corrected = 0
    
    for correct_file in correct_files:
        try:
            with open(correct_file, "r", encoding="utf-8") as f:
                correct_data = json.load(f)
            paper_id = correct_data.get("paper_id")
            pdf_name = correct_data.get("pdf_name")
            
            # Locate original PDF and extracted data
            paper_folder = PAPERS_DIR / paper_id
            pdf_path = paper_folder / pdf_name
            extracted_path = DIAGNOSTICS_DIR / f"extracted_{paper_id}.json"
            
            if not pdf_path.exists():
                print(f"  [ERROR] PDF file not found: {pdf_path}. Skipping.")
                continue
                
            # If extracted JSON is missing, run diagnostics on the fly without overwriting corrected files
            if not extracted_path.exists():
                print(f"  Diagnostics missing for {paper_id}. Running on-the-fly...")
                try:
                    from run_diagnostics import run_diagnostics_for_paper
                    extracted_data = run_diagnostics_for_paper(paper_folder, pdf_path)
                except Exception as e:
                    print(f"    Failed to run diagnostics: {e}. Skipping.")
                    continue
            else:
                with open(extracted_path, "r", encoding="utf-8") as f:
                    extracted_data = json.load(f)
                    
            print(f"Processing paper: {paper_id}...")
            total_papers += 1
            
            # Open PDF document to render pages
            doc_paper = fitz.open(str(pdf_path))
            
            # Sync correct_data format (migration)
            pages_dict = correct_data.get("pages", {})
            for page_num, content in list(pages_dict.items()):
                # Convert list structure to separate figures/captions dict
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
                    # Add automatically parsed captions as fallback
                    page_num_int = int(page_num)
                    for det in extracted_data.get("details", []):
                        if det["page"] == page_num_int:
                            f_num = det["fig_num"]
                            if not any(c.get("fig_num") == f_num for c in captions):
                                captions.append({
                                    "fig_num": f_num,
                                    "bbox": det["caption_bbox"]
                                })
                    pages_dict[page_num] = {
                        "figures": figures,
                        "captions": captions
                    }
            
            # Analyze each page
            for page_num_str, content in sorted(pages_dict.items(), key=lambda x: int(x[0])):
                page_num = int(page_num_str)
                
                figures_corr = content.get("figures", [])
                captions_corr = content.get("captions", [])
                
                # Fetch original automatic bboxes for this page
                original_details = [d for d in extracted_data.get("details", []) if d["page"] == page_num]
                
                is_page_edited = False
                case_details = []
                
                # 1. Compare Figures
                for fig in figures_corr:
                    fig_key = fig.get("fig_key")
                    c_bbox = fig.get("bbox")
                    
                    orig = None
                    for det in original_details:
                        if det["fig_key"] == fig_key:
                            orig = det
                            break
                            
                    if orig and orig["match_found"]:
                        o_bbox = orig["matched_bbox"]
                        iou = calculate_iou(o_bbox, c_bbox)
                        
                        if iou == 1.0:
                            total_figs_verified += 1
                            desc = "Validação direta: a extração automática coincide perfeitamente com a correção."
                            status = "verified"
                        else:
                            is_page_edited = True
                            total_figs_corrected += 1
                            status = "corrected"
                            
                            cx0, cy0, cx1, cy1 = c_bbox
                            ox0, oy0, ox1, oy1 = o_bbox
                            
                            shift_x = ((cx0 + cx1)/2) - ((ox0 + ox1)/2)
                            shift_y = ((cy0 + cy1)/2) - ((oy0 + oy1)/2)
                            w_o, h_o = ox1 - ox0, oy1 - oy0
                            w_c, h_c = cx1 - cx0, cy1 - cy0
                            area_o = w_o * h_o
                            area_c = w_c * h_c
                            area_change = ((area_c - area_o) / area_o) * 100 if area_o > 0 else 0
                            
                            desc = f"Ajuste fino (IoU: {iou:.2f}). Deslocamento horizontal: {shift_x:+.1f} pts, vertical: {shift_y:+.1f} pts. Área: {area_change:+.1f}%."
                            reasons = []
                            if shift_y < -5:
                                reasons.append("imagem automática cortada no topo")
                            elif shift_y > 5:
                                reasons.append("inclusão de texto na base da imagem")
                            if area_change > 10:
                                reasons.append("omissão de rótulos dos eixos/legendas internas")
                            elif area_change < -10:
                                reasons.append("remoção de margem em branco excessiva")
                            if reasons:
                                desc += " Motivo: " + " e ".join(reasons) + "."
                    else:
                        is_page_edited = True
                        total_figs_corrected += 1
                        status = "created"
                        desc = "Falso Negativo: Figura não detectada pelo extrator automático. Caixa criada manualmente."
                        
                    case_details.append({
                        "type": "figure",
                        "key": fig_key,
                        "status": status,
                        "desc": desc,
                        "original_bbox": orig["matched_bbox"] if (orig and orig["match_found"]) else None,
                        "corrected_bbox": c_bbox
                    })
                    
                # 2. Compare Captions
                for cap in captions_corr:
                    fig_num = cap.get("fig_num")
                    c_bbox = cap.get("bbox")
                    
                    orig = None
                    for det in original_details:
                        if det["fig_num"] == fig_num:
                            orig = det
                            break
                            
                    if orig:
                        o_bbox = orig["caption_bbox"]
                        iou = calculate_iou(o_bbox, c_bbox)
                        
                        if iou == 1.0:
                            desc = "Legenda validada: posição automática está correta."
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
                            
                            desc = f"Legenda ajustada (IoU: {iou:.2f}). Deslocamento: ({shift_x:+.1f}, {shift_y:+.1f}) pts. Área: {area_change:+.1f}%."
                            if abs(shift_y) > 8:
                                desc += " Motivo: Ajuste para capturar legenda multi-linha cortada."
                    else:
                        is_page_edited = True
                        status = "created"
                        desc = "Legenda criada manualmente."
                        
                    case_details.append({
                        "type": "caption",
                        "key": fig_num,
                        "status": status,
                        "desc": desc,
                        "original_bbox": orig["caption_bbox"] if orig else None,
                        "corrected_bbox": c_bbox
                    })
                    
                # 3. Deleted figures (Falsos Positivos)
                for orig in original_details:
                    if orig["match_found"]:
                        fig_key = orig["fig_key"]
                        if not any(f.get("fig_key") == fig_key for f in figures_corr):
                            is_page_edited = True
                            status = "deleted"
                            desc = "Falso Positivo: Figura automática deletada por conter apenas texto, tabelas ou ruído de layout."
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
                    
                # RENDER PAGE AND DRAW BOUNDING BOXES FOR PDF EMBEDDING
                page_paper = doc_paper[page_num - 1]
                pix = page_paper.get_pixmap(matrix=fitz.Matrix(2, 2))
                
                # Load to numpy
                img_orig = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                img_orig = cv2.cvtColor(img_orig, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
                img_corr = img_orig.copy()
                
                # Draw Original BBoxes on img_orig
                for d in case_details:
                    if d["original_bbox"]:
                        ox0, oy0, ox1, oy1 = [int(v * 2) for v in d["original_bbox"]]
                        color = (0, 0, 255) # Red for original figs
                        if d["type"] == "caption":
                            color = (255, 255, 0) # Cyan for original captions
                        cv2.rectangle(img_orig, (ox0, oy0), (ox1, oy1), color, 2)
                        cv2.putText(img_orig, f"{d['type'][:3].upper()}_{d['key']}", (ox0, oy0 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                                    
                # Draw Corrected BBoxes on img_corr
                for d in case_details:
                    if d["corrected_bbox"]:
                        cx0, cy0, cx1, cy1 = [int(v * 2) for v in d["corrected_bbox"]]
                        color = (0, 255, 0) # Green for corrected figs
                        if d["type"] == "caption":
                            color = (255, 255, 0) # Cyan for corrected captions
                        cv2.rectangle(img_corr, (cx0, cy0), (cx1, cy1), color, 2)
                        cv2.putText(img_corr, f"{d['type'][:3].upper()}_{d['key']}", (cx0, cy0 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                                    
                # Compress to PNG
                _, png_bytes_orig = cv2.imencode(".png", img_orig)
                _, png_bytes_corr = cv2.imencode(".png", img_corr)
                
                # --- PDF Page Compilation ---
                page_out = pdf_out.new_page(width=595, height=842) # A4 Size
                
                # 1. Header
                page_out.insert_text((30, 40), "RELATÓRIO DE CALIBRAÇÃO - EXTRAÇÃO DE IMAGENS", fontsize=14, fontname="hebo", color=(0.1, 0.2, 0.6))
                page_out.insert_text((30, 55), f"Paper: {paper_id}  |  Página: {page_num}", fontsize=10, fontname="helv", color=(0.4, 0.4, 0.4))
                page_out.insert_text((500, 55), f"Pág. PDF: {len(pdf_out)}", fontsize=8, fontname="helv", color=(0.5, 0.5, 0.5))
                
                # Line
                page_out.draw_line((30, 65), (565, 65), color=(0.8, 0.8, 0.8), width=1)
                
                # 2. Side-by-side Page Views
                # Rendered image aspect ratio
                aspect = pix.w / pix.h
                img_w = 250
                img_h = int(img_w / aspect)
                if img_h > 350:
                    img_h = 350
                    img_w = int(img_h * aspect)
                    
                rect_o = fitz.Rect(30, 80, 30 + img_w, 80 + img_h)
                rect_c = fitz.Rect(315, 80, 315 + img_w, 80 + img_h)
                
                page_out.insert_image(rect_o, stream=png_bytes_orig.tobytes())
                page_out.insert_image(rect_c, stream=png_bytes_corr.tobytes())
                
                # Captions below images
                y_lbl = 80 + img_h + 15
                page_out.insert_text((30, y_lbl), "Extração Automática (Vermelho = Fig, Ciano = Legenda)", fontsize=8, fontname="hebo", color=(0.7, 0.1, 0.1))
                page_out.insert_text((315, y_lbl), "Correção Humana (Verde = Fig, Ciano = Legenda)", fontsize=8, fontname="hebo", color=(0.1, 0.5, 0.1))
                
                # 3. Descriptive Case Analysis TextBox
                y_txt = y_lbl + 15
                rect_text = fitz.Rect(30, y_txt, 565, 810)
                
                text_block = f"Caso de Estudo: Página {page_num} ({'CORRIGIDA' if is_page_edited else 'VALIDADA SEM ALTERAÇÕES'})\n\n"
                for d in case_details:
                    text_block += f"• [{d['type'].upper()}] Chave: {d['key']} | Status: {d['status'].upper()}\n"
                    text_block += f"  Descrição: {d['desc']}\n"
                    if d['original_bbox']:
                        text_block += f"  Orig: [x0: {d['original_bbox'][0]:.1f}, y0: {d['original_bbox'][1]:.1f}, x1: {d['original_bbox'][2]:.1f}, y1: {d['original_bbox'][3]:.1f}]\n"
                    if d['corrected_bbox']:
                        text_block += f"  Corr: [x0: {d['corrected_bbox'][0]:.1f}, y0: {d['corrected_bbox'][1]:.1f}, x1: {d['corrected_bbox'][2]:.1f}, y1: {d['corrected_bbox'][3]:.1f}]\n"
                    text_block += "\n"
                    
                page_out.insert_textbox(rect_text, text_block, fontsize=8, fontname="helv")
                
            doc_paper.close()
        except Exception as e:
            print(f"Error compiling comparative PDF for {correct_file.name}: {e}")
            import traceback
            traceback.print_exc()
            
    # Add Cover/Summary page at index 0
    if len(pdf_out) > 0:
        cover = pdf_out.new_page(0, width=595, height=842)
        cover.insert_text((50, 150), "RELATÓRIO DE ESTUDO DE CASO E CALIBRAÇÃO", fontsize=20, fontname="hebo", color=(0.1, 0.2, 0.6))
        cover.insert_text((50, 180), "Extração de Imagens de Papers Acadêmicos - PaperCave", fontsize=12, fontname="helv", color=(0.4, 0.4, 0.4))
        
        cover.draw_line((50, 210), (545, 210), color=(0.1, 0.2, 0.6), width=2)
        
        # Summary Box
        rect_summary = fitz.Rect(50, 240, 545, 750)
        
        accuracy = (total_pages_verified / (total_pages_verified + total_pages_corrected) * 100) if (total_pages_verified + total_pages_corrected) > 0 else 0
        summary_text = (
            "Este documento consolida a análise estatística e visual detalhada da precisão do "
            "algoritmo de extração de figuras (utils/image_extractor.py).\n\n"
            "Métricas Consolidadas:\n"
            f"• Total de Papers com Correções de Limites: {total_papers}\n"
            f"• Total de Páginas Revisadas: {total_pages_verified + total_pages_corrected}\n"
            f"  - Páginas corretas automaticamente (validadas): {total_pages_verified}\n"
            f"  - Páginas que continham erros e foram ajustadas: {total_pages_corrected}\n"
            f"• Taxa de Acerto Automático por Página: {accuracy:.1f}%\n"
            f"• Total de Elementos Figuras Validados: {total_figs_verified}\n"
            f"• Total de Elementos Figuras Corrigidos/Ajustados: {total_figs_corrected}\n\n"
            "Instruções para a IA de Ajuste:\n"
            "As descrições detalhadas e discrepâncias métricas de coordenadas para cada página estão descritas "
            "nas páginas subsequentes deste PDF. Utilize esses dados textuais e matemáticos para realizar modificações "
            "no script de extração automática de forma a resolver os desvios sistemáticos de bounding boxes."
        )
        cover.insert_textbox(rect_summary, summary_text, fontsize=10, fontname="helv")
        
        # Save compiled document
        pdf_out.save(str(OUTPUT_PDF_PATH))
        pdf_out.close()
        print(f"\n[SUCCESS] Compiled PDF case study report successfully saved to: {OUTPUT_PDF_PATH}")
    else:
        print("No cases generated. PDF creation skipped.")

if __name__ == "__main__":
    main()
