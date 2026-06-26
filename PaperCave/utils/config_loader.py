"""
utils/config_loader.py
Carrega config/config.yaml e resolve o LLM correto para o provider configurado.
Suporta: google, openai, anthropic, lmstudio, ollama, openai_compatible.

Funções exportadas:
  load_config()                  → dict com toda a configuração
  make_llm(cfg)                  → LLM padrão (Reader, Summarizer)
  make_json_llm(cfg)             → LLM com response_format JSON (Classifier)
  get_config_summary(cfg)        → string legível do provider/modelo ativo
  get_embed_fn(cfg)              → função de embedding (ver rag_indexer.py)
"""
import os
import yaml
from pathlib import Path
from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"

PROVIDER_NATIVE = {"google", "openai", "anthropic"}


# ── Carregamento ───────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "config/config.yaml não encontrado.\n"
            "Copie config/config.example.yaml para config/config.yaml e configure."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Resolução de API key ───────────────────────────────────────────────────────

def _resolve_api_key(provider: str, cfg: dict) -> str | None:
    key = cfg.get("api_key")
    if key:
        return key
    env_map = {
        "google":            "GEMINI_API_KEY",
        "openai":            "OPENAI_API_KEY",
        "anthropic":         "ANTHROPIC_API_KEY",
        "lmstudio":          None,
        "ollama":            None,
        "openai_compatible": "OPENAI_API_KEY",
    }
    env_var = env_map.get(provider)
    return os.getenv(env_var) if env_var else None


def _resolve_base_url(provider: str, cfg: dict) -> str | None:
    url = cfg.get("base_url")
    if url:
        return url
    defaults = {
        "lmstudio": "http://localhost:1234/v1",
        "ollama":   "http://localhost:11434",
    }
    return defaults.get(provider)


# ── Fábrica de LLM ────────────────────────────────────────────────────────────

def _build_llm(cfg: dict, extra_kwargs: dict | None = None) -> LLM:
    """Constrói um LLM com os parâmetros resolvidos do config."""
    provider = cfg.get("provider", "google")
    model    = cfg.get("model", "gemini-2.5-flash")
    api_key  = _resolve_api_key(provider, cfg)
    base_url = _resolve_base_url(provider, cfg)

    kwargs: dict = {
        "model":       model,
        "num_retries": cfg.get("api_retries", 5),   # LiteLLM auto-retry on 429/503
        "timeout":     cfg.get("api_timeout", 120),
    }

    if provider in PROVIDER_NATIVE:
        if api_key:
            kwargs["api_key"] = api_key
    else:
        # Endpoint OpenAI-compatible (lmstudio, ollama, openai_compatible)
        if base_url:
            kwargs["base_url"] = base_url
        kwargs["api_key"] = api_key or "local"

    if extra_kwargs:
        kwargs.update(extra_kwargs)

    return LLM(**kwargs)


def make_llm(cfg: dict | None = None) -> LLM:
    """
    LLM padrão — para Reader e Summarizer (saída em texto livre).
    Sem restrições de formato.
    """
    if cfg is None:
        cfg = load_config()
    return _build_llm(cfg)


def make_json_llm(cfg: dict | None = None) -> LLM:
    """
    LLM com response_format=json_object — para o Classifier (sem tools).

    Força o modelo a responder sempre em JSON, eliminando markdown code fences
    e texto livre que quebram o parser Pydantic.

    Nota de compatibilidade:
      - Gemini, GPT-4o, GPT-4o-mini: suporte completo
      - Claude via Anthropic API: LiteLLM mapeia via tool-use — funciona
      - LMStudio / Ollama: depende do modelo; se falhar, o sistema retorna
        para modo sem response_format automaticamente
      - NÃO use para agentes com tools (ex: Designer) — o response_format
        conflita com o protocolo de tool-calling

    Se o provider não suportar, o _build_llm ignora silenciosamente o parâmetro
    (LiteLLM trata a incompatibilidade).
    """
    if cfg is None:
        cfg = load_config()

    provider = cfg.get("provider", "google")

    # Anthropic e Google (Gemini) não devem ter o response_format definido como dicionário:
    # - Anthropic usa tool-use no LiteLLM.
    # - Google (GeminiCompletion nativo do CrewAI) exige que response_format seja um Pydantic BaseModel (ou None).
    # O JSON é gerado corretamente pois o CrewAI passa o schema Pydantic dinamicamente via output_pydantic na task.
    if provider in ("anthropic", "google"):
        return _build_llm(cfg)

    return _build_llm(cfg, extra_kwargs={"response_format": {"type": "json_object"}})


# ── Sumário legível ────────────────────────────────────────────────────────────

def get_config_summary(cfg: dict) -> str:
    provider = cfg.get("provider", "google")
    model    = cfg.get("model", "gemini-2.5-flash")
    base_url = cfg.get("base_url", "")
    suffix   = f" @ {base_url}" if base_url else ""
    return f"{provider}/{model}{suffix}"
