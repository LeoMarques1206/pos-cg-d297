"""
crew_agents/extractor.py
Agente Extractor (ex-Classifier v3): recebe sumÃ¡rio e produz ExtractionResult.

- Usa make_json_llm() para forÃ§ar response_format=json_object.
- Sem tools para evitar conflito com json format.
- Suporta modo Simple (simple_mode=True) para usar prompt alternativo.

Prompts carregados de prompts/agents.yaml.
"""
import yaml
from pathlib import Path
from crewai import Agent


def _load_agent_prompts() -> dict:
    path = Path(__file__).parent.parent / "prompts" / "agents.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_extractor_agent(llm, max_retries: int = 3) -> Agent:
    prompts = _load_agent_prompts()["extractor"]
    return Agent(
        role=prompts["role"],
        goal=prompts["goal"],
        backstory=prompts["backstory"],
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_retry_limit=max_retries,
    )

