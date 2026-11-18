# talk-to-my-cv

🇬🇧 [Read in English](README.md)

**Aprendé RAG en un día armando un chat con tu CV. 100% local y gratis.**

## Inicio rápido

Requisitos: [uv](https://docs.astral.sh/uv/), Docker y [Ollama](https://ollama.com) corriendo nativo.

```bash
git clone https://github.com/pablothx/talk-to-my-cv && cd talk-to-my-cv
cp .env.example .env
ollama pull bge-m3 && ollama pull qwen2.5:3b
make install
make up
make doctor
```

## Pasos

| Paso | Lección | Tag |
|------|---------|-----|
| 0 | [Setup](lessons/00-setup/README.es.md) | `step-00` |
| 1 | [Embeddings](lessons/01-embeddings/README.es.md) | `step-01` |
| 2 | [Chunking e ingesta](lessons/02-chunking-ingestion/README.es.md) | `step-02` |
| 3 | [Primer RAG](lessons/03-first-rag/README.es.md) | `step-03` |
| 4 | [Citas y umbral](lessons/04-citations-threshold/README.es.md) | `step-04` |
| 5 | [Evaluación](lessons/05-evaluation/README.es.md) | `step-05` |
| 6 | [Búsqueda híbrida con OpenSearch](lessons/06-hybrid-search/README.es.md) | `step-06` |
| 7 | [LangGraph y verificación](lessons/07-langgraph/README.es.md) | `step-07` |
| 8 | API y web | próximamente |
| Bonus | Producción en AWS | próximamente |

## ¿Qué tan bien anda?

Cada cambio se mide con 20 preguntas sobre una persona ficticia ([paso 5](lessons/05-evaluation/README.es.md)):

![Barrido del umbral de relevancia](eval/results/threshold-sweep_bge-m3.png)

## Usalo con tu propio CV

Poné tu Markdown en `kb/` (con la misma forma que `kb.example/`), configurá `KB_DIR=kb` en `.env` y corré `make ingest`. Lo que esté en `kb/_drafts/` se ignora.

## Licencia

[MIT](LICENSE)
