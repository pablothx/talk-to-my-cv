# Paso 0: Setup

🇬🇧 [Read in English](README.md)

## Qué vas a aprender

- Qué piezas tiene un RAG local y dónde corre cada una.
- Cómo dejar un proyecto Python listo en minutos con `uv`.
- Cómo comprobar con un solo comando (`make doctor`) que todo está en su lugar, antes de escribir una línea de RAG.

## El concepto

Un RAG necesita tres cosas:

1. **Un modelo de embeddings**, que convierte texto en vectores. Usamos `bge-m3`.
2. **Un lugar donde guardar y buscar esos vectores.** Usamos Postgres con la extensión pgvector.
3. **Un LLM que redacta la respuesta.** Usamos `qwen2.5:3b`, o Groq si tu máquina no tiene GPU (más abajo).

En este proyecto, **Python corre en tu máquina** con `uv` y **Docker levanta solo la base de datos**. Ollama corre nativo. Así el ciclo editar → correr es instantáneo y el debugger funciona sin vueltas ([ADR-0001](../../docs/adr/0001-python-on-host-infra-in-compose.md)).

```
tu máquina
├── uv / Python  ──►  Ollama (nativo, :11434)    embeddings + LLM
└── docker compose ─► pgvector (:5432)           vectores
```

Todo es gratis y local por defecto: no hay API keys ni cuentas.

## El código

| Archivo | Para qué |
|---------|----------|
| `pyproject.toml` | Dependencias, configuración de pytest (los tests `e2e` quedan afuera por defecto) y ruff. |
| `compose.yaml` | pgvector con healthcheck. Ollama en contenedor es opcional (`--profile ollama`). |
| `.env.example` | Todas las variables, con sus defaults explicados. |
| `src/talk_to_my_cv/config.py` | `load_settings(env)`: configuración tipada y validada. |
| `src/talk_to_my_cv/doctor.py` | `make doctor`: revisa el entorno y te dice cómo arreglar lo que falla. |
| `.pre-commit-config.yaml` | gitleaks (que no se te escape una key) y ruff en cada commit. |

Dos decisiones de diseño que vas a ver repetidas en todo el tutorial:

**1. La configuración recibe el entorno como parámetro.** `load_settings(env={})` en los tests y `load_settings()` en la vida real, que lee `.env` y las variables del sistema. Así testeamos defaults y validaciones sin tocar variables globales:

```python
def test_groq_without_api_key_fails_pointing_to_the_variable():
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        load_settings(env={"LLM_PROVIDER": "groq"})
```

**2. El doctor recibe *probes* inyectables.** La lógica (qué chequear, qué saltear, qué sugerir) está separada de cómo se chequea de verdad. Los tests usan probes falsos; `make doctor` usa los reales. Por ejemplo, si Ollama está caído no tiene sentido decir también "falta el modelo": el doctor saltea esos chequeos y te da una sola pista útil.

## Cómo comprobar que anda

```bash
cp .env.example .env
ollama pull bge-m3 && ollama pull qwen2.5:3b
make install
make check-00
```

Tenés que ver esto:

```
✓ uv installed
✓ Docker running
✓ Postgres reachable
✓ Ollama reachable
✓ model bge-m3 pulled
✓ model qwen2.5:3b pulled
...
✓ step 00 OK
```

### Problemas que nos encontramos (y vos quizás también)

- **`Bind for 0.0.0.0:5432 failed: port is already allocated`.** Ya tenés otro Postgres usando ese puerto. En `.env`, poné `POSTGRES_PORT=5433` y cambiá también el puerto en `DATABASE_URL`.
- **`invalid go version` al instalar los hooks.** El hook clásico de gitleaks compila con el Go de tu sistema, y si es viejo falla. Por eso usamos `gitleaks-docker`: solo necesita Docker, que ya tenés.

### Sin GPU

En un Ryzen 7 4700U sin GPU, `qwen2.5:3b` genera entre 3 y 4 tokens por segundo: una respuesta tarda de 11 a 25 segundos. Funciona, pero no es una conversación fluida. Si tu máquina es parecida, poné `LLM_PROVIDER=groq` y una `GROQ_API_KEY` gratuita. Los embeddings siguen siendo locales. Números completos en la [lección 3](../03-first-rag/README.es.md#sin-gpu).

## Para jugar

1. Apagá Ollama, corré `make doctor` y mirá cómo cambia el reporte. Probá también con `OLLAMA_HOST=http://localhost:1 make doctor`.
2. Poné `LLM_PROVIDER=groq` en `.env` sin `GROQ_API_KEY`. ¿Dónde falla y qué te dice?
3. Agregá un probe nuevo a `doctor.py` (por ejemplo, que `.env` exista). Escribí primero el test.
