"""
crew_agents/mapper.py
Agente Mapper (ex-Designer v3): recebe ExtractionResult e produz CardManifest.

- NÃ£o usa response_format=json_object pois pode receber search_tool.
- Suporta simple_mode: usa prompt mapper_simple do agents.yaml.
- Ã‰ o target do retry loop controlado pelo Reviewer.

Prompts carregados de prompts/agents.yaml.
"""
import yaml
from pathlib import Path
from crewai import Agent
from crewai.tools import BaseTool


def _load_agent_prompts() -> dict:
    path = Path(__file__).parent.parent / "prompts" / "agents.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_mapper_agent(
    llm,
    search_tool: BaseTool | None = None,
    max_retries: int = 3,
    simple_mode: bool = False,
    card_count: int = 5,
) -> Agent:
    """
    Args:
        llm:         LLM padrÃ£o (make_llm).
        search_tool: Ferramenta de busca RAG (opcional).
        max_retries: Tentativas de re-geraÃ§Ã£o em caso de falha de schema.
        simple_mode: Se True, usa prompts mapper_simple (cards figure/chart apenas).
        card_count:  NÃºmero de cards que o Mapper deve produzir (injetado no goal).
    """
    prompts_key = "mapper_simple" if simple_mode else "mapper"
    prompts = _load_agent_prompts()[prompts_key]
    tools   = [search_tool] if search_tool is not None else []

    goal = prompts["goal"].replace("{card_count}", str(card_count))

    return Agent(
        role=prompts["role"],
        goal=goal,
        backstory=prompts["backstory"],
        tools=tools,
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_retry_limit=max_retries,
    )

