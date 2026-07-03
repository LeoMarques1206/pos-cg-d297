"""
utils/rag_indexer.py
RAG Agêntico — indexa o texto do paper e fornece uma ferramenta de busca
para o agente Designer consultar passagens específicas sob demanda.

Routing de embeddings por provider:
  - google:            Gemini Embeddings API (gemini-embedding-2, SDK google.genai)
  - openai /
    openai_compatible: OpenAI Embeddings API (text-embedding-3-small)
  - anthropic /
    lmstudio /
    ollama / outros:   SentenceTransformers local (all-MiniLM-L6-v2, roda em CPU)

Fallback automático: se o provider primário falhar nos primeiros chunks,
o sistema cai silenciosamente para embeddings locais (SentenceTransformers)
em vez de abortar — garantindo que o RAG funcione mesmo com problemas de API.

O índice é mantido em memória (numpy cosine similarity).

Nota sobre gemini-embedding-2 (retrieval assimétrico):
  Documentos são indexados com prefixo: "title: none | text: {conteúdo}"
  Queries são buscadas com prefixo:     "task: search result | query: {query}"
  Isso otimiza a precisão de retrieval conforme a documentação oficial do Gemini.
"""
import os
import re
import numpy as np
from typing import Callable, Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ── Chunking ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Divide o texto em chunks sobrepostos (chunk_size em caracteres)."""
    chunks = []
    start = 0
    while start < len(text):
        end   = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


# ── Similaridade ───────────────────────────────────────────────────────────────

def _cosine_sim(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom  = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 1e-9 else 0.0


# ── Provedores de Embedding ────────────────────────────────────────────────────

def _google_embed(api_key: str) -> tuple[Callable, Callable]:
    """
    Gemini Embeddings via SDK google.genai (nova API, não-deprecated).
    Modelo: gemini-embedding-2 (multimodal, 3072 dims, gratuito até cota free).

    Retrieval assimétrico (recomendado pela documentação oficial):
      - Documentos: "title: none | text: {conteúdo}"
      - Queries:    "task: search result | query: {query}"

    Retorna (embed_doc_fn, embed_query_fn) — funções distintas para indexação
    e para busca, necessárias pelo formato assimétrico do gemini-embedding-2.
    """
    def _embed_doc(text: str) -> list[float]:
        from google import genai
        client = genai.Client(api_key=api_key)
        doc_text = f"title: none | text: {text[:7000]}"
        result   = client.models.embed_content(
            model    = "gemini-embedding-2",
            contents = doc_text,
        )
        return list(result.embeddings[0].values)

    def _embed_query(text: str) -> list[float]:
        from google import genai
        client = genai.Client(api_key=api_key)
        query_text = f"task: search result | query: {text[:7000]}"
        result     = client.models.embed_content(
            model    = "gemini-embedding-2",
            contents = query_text,
        )
        return list(result.embeddings[0].values)

    return _embed_doc, _embed_query


def _openai_embed(api_key: str, base_url: Optional[str] = None, model: str = "text-embedding-3-small") -> tuple[Callable, Callable]:
    """OpenAI-compatible Embeddings — customizable model."""
    def _embed(text: str) -> list[float]:
        from openai import OpenAI
        client = OpenAI(api_key=api_key or "local", base_url=base_url)
        result = client.embeddings.create(
            model = model,
            input = text[:8000],
        )
        return result.data[0].embedding

    # OpenAI usa o mesmo modelo para doc e query (embedding simétrico)
    return _embed, _embed


# Cache do modelo SentenceTransformers para evitar recarregar entre calls
_LOCAL_MODEL_CACHE: dict[str, object] = {}


def _local_embed(model_name: str = "all-MiniLM-L6-v2") -> tuple[Callable, Callable]:
    """
    SentenceTransformers local — roda em CPU, ~90MB de download único.
    Embedding simétrico (mesma função para doc e query).
    """
    def _embed(text: str) -> list[float]:
        if model_name not in _LOCAL_MODEL_CACHE:
            from sentence_transformers import SentenceTransformer
            print(f"\n  Carregando modelo de embeddings local ({model_name})...")
            _LOCAL_MODEL_CACHE[model_name] = SentenceTransformer(model_name)
        model = _LOCAL_MODEL_CACHE[model_name]
        return model.encode(text, normalize_embeddings=True).tolist()

    return _embed, _embed


def _probe_embed_fn(embed_doc_fn: Callable, probe_text: str = "test") -> bool:
    """Testa se uma função de embedding funciona sem erros. Retorna True se OK."""
    try:
        result = embed_doc_fn(probe_text)
        return isinstance(result, list) and len(result) > 0
    except Exception:
        return False


def get_embed_fns(cfg: dict) -> tuple[Callable, Callable]:
    """
    Resolve (embed_doc_fn, embed_query_fn) para o provider configurado,
    com fallback automático para SentenceTransformers local se a API primária falhar.

    Routing:
      google            → Gemini Embeddings API (gemini-embedding-2)
      openai /
      openai_compatible /
      lmstudio          → OpenAI Embeddings API (customizable base_url and model)
      anthropic /
      ollama / outros   → SentenceTransformers local (CPU)
    """
    provider = cfg.get("provider", "google")

    if provider == "google":
        api_key = cfg.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
        embed_doc, embed_query = _google_embed(api_key)
        if _probe_embed_fn(embed_doc):
            return embed_doc, embed_query
        print("  Aviso: Gemini Embeddings indisponível - usando embeddings locais.")
        return _local_embed()

    if provider in ("openai", "openai_compatible", "lmstudio"):
        api_key  = cfg.get("api_key") or os.getenv("OPENAI_API_KEY", "")
        base_url = cfg.get("embedding_base_url") or cfg.get("base_url")
        if not base_url and provider == "lmstudio":
            base_url = "http://localhost:1234/v1"

        embed_model = cfg.get("embedding_model") or "text-embedding-3-small"

        embed_doc, embed_query = _openai_embed(api_key, base_url, model=embed_model)
        if _probe_embed_fn(embed_doc):
            return embed_doc, embed_query
        print(f"  Aviso: API de Embeddings ({provider}/{embed_model}) indisponível - usando embeddings locais.")
        return _local_embed()

    # anthropic, ollama, desconhecido → embeddings locais diretamente
    return _local_embed()


# Alias de compatibilidade — get_embed_fn (singular) retorna só a função de documento
def get_embed_fn(cfg: dict) -> Callable:
    """Alias que retorna apenas embed_doc_fn (para compatibilidade com código legado)."""
    return get_embed_fns(cfg)[0]


# ── Tool CrewAI ────────────────────────────────────────────────────────────────

class _SearchInput(BaseModel):
    query: str = Field(
        description=(
            "Termos de busca para encontrar passagens específicas no paper. "
            "Use termos técnicos precisos: nomes de algoritmos, métricas, "
            "hardware, percentuais ou conceitos que você quer verificar."
        )
    )


def build_paper_search_tool(text: str, cfg: dict, n_results: int = 3) -> BaseTool:
    """
    Constrói e retorna uma ferramenta CrewAI de busca semântica sobre o paper.

    Processo:
    1. Divide o texto em chunks sobrepostos de ~1000 chars
    2. Testa o provider de embeddings — cai para local se falhar
    3. Pré-computa embeddings de todos os chunks
    4. Retorna um BaseTool que, dada uma query, encontra os chunks mais relevantes

    Args:
        text:      Texto completo do paper
        cfg:       Configuração do sistema (resolve provider de embeddings)
        n_results: Número de chunks a retornar por query (padrão: 3)
    """
    chunk_size = cfg.get("rag_chunk_size", 1000)
    overlap    = cfg.get("rag_chunk_overlap", 200)

    chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        raise ValueError("Texto do paper está vazio — não é possível construir o índice RAG.")

    # Resolve funções de embedding (com fallback automático)
    embed_doc_fn, embed_query_fn = get_embed_fns(cfg)

    # Pré-computa embeddings de todos os chunks
    print(f"\n  Indexando {len(chunks)} chunks para RAG agêntico...")
    chunk_embeddings: list[Optional[list[float]]] = []
    failed = 0

    for i, chunk in enumerate(chunks):
        try:
            emb = embed_doc_fn(chunk)
            chunk_embeddings.append(emb)
        except Exception as e:
            chunk_embeddings.append(None)
            failed += 1
            if failed <= 2:
                # Mostra os primeiros erros para diagnóstico
                short_err = str(e)[:120]
                print(f"  Aviso: chunk {i} falhou: {short_err}")
            if failed == 3:
                # A partir do 3° erro consecutivo, tenta fallback para local
                print("  3 falhas consecutivas — tentando fallback para embeddings locais...")
                try:
                    embed_doc_fn, embed_query_fn = _local_embed()
                    # Testa o fallback
                    embed_doc_fn("teste")
                    print("  Embeddings locais ativados.")
                    # Reinicia a indexação do zero com o novo embed_fn
                    chunk_embeddings = []
                    failed = 0
                    for j, c in enumerate(chunks):
                        chunk_embeddings.append(embed_doc_fn(c))
                    break  # sai do loop original
                except Exception as fe:
                    raise RuntimeError(
                        f"Falha no provider primário e no fallback local.\n"
                        f"Instale sentence-transformers: pip install sentence-transformers\n"
                        f"Detalhe: {fe}"
                    ) from fe

    valid_count = sum(1 for e in chunk_embeddings if e is not None)
    print(f"  Índice pronto: {valid_count}/{len(chunks)} chunks indexados.")

    if valid_count == 0:
        raise RuntimeError("Nenhum chunk foi indexado com sucesso.")

    # Cria o tool como subclasse aninhada para encapsular dados no closure
    class _PaperSearchTool(BaseTool):
        name: str = "paper_search"
        description: str = (
            "Busca passagens relevantes do paper científico original. "
            "Use quando precisar de métricas específicas, trechos de metodologia, "
            "nomes de hardware/software ou resultados numéricos que não constam "
            "no sumário fornecido. Retorna os trechos mais relevantes para a query."
        )
        args_schema: type[BaseModel] = _SearchInput

        def _run(self, query: str) -> str:
            try:
                q_emb = embed_query_fn(query)
            except Exception as e:
                return f"Erro ao processar query de busca: {e}"

            scores = [
                _cosine_sim(q_emb, ce) if ce is not None else -1.0
                for ce in chunk_embeddings
            ]

            top_k_idx = sorted(
                range(len(scores)),
                key=lambda i: scores[i],
                reverse=True,
            )[:n_results]

            relevant = [
                (chunks[i], scores[i])
                for i in top_k_idx
                if scores[i] > 0.1
            ]

            if not relevant:
                return (
                    "Nenhuma passagem suficientemente relevante encontrada. "
                    "Tente termos mais específicos do paper."
                )

            return "\n\n---\n\n".join(
                f"[Relevância: {score:.2f}]\n{chunk_text}"
                for chunk_text, score in relevant
            )

    return _PaperSearchTool()
