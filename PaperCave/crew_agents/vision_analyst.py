"""
crew_agents/vision_analyst.py
Agente Vision Analyst: analisa imagens selecionadas do paper.

MODO A (visual): recebe imagens como bytes via tool + contexto textual.
MODO B (text_inferred): recebe apenas caption + parÃ¡grafos vizinhos.

O modo Ã© determinado em crew.py com base no provider configurado.
Prompts carregados de prompts/agents.yaml.
"""
import yaml
from pathlib import Path
from crewai import Agent
from crewai.tools import BaseTool


def _load_agent_prompts() -> dict:
    path = Path(__file__).parent.parent / "prompts" / "agents.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_vision_analyst_agent(llm, vision_tool: BaseTool | None = None) -> Agent:
    """
    Args:
        llm:         LLM configurado (deve suportar visÃ£o para MODO A).
        vision_tool: Tool que fornece imagem como bytes ao agente.
                     Se None, o agente opera em MODO B (text_inferred).
    """
    prompts = _load_agent_prompts()["vision_analyst"]
    tools   = [vision_tool] if vision_tool is not None else []

    return Agent(
        role=prompts["role"],
        goal=prompts["goal"],
        backstory=prompts["backstory"],
        tools=tools,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

