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
| 2 | Chunking e ingesta | próximamente |
| 3 | Primer RAG | próximamente |
| 4 | Citas y umbral | próximamente |
| 5 | Evaluación | próximamente |

## Usalo con tu propio CV

Llega con el paso 2: poné tu Markdown en `kb/` y configurá `KB_DIR=kb`.

## Licencia

[MIT](LICENSE)
