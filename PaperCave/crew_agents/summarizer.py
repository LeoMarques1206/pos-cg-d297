"""
crew_agents/summarizer.py
Agente Summarizer: comprime o texto do paper em sumÃ¡rio denso estruturado.
Prompts carregados de prompts/agents.yaml.
"""
import yaml
from pathlib import Path
from crewai import Agent


def _load_agent_prompts() -> dict:
    path = Path(__file__).parent.parent / "prompts" / "agents.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_summarizer_agent(llm) -> Agent:
    prompts = _load_agent_prompts()["summarizer"]
    return Agent(
        role=prompts["role"],
        goal=prompts["goal"],
        backstory=prompts["backstory"],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

