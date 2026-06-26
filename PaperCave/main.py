"""
main.py — Paper Cave entry point.

Commands:
  extract   Extract figures from a paper (no AI, fast)
  run       Run the full AI pipeline for one paper
  batch     Run the full pipeline for all papers in papers/
  export    Export results to Unity (no AI)

Examples:
  python main.py extract --paper papers/joyce-2020/
  python main.py run --paper papers/joyce-2020/
  python main.py run --paper papers/joyce-2020/ --from-step mapper
  python main.py run --paper papers/joyce-2020/ --simple
  python main.py batch
  python main.py batch --paper "joyce"          # filter by name
  python main.py batch --skip-figures           # reuse existing FIG_*.png
  python main.py export --paper joyce_2020
"""
import argparse
import sys
from pathlib import Path


PAPERS_DIR = Path(__file__).parent / "papers"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_paper(name_or_path: str) -> tuple[Path, Path]:
    """
    Resolve a paper folder and its PDF from a name fragment or full path.
    Returns (paper_folder, pdf_path).
    """
    candidate = Path(name_or_path)
    if candidate.is_dir():
        paper_folder = candidate.resolve()
    else:
        # Search by fragment in papers/
        matches = [
            d for d in PAPERS_DIR.iterdir()
            if d.is_dir() and name_or_path.lower().strip("/\\") in d.name.lower()
        ]
        if not matches:
            print(f"ERRO: nenhuma pasta de paper contendo '{name_or_path}' encontrada em {PAPERS_DIR}")
            sys.exit(1)
        if len(matches) > 1:
            print(f"Múltiplas pastas correspondem a '{name_or_path}':")
            for m in matches:
                print(f"  {m.name}")
            print("Seja mais específico.")
            sys.exit(1)
        paper_folder = matches[0]

    pdfs = sorted(paper_folder.glob("*.pdf"))
    if not pdfs:
        print(f"ERRO: nenhum PDF encontrado em {paper_folder}")
        sys.exit(1)
    return paper_folder, pdfs[0]


def _print_header(title: str) -> None:
    bar = "=" * 64
    print(f"\n  {bar}")
    print(f"  Paper Cave  >  {title}")
    print(f"  {bar}\n")


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_extract(args) -> None:
    """Extract figures from a paper PDF. Fast, no AI required."""
    from utils.image_extractor import extract_figures_from_pdf

    paper_folder, pdf_path = _resolve_paper(args.paper)
    _print_header(f"extract  >  {paper_folder.name}")
    print(f"  PDF: {pdf_path.name}\n")

    captions = extract_figures_from_pdf(paper_folder, pdf_path, verbose=True)

    print()
    if captions:
        print(f"  {len(captions)} figura(s) salva(s) em {paper_folder}/")
        print(f"  captions.txt gravado.")
    else:
        print("  Nenhuma figura com caption 'Fig N' encontrada.")
        print("  Verifique se o paper tem figuras com legendas padrão IEEE/ACM.")


_STEP_OUTPUTS = [
    # (step_name_for_--from-step, output_filename)
    ("vision_analyst", "01_reader_output.json"),
    ("summarizer",     "03_vision_insights.json"),
    ("extractor",      "04_summarizer_output.json"),
    ("mapper",         "05_extractor_output.json"),
    ("reviewer",       "06_mapper_output.json"),
]

def _detect_resume(paper_id: str) -> str | None:
    """
    Inspect output folder to find the furthest completed step.
    Returns the next --from-step to suggest, or None if nothing done yet.
    """
    outputs_dir = Path(__file__).parent / "outputs" / paper_id
    if not outputs_dir.exists():
        return None
    last_done = None
    for step_name, fname in _STEP_OUTPUTS:
        if (outputs_dir / fname).exists():
            last_done = step_name
    return last_done


def _ask_resume(paper_id: str, from_step_arg: str | None) -> str | None:
    """
    If previous outputs exist and --from-step wasn't passed, ask the user
    whether to resume from the last completed step or start fresh.
    Returns the from_step to use (None = start fresh).
    """
    if from_step_arg is not None:
        return from_step_arg   # user already decided

    detected = _detect_resume(paper_id)
    if not detected:
        return None

    outputs_dir = Path(__file__).parent / "outputs" / paper_id
    existing = [f.name for f in sorted(outputs_dir.glob("0*.json"))]
    print(f"  Progresso anterior detectado em outputs/{paper_id}/:")
    for f in existing:
        print(f"    {f}")
    print()
    print(f"  Sugestao: retomar de '--from-step {detected}'")
    print("  [R] Retomar do ponto salvo")
    print("  [N] Comecar do zero (sobrescreve outputs anteriores)")
    print("  [Q] Cancelar")
    while True:
        choice = input("  Escolha [R/N/Q]: ").strip().upper()
        if choice == "R":
            print(f"\n  Retomando de '{detected}'.\n")
            return detected
        elif choice == "N":
            print("\n  Iniciando do zero.\n")
            return None
        elif choice == "Q":
            print("  Cancelado.")
            sys.exit(0)


