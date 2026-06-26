"""
run_all_papers.py
Batch runner — processa todos os papers da pasta papers/ em sequência.
Use main.py como ponto de entrada principal; este módulo contém a lógica de batch.

Fluxo:
  FASE 1 (todos os papers, sem IA):
    - PDFs soltos na raiz de papers/ ganham subpasta própria
    - Figuras extraídas de cada PDF (via utils/image_extractor)

  FASE 2 (um paper por vez):
    - Pipeline CrewAI completo
    - Unity export imediato após cada paper
    - Pressione ESC a qualquer momento para parar antes do próximo paper
"""
import argparse
import shutil
import sys
import threading
import traceback
from pathlib import Path
from datetime import datetime

from utils.slug import slugify
from utils.image_extractor import extract_figures_from_pdf

# ── Paths ─────────────────────────────────────────────────────────────────────

PAPERS_DIR  = Path(__file__).parent / "papers"
OUTPUTS_DIR = Path(__file__).parent / "outputs"

# ── ESC key cancellation ──────────────────────────────────────────────────────

_cancel = threading.Event()

def _keyboard_monitor() -> None:
    """Daemon thread: sets _cancel when ESC is pressed (Windows only)."""
    try:
        import msvcrt
        while not _cancel.is_set():
            if msvcrt.kbhit():
                if msvcrt.getch() == b"\x1b":
                    print(
                        "\n  [ESC] Cancelamento solicitado — "
                        "terminando o paper atual e parando.\n"
                    )
                    _cancel.set()
                    return
    except ImportError:
        pass  # não-Windows: ESC não disponível, use Ctrl+C

def _cancelled() -> bool:
    return _cancel.is_set()

def _start_keyboard_monitor() -> None:
    t = threading.Thread(target=_keyboard_monitor, daemon=True)
    t.start()


def _extract_figures_wrapper(paper_folder: Path, pdf_path: Path, verbose: bool = True) -> int:
    """Delegates to utils/image_extractor (single source of truth)."""
    captions = extract_figures_from_pdf(paper_folder, pdf_path, verbose=verbose)
    return len(captions)


# ── Paper discovery ────────────────────────────────────────────────────────────

