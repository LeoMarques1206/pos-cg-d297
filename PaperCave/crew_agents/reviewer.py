"""
crew_agents/reviewer.py
Agente Reviewer: avalia o Object Manifest gerado pelo Mapper.

Atribui score (0.0 a 1.0) por objeto.
Reprova o manifest se 2+ objetos tiverem score < 0.6.
MantÃ©m histÃ³rico de tentativas e monta best_manifest no final.
MÃ¡ximo de 3 tentativas antes de entregar o melhor resultado disponÃ­vel.

Prompts carregados de prompts/agents.yaml.
"""
import yaml
from pathlib import Path
from crewai import Agent


def _load_agent_prompts() -> dict:
    path = Path(__file__).parent.parent / "prompts" / "agents.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_reviewer_agent(llm, max_retries: int = 3) -> Agent:
    prompts = _load_agent_prompts()["reviewer"]
    return Agent(
        role=prompts["role"],
        goal=prompts["goal"],
        backstory=prompts["backstory"],
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_retry_limit=max_retries,
    )

