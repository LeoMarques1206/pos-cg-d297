"""
crew.py
Paper Cave v5 — main entry point.

Usage:
  python crew.py                               # interactive paper folder selector
  python crew.py --paper papers/my_paper/     # specify paper folder directly
  python crew.py --simple                      # Simple Mode (figure/chart/table only, no stacks)
  python crew.py --from-step vision_analyst   # resume from Vision Analyst
  python crew.py --from-step summarizer       # resume from Summarizer
  python crew.py --from-step extractor        # resume from Extractor
  python crew.py --from-step mapper           # resume from Mapper
  python crew.py --from-step reviewer         # resume from Reviewer

Pipeline v5:
  PaperFolder → Reader → Vision Analyst (pre-extracted FIG_*.png)
              → Summarizer → Extractor
              → Mapper (+ RAG + context) ↔ Reviewer → ReviewedUnitManifest

v5 changes vs v4.1:
  - Image Selector removed. Vision Analyst now directly describes FIG_*.png
    files that were pre-extracted into the paper folder before running crew.py.
  - Mapper produces a Unit Manifest (cards + stacks) instead of a flat Card Manifest.
  - table and text_panel contentTypes added.
  - Unit IDs use unit_01/unit_02 format instead of card_01/card_02.
  - whyThisUnit replaces whyThisCard.
  - call_with_backoff added for transient API errors (503, rate limits).

LLM routing:
  Reader, Summarizer, Mapper, Vision Analyst, Reviewer → make_llm()
  Extractor                                            → make_json_llm()
"""
import argparse
import json
import logging
import sys
import time
import yaml
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from crewai import Crew, Task, Process