def discover_and_organize(only: str | None = None) -> list[tuple[Path, Path]]:
    """
    Encontra todos os papers em papers/.
    PDFs soltos na raiz ganham uma subpasta com o nome do arquivo.
    Retorna lista de (paper_folder, pdf_path).
    """
    if not PAPERS_DIR.exists():
        print(f"ERRO: pasta papers/ não encontrada em {PAPERS_DIR}")
        sys.exit(1)

    # --- Organiza PDFs soltos na raiz primeiro ---
    for pdf in sorted(PAPERS_DIR.glob("*.pdf")):
        folder_name  = slugify(pdf.stem)   # ASCII, sem espaços, max 60 chars
        paper_folder = PAPERS_DIR / folder_name
        paper_folder.mkdir(exist_ok=True)
        dest_pdf = paper_folder / pdf.name
        if not dest_pdf.exists():
            shutil.copy2(pdf, dest_pdf)
            print(f"  [organizar] {pdf.name} → {folder_name}/")

    # --- Coleta todas as subpastas com PDF ---
    results: list[tuple[Path, Path]] = []
    for entry in sorted(PAPERS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        pdfs = sorted(entry.glob("*.pdf"))
        if not pdfs:
            continue
        results.append((entry, pdfs[0]))

    if only:
        only_lower = only.lower().strip("/\\")
        results = [
            (f, p) for f, p in results
            if only_lower in f.name.lower()
        ]
        if not results:
            print(f"ERRO: nenhum paper com '{only}' encontrado em {PAPERS_DIR}")
            sys.exit(1)

    return results

# ── Summary printer ───────────────────────────────────────────────────────────

def _print_summary(results: list[dict], ts_start: datetime) -> None:
    elapsed = datetime.now() - ts_start
    m, s = divmod(int(elapsed.total_seconds()), 60)

    print(f"\n{'='*66}")
    print(f"  Resumo — {m}m {s}s")
    print(f"{'='*66}")
    print(f"  {'Paper':<36}  {'Figs':<12}  {'Pipeline':<20}  Export")
    print(f"  {'-'*36}  {'-'*12}  {'-'*20}  {'-'*12}")
    for r in results:
        name = r["paper_id"][:36]
        figs = r.get("figures", "-")
        pipe = r.get("pipeline", "-")
        expo = r.get("export", "-")
        print(f"  {name:<36}  {figs:<12}  {pipe:<20}  {expo}")
    print()

    processed = sum(1 for r in results if "ok" in r.get("pipeline", ""))
    failed    = sum(1 for r in results if "ERRO" in r.get("pipeline", "") or "FALHOU" in r.get("pipeline", ""))
    skipped   = sum(1 for r in results if r.get("pipeline") == "cancelado")

    if skipped:
        print(f"  {processed} processado(s), {failed} com erro, {skipped} cancelado(s) (ESC).")
    elif failed:
        print(f"  {processed}/{len(results)} com sucesso, {failed} com erro.")
    else:
        print(f"  Todos os {len(results)} paper(s) processados com sucesso.")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────

def run_all(
    from_step: str | None = None,
    simple_mode: bool = False,
    skip_figures: bool = False,
    skip_export: bool = False,
    only: str | None = None,
) -> None:
    ts_start = datetime.now()
    _start_keyboard_monitor()

    # ──────────────────────────────────────────────────────────────────────────
    # FASE 1 — organização de pastas + extração de figuras (todos os papers)
    # ──────────────────────────────────────────────────────────────────────────
    print(f"\n{'='*66}")
    print("  FASE 1 — Organizar pastas e extrair figuras")
    print(f"{'='*66}\n")

    papers = discover_and_organize(only=only)
    total  = len(papers)

    if not papers:
        print(f"Nenhum paper encontrado em {PAPERS_DIR}")
        return

    print(f"  {total} paper(s) encontrado(s).\n")

    fig_results: dict[Path, str] = {}

    if skip_figures:
        print("  Extração de figuras ignorada (--skip-figures).\n")
        for paper_folder, _ in papers:
            fig_results[paper_folder] = "ignorado"
    else:
        for i, (paper_folder, pdf_path) in enumerate(papers, 1):
            print(f"  [{i}/{total}] {paper_folder.name}")
            try:
                n = _extract_figures_wrapper(paper_folder, pdf_path, verbose=True)
                fig_results[paper_folder] = f"ok ({n} nova(s))"
            except Exception as e:
                fig_results[paper_folder] = f"ERRO: {e}"
                print(f"    FALHOU: {e}")
            print()

    # ──────────────────────────────────────────────────────────────────────────
    # FASE 2 — pipeline IA + export Unity (um paper por vez)
    # ──────────────────────────────────────────────────────────────────────────
    print(f"\n{'='*66}")
    print("  FASE 2 — Pipeline IA + Unity export")
    if simple_mode: print("  Mode: SIMPLE")
    if from_step:   print(f"  Retomando de: {from_step}")
    print("  Pressione ESC a qualquer momento para parar após o paper atual.")
    print(f"{'='*66}\n")

    from crew import run as crew_run
    from utils.unity_asset_exporter import export_assets_to_unity

    results: list[dict] = []

    for i, (paper_folder, pdf_path) in enumerate(papers, 1):
        paper_id = slugify(paper_folder.name)
        status   = {
            "paper_id": paper_id,
            "figures":  fig_results.get(paper_folder, "-"),
            "pipeline": "-",
            "export":   "-",
        }

        # Checa ESC antes de iniciar cada paper
        if _cancelled():
            status["pipeline"] = "cancelado"
            status["export"]   = "cancelado"
            results.append(status)
            # Marca os papers restantes como cancelados também
            for paper_folder_r, _ in papers[i:]:
                results.append({
                    "paper_id": slugify(paper_folder_r.name),
                    "figures":  fig_results.get(paper_folder_r, "-"),
                    "pipeline": "cancelado",
                    "export":   "cancelado",
                })
            break

        print(f"[{i}/{total}] {paper_id}")
        print(f"  PDF:    {pdf_path.name}")
        print(f"  Pasta:  {paper_folder.name}")
        print()

        # ── Pipeline CrewAI ────────────────────────────────────────────────
        try:
            reviewed = crew_run(
                pdf_path     = str(pdf_path),
                paper_folder = paper_folder,
                from_step    = from_step,
                simple_mode  = simple_mode,
            )
            if reviewed is None:
                status["pipeline"] = "FALHOU (sem output)"
            else:
                status["pipeline"] = f"ok ({reviewed.unitCount} unid.)"
        except KeyboardInterrupt:
            print("\n  Ctrl+C — parando batch.")
            status["pipeline"] = "cancelado"
            results.append(status)
            for paper_folder_r, _ in papers[i:]:
                results.append({
                    "paper_id": slugify(paper_folder_r.name),
                    "figures":  fig_results.get(paper_folder_r, "-"),
                    "pipeline": "cancelado",
                    "export":   "cancelado",
                })
            break
        except Exception as e:
            status["pipeline"] = f"ERRO: {type(e).__name__}"
            print(f"\n  [pipeline] FALHOU:")
            traceback.print_exc()

        # ── Unity export (imediato, só se pipeline ok) ─────────────────────
        if not skip_export and "ok" in status["pipeline"]:
            try:
                export_assets_to_unity(
                    paper_id=paper_id,
                    paper_folder=paper_folder,
                    unity_project_root=Path("..")
                )
                status["export"] = "ok"
            except FileNotFoundError as e:
                status["export"] = f"ERRO: arquivo não encontrado"
                print(f"  [export] FALHOU: {e}")
            except Exception as e:
                status["export"] = f"ERRO: {type(e).__name__}"
                traceback.print_exc()
        elif skip_export:
            status["export"] = "ignorado"
        else:
            status["export"] = "ignorado (pipeline falhou)"

        results.append(status)
        print()

    _cancel.set()  # encerra thread de teclado
    _print_summary(results, ts_start)

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Paper Cave — Batch runner. Processa todos os papers em papers/ sequencialmente.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python run_all_papers.py                        # processa todos
  python run_all_papers.py --simple               # Simple Mode (sem stacks/animation)
  python run_all_papers.py --from-step mapper     # retoma todos a partir do Mapper
  python run_all_papers.py --skip-figures         # não extrai figuras (já existem)
  python run_all_papers.py --skip-export          # não exporta para Unity
  python run_all_papers.py --paper "VTracer"      # só um paper específico
        """,
    )
    parser.add_argument(
        "--from-step",
        choices=["vision_analyst", "summarizer", "extractor", "mapper", "reviewer"],
        default=None,
        help="Retoma todos os papers a partir desta etapa.",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Simple Mode: apenas figure/chart/table, sem stacks ou animation.",
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Pula extração de figuras (usa FIG_*.png já existentes).",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Pula o unity_export após cada paper.",
    )
    parser.add_argument(
        "--paper",
        default=None,
        help="Processa só o paper cujo nome de pasta contém este texto.",
    )
    args = parser.parse_args()

    run_all(
        from_step    = args.from_step,
        simple_mode  = args.simple,
        skip_figures = args.skip_figures,
        skip_export  = args.skip_export,
        only         = args.paper,
    )