def cmd_run(args) -> None:
    """Run the full AI pipeline for one paper."""
    from crew import run as crew_run
    from utils.slug import slugify

    paper_folder, pdf_path = _resolve_paper(args.paper)
    paper_id = slugify(paper_folder.name)

    _print_header(f"run  >  {paper_id}")

    # Resume detection (only when not already told what to do)
    from_step = _ask_resume(paper_id, getattr(args, "from_step", None))

    if from_step:
        print(f"  Retomando de: {from_step}\n")

    # Extract figures unless skipped or resuming past that point
    skip_figs = getattr(args, "skip_figures", False) or from_step in (
        "summarizer", "extractor", "mapper", "reviewer"
    )
    if not skip_figs:
        from utils.image_extractor import extract_figures_from_pdf
        print("  Extraindo figuras...\n")
        captions = extract_figures_from_pdf(paper_folder, pdf_path, verbose=True)
        print()
        if not captions:
            print("  Aviso: nenhuma figura extraída. Continuando sem figuras visuais.\n")

    result = crew_run(
        pdf_path     = str(pdf_path),
        paper_folder = paper_folder,
        from_step    = from_step,
        simple_mode  = getattr(args, "simple", False),
    )

    if result:
        print(f"\n  Pipeline concluido. Outputs em: outputs/{paper_id}/")
        if not getattr(args, "skip_export", False):
            _do_export(paper_id)
    else:
        print(f"\n  Pipeline falhou. Log: outputs/{paper_id}/session_*.log")
        sys.exit(1)


def cmd_batch(args) -> None:
    """Run the full pipeline for all papers in papers/."""
    from run_all_papers import run_all
    _print_header("batch")
    run_all(
        from_step    = args.from_step,
        simple_mode  = args.simple,
        skip_figures = args.skip_figures,
        skip_export  = args.skip_export,
        only         = args.paper,
    )


def cmd_export(args) -> None:
    """Export pipeline results to Unity."""
    from utils.slug import slugify
    _print_header(f"export  >  {args.paper}")

    paper_id = slugify(Path(args.paper).name) if Path(args.paper).exists() else args.paper
    _do_export(paper_id)


def _do_export(paper_id: str) -> None:
    from utils.unity_asset_exporter import export_assets_to_unity
    paper_folder = Path("papers") / paper_id
    try:
        export_assets_to_unity(
            paper_id=paper_id,
            paper_folder=paper_folder,
            unity_project_root=Path(".."),
        )
        print(f"  Export concluído: Assets/PaperCaveData/{paper_id}/")
    except FileNotFoundError as e:
        print(f"  Export falhou (arquivo não encontrado): {e}")
    except Exception as e:
        print(f"  Export falhou: {e}")


# ── Argument parser ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Paper Cave — extrai figuras e processa papers acadêmicos para Unity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── extract ──────────────────────────────────────────────────────────────
    p_ext = sub.add_parser("extract", help="Extrai figuras do PDF (sem IA)")
    p_ext.add_argument(
        "--paper", required=True,
        help="Caminho ou fragmento de nome da pasta do paper (ex: papers/joyce-2020/ ou 'joyce')",
    )

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Pipeline completo para um paper")
    p_run.add_argument(
        "--paper", required=True,
        help="Caminho ou fragmento de nome da pasta do paper",
    )
    p_run.add_argument(
        "--from-step",
        choices=["vision_analyst", "summarizer", "extractor", "mapper", "reviewer"],
        default=None,
        help="Retoma a partir desta etapa (reusa outputs anteriores)",
    )
    p_run.add_argument(
        "--simple", action="store_true",
        help="Simple Mode: apenas figure/chart/table, sem stacks ou animation",
    )
    p_run.add_argument(
        "--skip-figures", action="store_true",
        help="Pula extração de figuras (usa FIG_*.png já existentes)",
    )
    p_run.add_argument(
        "--skip-export", action="store_true",
        help="Pula o export para Unity ao final",
    )

    # ── batch ─────────────────────────────────────────────────────────────────
    p_bat = sub.add_parser("batch", help="Pipeline para todos os papers em papers/")
    p_bat.add_argument(
        "--paper", default=None,
        help="Processa só o paper cujo nome contém este texto",
    )
    p_bat.add_argument(
        "--from-step",
        choices=["vision_analyst", "summarizer", "extractor", "mapper", "reviewer"],
        default=None,
    )
    p_bat.add_argument("--simple", action="store_true")
    p_bat.add_argument("--skip-figures", action="store_true")
    p_bat.add_argument("--skip-export",  action="store_true")

    # ── export ────────────────────────────────────────────────────────────────
    p_exp = sub.add_parser("export", help="Exporta resultado para Unity (sem IA)")
    p_exp.add_argument(
        "--paper", required=True,
        help="paper_id ou caminho da pasta (ex: joyce_2020)",
    )

    return parser


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = build_parser()
    args   = parser.parse_args()

    # Normalize --from-step (argparse converts hyphens to underscores in dest)
    if hasattr(args, "from_step") and args.from_step:
        args.from_step = args.from_step.replace("-", "_")

    dispatch = {
        "extract": cmd_extract,
        "run":     cmd_run,
        "batch":   cmd_batch,
        "export":  cmd_export,
    }
    dispatch[args.command](args)