# Suppress noisy third-party loggers before any imports that trigger them
for _noisy in ("litellm", "crewai", "openai", "httpx", "httpcore", "urllib3", "google_genai"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

from utils.config_loader import load_config, make_llm, make_json_llm, get_config_summary
from utils.slug import slugify
from utils.pdf_selector import select_paper_folder
from utils.context_checker import check_and_warn
from utils.thinking_stripper import strip_thinking_tags, has_thinking_tags, extract_json_from_output
from utils.paper_context_loader import (
    load_paper_context,
    update_figure_captions,
    _build_map_task_description,
)
from utils.unity_asset_exporter import export_assets_to_unity
from crew_agents import (
    make_reader_agent,
    make_summarizer_agent,
    make_extractor_agent,
    make_mapper_agent,
    make_vision_analyst_agent,
    make_reviewer_agent,
)
from models.schemas import (
    ImageInsights, ExtractionResult,
    UnitManifest, ReviewResult, ReviewedUnitManifest,
    ObjectScore, ImplementationNotes,
)

load_dotenv()


# ── Helpers ────────────────────────────────────────────────────────────────────

def paper_id_from_folder(paper_folder: Path) -> str:
    return slugify(paper_folder.name)


def save_output(paper_id: str, step: str, data: dict | str) -> Path:
    out_dir = Path("outputs") / paper_id
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / f"{step}.json"
    content = (
        data if isinstance(data, str)
        else json.dumps(data, ensure_ascii=False, indent=2)
    )
    filepath.write_text(content, encoding="utf-8")
    return filepath


def load_task_prompts() -> dict:
    path = Path(__file__).parent / "prompts" / "tasks.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json_output(paper_id: str, filename: str) -> dict:
    filepath = Path("outputs") / paper_id / filename
    if not filepath.exists():
        raise FileNotFoundError(
            f"Intermediate output not found: {filepath}\n"
            f"Run without --from-step first to generate previous outputs."
        )
    return json.loads(filepath.read_text(encoding="utf-8"))


# ── Logging ────────────────────────────────────────────────────────────────────

def setup_logging(paper_id: str) -> logging.Logger:
    log_dir = Path("outputs") / paper_id
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = log_dir / f"session_{timestamp}.log"

    logger = logging.getLogger("paper_cave")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()   # reset handlers to avoid duplicate output on re-runs

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    # Route third-party logs to file only (not console)
    for lib in ("crewai", "litellm", "openai"):
        lib_logger = logging.getLogger(lib)
        lib_logger.handlers.clear()
        lib_logger.addHandler(fh)
        lib_logger.propagate = False

    logger.info(f"Session log: {log_file}")
    return logger


# ── Progress display ───────────────────────────────────────────────────────────

class _Step:
    """Context manager that prints timed step progress to the console."""

    def __init__(self, logger, n: int, total: int, name: str):
        self._logger = logger
        self._label  = f"[{n}/{total}] {name}"
        self._t0     = 0.0

    def __enter__(self):
        self._t0 = time.time()
        self._logger.info(f"\n  +- {self._label}")
        return self

    def done(self, detail: str = ""):
        elapsed = time.time() - self._t0
        suffix  = f" — {detail}" if detail else ""
        self._logger.info(f"  +- ✓ {elapsed:.0f}s{suffix}")

    def fail(self, reason: str = ""):
        elapsed = time.time() - self._t0
        self._logger.error(f"  +- ✗ {elapsed:.0f}s — {reason}")

    def __exit__(self, exc_type, *_):
        if exc_type is not None:
            self.fail(str(exc_type.__name__) if exc_type else "")


# ── Transient API error retry ──────────────────────────────────────────────────

def call_with_backoff(fn, max_attempts: int = 5, base_delay: float = 3.0, logger=None):
    """
    Retries a callable on transient API errors (rate limits, 503s) with
    exponential backoff. Catches both LiteLLM exceptions and generic HTTP errors
    that contain status codes 429/500/503 in their message.
    """
    try:
        from litellm.exceptions import RateLimitError, ServiceUnavailableError, APIError
        transient_litellm = (RateLimitError, ServiceUnavailableError, APIError)
    except ImportError:
        transient_litellm = ()

    def _is_transient(exc: Exception) -> bool:
        if transient_litellm and isinstance(exc, transient_litellm):
            return True
        msg = str(exc).lower()
        return any(code in msg for code in ("503", "429", "rate limit", "unavailable", "overloaded"))

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            if not _is_transient(exc):
                raise
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            msg = (
                f"  API indisponível (tentativa {attempt}/{max_attempts}): "
                f"{type(exc).__name__}. Aguardando {delay:.0f}s..."
            )
            if logger:
                logger.warning(msg)
            else:
                print(msg)
            time.sleep(delay)

    raise RuntimeError(
        f"API falhou após {max_attempts} tentativas. Último erro: {last_exc}"
    ) from last_exc


# ── Post-processing ────────────────────────────────────────────────────────────

def _recover_pydantic(raw: str, model_cls):
    if not raw:
        return None
    try:
        return model_cls.model_validate_json(raw)
    except Exception:
        pass
    cleaned = extract_json_from_output(raw)
    if cleaned == raw:
        return None
    try:
        return model_cls.model_validate_json(cleaned)
    except Exception:
        pass
    return None


def _process_output(task_out, model_cls, logger=None):
    if task_out is None:
        return None, ""
    raw = task_out.raw or ""
    if task_out.pydantic is not None:
        return task_out.pydantic, raw
    if has_thinking_tags(raw) and logger:
        logger.info("  Reasoning tags detected — stripping...")
    recovered = _recover_pydantic(raw, model_cls)
    if recovered is not None and logger:
        logger.info("  Schema recovered after output cleaning.")
    return recovered, raw


# ── Vision support detection ───────────────────────────────────────────────────

def _provider_supports_vision(cfg: dict) -> bool:
    provider = cfg.get("provider", "google")
    model    = cfg.get("model", "").lower()
    vision_providers = {"google"}
    vision_models    = {
        "gpt-4o", "gpt-4o-mini", "gpt-4-vision",
        "claude-opus-4", "claude-sonnet-4", "claude-haiku-4",
        "claude-opus-4-5", "claude-sonnet-4-5",
        "claude-opus-4-7", "claude-sonnet-4-6",
    }
    if provider in vision_providers:
        return True
    if any(vm in model for vm in vision_models):
        return True
    return False


# ── Vision Analyst (simplified — describes pre-extracted FIG_*.png) ────────────

def _describe_paper_figures(
    paper_folder: Path,
    paper_context: dict,
    agents: dict,
    tp: dict,
    logger=None,
) -> ImageInsights | None:
    """
    Runs the Vision Analyst on FIG_*.png files already present in the paper
    folder. No image extraction or selection step — those must be done before
    running crew.py (e.g. via extract_figures.py or manually).
    """
    available_figs = paper_context.get("available_figures", [])
    if not available_figs:
        if logger:
            logger.info("  No FIG*.png in paper folder — skipping Vision Analyst.")
        return None

    captions = paper_context.get("figure_captions", {})
    analyst_context = "\n\n".join(
        f"[{fig}.png]\nCaption: {captions.get(fig, '(no caption extracted)')}"
        for fig in available_figs
    )

    analyst_task = Task(
        description=(
            tp["analyze_images"]["description"]
            + f"\n\nFigures to describe:\n{analyst_context}"
        ),
        expected_output=tp["analyze_images"]["expected_output"],
        agent=agents["vision_analyst"],
        output_pydantic=ImageInsights,
    )
    analyst_result = call_with_backoff(
        lambda: Crew(
            agents=[agents["vision_analyst"]],
            tasks=[analyst_task],
            process=Process.sequential,
            verbose=False,
        ).kickoff(),
        logger=logger,
    )

    insights, _ = _process_output(analyst_result.tasks_output[0], ImageInsights, logger)
    if logger and insights:
        logger.info(f"  Vision Analyst described {len(insights.insights)} figure(s).")
    return insights


# ── Mapper → Reviewer retry loop ──────────────────────────────────────────────

def _format_attempt_history(history: list[dict]) -> str:
    if not history:
        return "No previous attempts."
    lines = []
    for i, entry in enumerate(history, 1):
        if entry["review"] is None:
            lines.append(f"Attempt {i}: Reviewer failed on schema.")
            continue
        scores = ", ".join(
            f"{s['suggestedName']}={s['score']:.2f}"
            for s in entry["review"]["objectScores"]
        )
        lines.append(f"Attempt {i}: {scores}")
    return "\n".join(lines)


def _run_mapper_reviewer_loop(
    manifest_context: str,
    agents: dict,
    tp: dict,
    available_figures: list[str],
    card_count: int = 5,
    simple_mode: bool = False,
    map_task_base_description: str | None = None,
    max_attempts: int = 3,
    logger=None,
) -> ReviewedUnitManifest | None:
    """
    Runs the Mapper → Reviewer loop with attempt history.
    Assembles the best manifest from the highest-scoring units across attempts.
    """
    map_task_key = "map_simple" if simple_mode else "map"
    if map_task_base_description and not simple_mode:
        base_desc = map_task_base_description
    else:
        base_desc = tp[map_task_key]["description"].replace("{card_count}", str(card_count))

    expected_output = tp[map_task_key]["expected_output"].replace("{card_count}", str(card_count))

    attempt_history: list[dict] = []
    best_units: dict[int, tuple] = {}
    last_manifest: UnitManifest | None = None

    for attempt in range(1, max_attempts + 1):
        if logger:
            logger.info(f"  Mapper attempt {attempt}/{max_attempts}")

        # Inject Reviewer feedback (or schema error) from previous attempt
        mapper_context = manifest_context
        if attempt > 1 and attempt_history:
            last_entry = attempt_history[-1]
            last_review = last_entry.get("review")
            last_schema_error = last_entry.get("schema_error")
            if last_schema_error:
                mapper_context += (
                    f"\n\nSCHEMA VALIDATION ERRORS FROM ATTEMPT {attempt - 1}:\n"
                    f"{last_schema_error}\n\n"
                    "Your previous response was REJECTED due to schema errors. "
                    "Read each error carefully and fix them before responding. "
                    "Pay special attention to character limits: "
                    "title/stackLabel max 30 chars, summary max 80 chars, "
                    "animation frame label max 20 chars, frame description max 120 chars."
                )
            elif last_review is not None:
                feedback_lines = [
                    f"  - {s['suggestedName']}: {s['feedback']}"
                    for s in last_review["objectScores"]
                    if s["score"] < 0.6
                ]
                if feedback_lines:
                    mapper_context += (
                        f"\n\nREVIEWER FEEDBACK FROM ATTEMPT {attempt - 1}:\n"
                        + "\n".join(feedback_lines)
                        + "\n\nFix only the flagged units. Keep the others unchanged."
                    )

        map_task = Task(
            description=base_desc + f"\n\nExtracted elements:\n{mapper_context}",
            expected_output=expected_output,
            agent=agents["mapper"],
            output_pydantic=UnitManifest,
        )
        try:
            mapper_result = call_with_backoff(
                lambda: Crew(
                    agents=[agents["mapper"]],
                    tasks=[map_task],
                    process=Process.sequential,
                    verbose=False,
                ).kickoff(),
                logger=logger,
            )
            task_out  = mapper_result.tasks_output[0]
            manifest, _ = _process_output(task_out, UnitManifest, logger)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            # Pydantic ValidationError raised inside CrewAI task execution counts
            # as a schema failure — log and retry instead of crashing the pipeline.
            schema_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            if logger:
                logger.warning(f"  Mapper attempt {attempt} schema error: {schema_error[:200]}")
            attempt_history.append({"manifest": None, "review": None, "schema_error": schema_error})
            continue

        if manifest is None:
            if logger:
                logger.warning(f"  Mapper attempt {attempt} failed on schema.")
            attempt_history.append({"manifest": None, "review": None})
            continue

        last_manifest = manifest

        # Reviewer
        attempt_history_str = _format_attempt_history(attempt_history)
        review_task = Task(
            description=(
                tp["review"]["description"]
                .replace("{attempt_history}", attempt_history_str)
                .replace("{current_attempt}", str(attempt))
                + f"\n\nManifest to evaluate:\n{manifest.model_dump_json(indent=2)}"
            ),
            expected_output=tp["review"]["expected_output"],
            agent=agents["reviewer"],
            output_pydantic=ReviewResult,
        )
        try:
            review_raw = call_with_backoff(
                lambda: Crew(
                    agents=[agents["reviewer"]],
                    tasks=[review_task],
                    process=Process.sequential,
                    verbose=False,
                ).kickoff(),
                logger=logger,
            )
            review, _ = _process_output(review_raw.tasks_output[0], ReviewResult, logger)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            if logger:
                logger.warning(
                    f"  Reviewer attempt {attempt} schema error: "
                    f"{type(exc).__name__}: {str(exc)[:200]}"
                )
            attempt_history.append({"manifest": manifest, "review": None})
            break

        if review is None:
            if logger:
                logger.warning(f"  Reviewer attempt {attempt} failed on schema.")
            attempt_history.append({"manifest": manifest, "review": None})
            break

        attempt_history.append({
            "manifest": manifest,
            "review":   review.model_dump(),
        })

        for idx, (unit, score_obj) in enumerate(
            zip(manifest.units, review.objectScores)
        ):
            if idx not in best_units or score_obj.score > best_units[idx][1]:
                best_units[idx] = (unit, score_obj.score)

        if review.approved:
            if logger:
                logger.info(f"  Manifest approved on attempt {attempt}.")
            break

        if attempt == max_attempts and logger:
            logger.info(
                f"  Max attempts reached. "
                f"Delivering best manifest from {max_attempts} attempts."
            )

    if not best_units:
        return None

    best_unit_list = [best_units[i][0] for i in range(len(best_units))]
    best_scores = [
        ObjectScore(
            suggestedName=best_units[i][0].display_name,
            score=best_units[i][1],
            confidence=(
                "high"   if best_units[i][1] >= 0.8 else
                "medium" if best_units[i][1] >= 0.6 else
                "low"
            ),
            feedback="",
        )
        for i in range(len(best_units))
    ]

    assembled_from_multiple = len(attempt_history) > 1 and any(
        attempt_history[-1]["review"] is not None
        and best_units[i][1] != attempt_history[-1]["review"]["objectScores"][i]["score"]
        for i in range(len(best_units))
        if i < len(attempt_history[-1].get("review", {}).get("objectScores", []))
    )

    ref_manifest = last_manifest or attempt_history[-1]["manifest"]
    return ReviewedUnitManifest(
        paperTitle=ref_manifest.paperTitle,
        centralContribution=ref_manifest.centralContribution,
        unitCount=len(best_unit_list),
        units=best_unit_list,
        objectScores=best_scores,
        totalAttempts=len(attempt_history),
        assembledFromMultipleAttempts=assembled_from_multiple,
        implementationNotes=ImplementationNotes(),
    )


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run(
    pdf_path: str,
    paper_folder: Path,
    from_step: str | None = None,
    simple_mode: bool = False,
):
    cfg      = load_config()
    paper_id = paper_id_from_folder(paper_folder)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger = setup_logging(paper_id)
    mode_label = " [SIMPLE MODE]" if simple_mode else ""
    logger.info(f"\n{'='*60}")
    logger.info(f"  Paper Cave v5{mode_label} — {paper_id}")
    logger.info(f"  Provider: {get_config_summary(cfg)}")
    logger.info(f"  {ts}")
    if from_step:
        logger.info(f"  Mode: resuming from '{from_step}'")
    logger.info(f"{'='*60}\n")

    max_retries = cfg.get("max_schema_retries", 3)
    card_count  = cfg.get("card_count", 5)

    # ── LLMs ──────────────────────────────────────────────────────────────────
    llm_plain  = make_llm(cfg)
    llm_json   = make_json_llm(cfg)
    has_vision = _provider_supports_vision(cfg)

    vision_label = "VISUAL mode" if has_vision else "TEXT INFERRED mode"
    logger.info(f"  Vision Analyst: {vision_label}")

    # ── Load paper context (figures, catalog, style guide) ─────────────────────
    paper_context = load_paper_context(paper_folder)
    available_figs = paper_context["available_figures"]
    if available_figs:
        logger.info(f"  Paper figures found: {', '.join(available_figs)}")
    else:
        logger.info("  No FIG*.png figures found in paper folder.")

    # ── Extract PDF text for RAG and context checking ──────────────────────────
    full_text   = ""
    search_tool = None

    needs_pdf_read = from_step in (None, "vision_analyst", "summarizer")

    if needs_pdf_read and Path(pdf_path).exists():
        try:
            import fitz
            doc       = fitz.open(pdf_path)
            full_text = "\n\n".join(page.get_text() for page in doc)
            doc.close()
            should_proceed = check_and_warn(
                text=full_text,
                model=cfg.get("model", ""),
                base_url=cfg.get("base_url"),
                cfg=cfg,
            )
            if not should_proceed:
                sys.exit(0)
        except Exception as e:
            logger.warning(f"Could not verify PDF context: {e}")

    if not full_text and Path(pdf_path).exists():
        try:
            import fitz
            doc       = fitz.open(pdf_path)
            full_text = "\n\n".join(page.get_text() for page in doc)
            doc.close()
        except Exception:
            pass

    # Populate figure captions from PDF text
    if full_text and available_figs:
        update_figure_captions(paper_context, full_text)
        logger.info(
            f"  Figure captions extracted: "
            f"{len(paper_context['figure_captions'])}/{len(available_figs)}"
        )

    # Build RAG index
    if full_text:
        try:
            from utils.rag_indexer import build_paper_search_tool
            search_tool = build_paper_search_tool(full_text, cfg)
        except (Exception, KeyboardInterrupt) as e:
            if isinstance(e, KeyboardInterrupt):
                logger.warning("RAG interrupted — continuing without search.")
            else:
                logger.warning(f"RAG disabled: {e}")
            search_tool = None

    # ── Build map task description with injected context ───────────────────────
    tp = load_task_prompts()
    map_task_description = None
    if not simple_mode:
        map_task_description = _build_map_task_description(tp, paper_context, card_count)

    # ── Instantiate agents ─────────────────────────────────────────────────────
    agents = {
        "reader":         make_reader_agent(llm_plain),
        "vision_analyst": make_vision_analyst_agent(llm_plain),
        "summarizer":     make_summarizer_agent(llm_plain),
        "extractor":      make_extractor_agent(llm_json, max_retries=max_retries),
        "mapper":         make_mapper_agent(
                              llm_plain,
                              search_tool=search_tool,
                              max_retries=max_retries,
                              simple_mode=simple_mode,
                              card_count=card_count,
                          ),
        "reviewer":       make_reviewer_agent(llm_plain, max_retries=max_retries),
    }

    insights: ImageInsights | None = None
    summary_text = ""
    extraction: ExtractionResult | None = None

    # ── Step 1: Reader ─────────────────────────────────────────────────────────
    if from_step is None:
        with _Step(logger, 1, 6, "Reader — extraindo texto do PDF") as step:
            read_task = Task(
                description=tp["read"]["description"].format(pdf_path=pdf_path),
                expected_output=tp["read"]["expected_output"],
                agent=agents["reader"],
            )
            read_result = call_with_backoff(
                lambda: Crew(
                    agents=[agents["reader"]],
                    tasks=[read_task],
                    process=Process.sequential,
                    verbose=False,
                ).kickoff(),
                logger=logger,
            )
            reader_out  = read_result.tasks_output[0]
            raw_text    = reader_out.raw or ""
            text_clean  = strip_thinking_tags(raw_text) if has_thinking_tags(raw_text) else raw_text
            save_output(paper_id, "01_reader_output", {"raw": text_clean})
            full_text   = text_clean or full_text
            if available_figs and full_text:
                update_figure_captions(paper_context, full_text)
            step.done(f"{len(full_text):,} chars")
    else:
        try:
            full_text = _load_json_output(paper_id, "01_reader_output.json").get("raw", full_text)
            if available_figs and full_text:
                update_figure_captions(paper_context, full_text)
            logger.info("  [1/6] Reader — usando output salvo.")
        except FileNotFoundError:
            logger.info("  [1/6] Reader — output não encontrado, usando texto do PDF.")

    # Rebuild map task description with updated captions after Reader
    if not simple_mode and full_text:
        map_task_description = _build_map_task_description(tp, paper_context, card_count)

    # ── Step 2: Vision Analyst (pre-extracted figures only) ────────────────────
    skip_vision = from_step in ("summarizer", "extractor", "mapper", "reviewer")

    if not skip_vision:
        if from_step in (None, "vision_analyst"):
            n_figs = len(paper_context.get("available_figures", []))
            if n_figs:
                with _Step(logger, 2, 6, f"Vision Analyst — {n_figs} figura(s)") as step:
                    insights = _describe_paper_figures(paper_folder, paper_context, agents, tp, logger)
                    if insights:
                        save_output(paper_id, "03_vision_insights", insights.model_dump())
                        step.done(f"{len(insights.insights)} figura(s) descritas")
                    else:
                        step.done("sem figuras para descrever")
            else:
                logger.info("  [2/6] Vision Analyst — sem FIG*.png, etapa ignorada.")
    else:
        try:
            ins_data  = _load_json_output(paper_id, "03_vision_insights.json")
            insights  = ImageInsights.model_validate(ins_data)
            logger.info(f"  [2/6] Vision Analyst — usando output salvo ({len(insights.insights)} figuras).")
        except (FileNotFoundError, Exception):
            logger.info("  [2/6] Vision Analyst — output não encontrado, continuando sem insights visuais.")

    # ── Step 3: Summarizer ─────────────────────────────────────────────────────
    if from_step not in ("extractor", "mapper", "reviewer"):
        with _Step(logger, 3, 6, "Summarizer") as step:
            visual_block = ""
            if insights and insights.insights:
                lines = ["VISUAL INSIGHTS (from pre-extracted paper figures):"]
                for ins in insights.insights:
                    lines.append(
                        f"  [{ins.filename}] {ins.description} "
                        f"(relevance: {ins.relevance})"
                        + (" [text inferred]" if ins.mode == "text_inferred" else "")
                    )
                visual_block = "\n" + "\n".join(lines)

            summarize_desc = (
                tp["summarize"]["description"]
                + f"\n\nFull paper text:\n\n{full_text[:60000]}"
                + visual_block
            )
            summarize_task = Task(
                description=summarize_desc,
                expected_output=tp["summarize"]["expected_output"],
                agent=agents["summarizer"],
            )
            sum_result = call_with_backoff(
                lambda: Crew(
                    agents=[agents["summarizer"]],
                    tasks=[summarize_task],
                    process=Process.sequential,
                    verbose=False,
                ).kickoff(),
                logger=logger,
            )
            sum_out   = sum_result.tasks_output[0]
            raw_sum   = sum_out.raw or ""
            sum_clean = strip_thinking_tags(raw_sum) if has_thinking_tags(raw_sum) else raw_sum
            save_output(paper_id, "04_summarizer_output", {"raw": sum_clean})
            summary_text = sum_clean
            step.done(f"{len(sum_clean):,} chars")
    else:
        summary_text = _load_json_output(paper_id, "04_summarizer_output.json").get("raw", "")
        logger.info("  [3/6] Summarizer — usando output salvo.")

    # ── Step 4: Extractor ──────────────────────────────────────────────────────
    if from_step not in ("mapper", "reviewer"):
        with _Step(logger, 4, 6, "Extractor") as step:
            extract_task = Task(
                description=tp["extract"]["description"] + f"\n\nSummary:\n\n{summary_text}",
                expected_output=tp["extract"]["expected_output"],
                agent=agents["extractor"],
                output_pydantic=ExtractionResult,
            )
            ext_result = call_with_backoff(
                lambda: Crew(
                    agents=[agents["extractor"]],
                    tasks=[extract_task],
                    process=Process.sequential,
                    verbose=False,
                ).kickoff(),
                logger=logger,
            )
            extraction, _ = _process_output(ext_result.tasks_output[0], ExtractionResult, logger)

            if extraction is None:
                step.fail("falha no schema — abortando pipeline")
                return None
            save_output(paper_id, "05_extractor_output", extraction.model_dump())
            step.done()
    else:
        ext_data   = _load_json_output(paper_id, "05_extractor_output.json")
        extraction = ExtractionResult.model_validate(ext_data)
        logger.info("  [4/6] Extractor — usando output salvo.")

    # ── Steps 5+6: Mapper → Reviewer (retry loop) ─────────────────────────────
    if from_step != "reviewer":
        with _Step(logger, 5, 6, f"Mapper → Reviewer (máx {max_retries} tentativas)") as step:
            manifest_context = extraction.model_dump_json(indent=2)

            reviewed = _run_mapper_reviewer_loop(
                manifest_context=manifest_context,
                agents=agents,
                tp=tp,
                available_figures=available_figs,
                card_count=card_count,
                simple_mode=simple_mode,
                map_task_base_description=map_task_description,
                max_attempts=max_retries,
                logger=logger,
            )

            if reviewed is None:
                step.fail("falhou em todas as tentativas")
                return None

            save_output(paper_id, "06_mapper_output",   reviewed.model_dump())
            save_output(paper_id, "07_reviewer_output", reviewed.model_dump())
            step.done(f"{reviewed.unitCount} unidade(s), {reviewed.totalAttempts} tentativa(s)")
    else:
        with _Step(logger, 6, 6, "Reviewer — re-avaliando manifest salvo") as step:
            manifest_context = extraction.model_dump_json(indent=2)
            reviewed = _run_mapper_reviewer_loop(
                manifest_context=manifest_context,
                agents=agents,
                tp=tp,
                available_figures=available_figs,
                card_count=card_count,
                simple_mode=simple_mode,
                map_task_base_description=map_task_description,
                max_attempts=max_retries,
                logger=logger,
            )
            if reviewed:
                save_output(paper_id, "07_reviewer_output", reviewed.model_dump())
                step.done(f"{reviewed.unitCount} unidade(s)")
            else:
                step.fail("sem resultado")

    if reviewed:
        try:
            logger.info("  [Export] Iniciando exportação automática para a pasta de assets do Unity...")
            export_assets_to_unity(
                paper_id=paper_id,
                paper_folder=Path(paper_folder),
                unity_project_root=Path("..")
            )
        except Exception as e:
            logger.warning(f"  [Export] Falha na exportação automática para o Unity: {e}")

    logger.info(f"\n{'='*60}")
    logger.info(f"  Done. Outputs at: outputs/{paper_id}/")
    if simple_mode:
        logger.info("  Mode: SIMPLE (figure/chart/table cards only, no stacks)")
    if available_figs:
        logger.info(f"  Paper figures referenced: {', '.join(available_figs)}")
    logger.info(f"{'='*60}\n")

    return reviewed


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Paper Cave v5 — transforms papers into Unit Manifests for Unity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crew.py                                      # interactive folder selector
  python crew.py --paper papers/my_paper/            # specify folder directly
  python crew.py --simple                             # Simple Mode (no stacks/animation)
  python crew.py --from-step vision_analyst          # resume from Vision Analyst
  python crew.py --from-step extractor               # resume from Extractor
  python crew.py --from-step mapper                  # resume from Mapper
  python crew.py --from-step reviewer                # resume from Reviewer

Paper folder structure:
  papers/
    my_paper/
      paper.pdf       <- the PDF (required)
      FIG_1.png       <- extracted figure 1 (run extract_figures.py first)
      FIG_2.png       <- extracted figure 2
        """,
    )
    parser.add_argument(
        "--paper",
        help="Path to the paper folder (e.g., papers/my_paper/). If omitted, opens interactive selector.",
        default=None,
    )
    parser.add_argument(
        "--from-step",
        choices=["vision_analyst", "summarizer", "extractor", "mapper", "reviewer"],
        help="Resume execution from this step, reusing previous outputs.",
        default=None,
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Simple Mode: units restricted to figure/chart/table (no stacks, no animation).",
    )
    args = parser.parse_args()

    if args.paper:
        folder   = Path(args.paper)
        pdfs     = list(folder.glob("*.pdf"))
        if not pdfs:
            print(f"  No PDF found in {folder}")
            sys.exit(1)
        pdf_path    = str(pdfs[0])
        paper_folder = folder
    else:
        pdf_path, paper_folder = select_paper_folder()

    run(
        pdf_path=pdf_path,
        paper_folder=paper_folder,
        from_step=args.from_step,
        simple_mode=args.simple,
    )
