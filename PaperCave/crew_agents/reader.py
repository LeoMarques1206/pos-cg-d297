"""
crew_agents/reader.py
Agente Reader: extrai texto limpo de um PDF.
Prompts carregados de prompts/agents.yaml.
"""
import yaml
from pathlib import Path
from crewai import Agent
from tools.pdf_tool import PDFReaderTool


def _load_agent_prompts() -> dict:
    path = Path(__file__).parent.parent / "prompts" / "agents.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_reader_agent(llm) -> Agent:
    prompts = _load_agent_prompts()["reader"]
    return Agent(
        role=prompts["role"],
        goal=prompts["goal"],
        backstory=prompts["backstory"],
        tools=[PDFReaderTool()],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

