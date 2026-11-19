# Paso 0: Setup

🇬🇧 [Read in English](README.md)

Antes de escribir una línea de RAG, dejamos la máquina lista y comprobamos con un solo comando que todo está en su lugar. Si no leíste los [fundamentos](../fundamentals/README.es.md), empezá por ahí.

## Qué vas a aprender

- Qué piezas tiene un RAG local y dónde corre cada una.
- Cómo dejar un proyecto Python listo en minutos con `uv`.
- Cómo comprobar el entorno con `make doctor` antes de empezar.
- Dos ideas de diseño que se repiten en todo el tutorial.

---

## Pieza 1: las tres piezas de un RAG

Un RAG necesita tres cosas:

1. **Un modelo de embeddings**, que convierte texto en vectores. Usamos `bge-m3`.
2. **Un lugar donde guardar y buscar esos vectores.** Usamos Postgres con la extensión **pgvector**, que le enseña a Postgres a guardar listas de números y compararlas.
3. **Un LLM que redacta la respuesta.** Usamos `qwen2.5:3b`.

Los dos modelos corren en **Ollama**, un programa que sirve modelos en tu máquina. El código le habla por HTTP, como a cualquier API.

## Pieza 2: qué corre dónde

```
tu máquina
├── uv / Python  ──►  Ollama (nativo, :11434)    embeddings + LLM
└── docker compose ─► Postgres + pgvector (:5432) vectores
```

- **Python corre en tu máquina**, no en Docker. Así el ciclo "editar → correr" es instantáneo y el debugger anda sin vueltas ([ADR-0001](../../docs/adr/0001-python-on-host-infra-in-compose.md)).
- **Docker levanta solo la infraestructura:** la base de datos (y en el paso 6, OpenSearch).
- **Ollama corre nativo,** porque así usa tu GPU si tenés una.

Todo es gratis y local: no hay API keys ni cuentas.

## Pieza 3: las herramientas

| Herramienta | Qué es | Para qué la usamos |
|---|---|---|
| **uv** | Un gestor de proyectos Python, muy rápido | Instala Python, las dependencias y corre los comandos |
| **Docker / compose** | Contenedores | Levantar Postgres sin instalarlo |
| **make** | Un atajo de comandos | `make chat` en vez de un comando largo |
| **Ollama** | Un servidor de modelos | Embeddings y LLM, locales |

Cada `make algo` es un atajo: si querés ver qué hace por dentro, abrí el `Makefile`. `make help` lista todos.

## Pieza 4: los archivos del setup

| Archivo | Para qué |
|---------|----------|
| `pyproject.toml` | Las dependencias, la configuración de los tests (los `e2e` quedan afuera por defecto) y de ruff (el linter). |
| `uv.lock` | Las versiones exactas de todo, para que tu instalación sea igual a la nuestra. |
| `compose.yaml` | Postgres con pgvector, con un *healthcheck* (Docker sabe cuándo ya está listo). Ollama en contenedor es opcional (`--profile ollama`). |
| `.env.example` | Todas las variables, con sus defaults explicados. Lo copiás a `.env`. |
| `src/talk_to_my_cv/config.py` | `load_settings()`: lee `.env` y valida cada variable. |
| `src/talk_to_my_cv/doctor.py` | `make doctor`: revisa el entorno y te dice cómo arreglar lo que falla. |
| `.pre-commit-config.yaml` | En cada commit: **gitleaks** (frena si se te escapa una key) y **ruff** (estilo del código). |
| `.github/workflows/ci.yml` | En cada push, GitHub corre el linter y los tests unitarios. |

## Pieza 5: el `.env`

Toda la configuración vive en un archivo `.env`, que **nunca se commitea**. Las más importantes:

```bash
LLM_PROVIDER=ollama      # quién escribe las respuestas
LLM_MODEL=qwen2.5:3b
EMBED_MODEL=bge-m3       # quién hace los embeddings
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/talk_to_my_cv
KB_DIR=kb.example        # de dónde sale el CV: el de ejemplo, o `kb` para el tuyo
```

Si escribís un valor inválido (por ejemplo `LLM_PROVIDER=chatgpt`), `config.py` falla al arrancar con un mensaje que te dice qué variable está mal. Mejor fallar al principio que a la mitad.

## Pieza 6: `make doctor`

Antes de empezar, `make doctor` revisa todo y te dice qué falta:

```
✓ uv installed
✓ Docker running
✓ Postgres reachable
✓ Ollama reachable
✓ model bge-m3 pulled
✓ model qwen2.5:3b pulled
```

Si algo falla, te da **una pista concreta** ("corré `ollama pull bge-m3`"). Y si Ollama está caído, no te dice también "falta el modelo": saltea esos chequeos y te da una sola pista útil.

## Pieza 7: dos ideas de diseño que vas a ver en todo el tutorial

**1. La configuración recibe el entorno como parámetro.** `load_settings(env={...})` en los tests y `load_settings()` en la vida real. Así testeamos defaults y errores sin tocar variables globales:

```python
def test_groq_without_api_key_fails_pointing_to_the_variable():
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        load_settings(env={"LLM_PROVIDER": "groq"})
```

**2. El doctor recibe *probes* inyectables.** Un *probe* es la función que chequea algo de verdad (¿responde Ollama?). La lógica del doctor (qué chequear, qué saltear, qué sugerir) está separada de los probes. Los tests le pasan probes falsos ("Ollama está caído") y verifican el reporte, sin necesitar Ollama.

Las dos son la misma idea: **inyectar lo que viene de afuera**, para poder testear la lógica con piezas falsas. La vas a ver en cada paso.

## Pieza 8: dos niveles de tests

- **Tests unitarios** (`make test`): usan piezas falsas, corren en milisegundos y son los únicos que corren en GitHub.
- **Tests e2e** (`make test-e2e`): hablan con Ollama y Postgres de verdad. Nunca comparan el texto exacto de una respuesta, porque un LLM no siempre dice lo mismo ([ADR-0008](../../docs/adr/0008-tests-against-nondeterministic-llms.md)).

Y cada paso tiene su **`make check-NN`**: corre los tests unitarios, los e2e de todos los pasos hasta ese, y una prueba final. Un paso está terminado cuando su check pasa.

---

## Cómo comprobar que anda

```bash
cp .env.example .env
ollama pull bge-m3 && ollama pull qwen2.5:3b
make install
make check-00
```

Tenés que ver los ✓ de arriba y al final:

```
✓ step 00 OK
```

### Problemas que nos encontramos (y vos quizás también)

- **`Bind for 0.0.0.0:5432 failed: port is already allocated`.** Ya tenés otro Postgres en ese puerto. En `.env`, poné `POSTGRES_PORT=5433` y cambiá también el puerto en `DATABASE_URL`.
- **`invalid go version` al instalar los hooks.** El hook clásico de gitleaks compila con el Go de tu sistema, y si es viejo falla. Por eso usamos `gitleaks-docker`: solo necesita Docker.

### Sin GPU

En un Ryzen 7 4700U sin GPU, `qwen2.5:3b` genera entre 3 y 4 palabras (tokens) por segundo: una respuesta tarda de 11 a 25 segundos. Funciona, pero no es una conversación fluida. Si tu máquina es parecida, podés poner `LLM_PROVIDER=groq` y una `GROQ_API_KEY` gratuita; los embeddings siguen siendo locales. Números completos en la [lección 3](../03-first-rag/README.es.md#sin-gpu).

## Para jugar

1. Apagá Ollama, corré `make doctor` y mirá cómo cambia el reporte. Probá también con `OLLAMA_HOST=http://localhost:1 make doctor`.
2. Poné `LLM_PROVIDER=groq` en `.env` sin `GROQ_API_KEY`. ¿Dónde falla y qué te dice?
3. Agregá un probe nuevo a `doctor.py` (por ejemplo, que `.env` exista). Escribí primero el test.

---

## ✋ Repaso

**1. ¿Por qué Python corre en tu máquina y no en un contenedor?**

<details><summary>Ver respuesta</summary>

Para que editar y correr sea instantáneo y el debugger funcione sin configuración. Docker queda solo para la infraestructura (Postgres, OpenSearch). Está en el ADR-0001.
</details>

**2. 🧪 Probalo:** corré `LLM_PROVIDER=chatgpt make doctor`. Antes de mirar: ¿falla en el doctor o antes?

<details><summary>Ver respuesta</summary>

Antes: `load_settings()` valida `LLM_PROVIDER` al arrancar y el mensaje nombra la variable. La configuración inválida nunca llega a usarse.
</details>

**3. ¿Por qué el doctor no dice "falta el modelo bge-m3" cuando Ollama está apagado?**

<details><summary>Ver respuesta</summary>

Porque sería un falso diagnóstico: si Ollama no responde, no sabe si el modelo está. Saltea esos chequeos y te da una sola pista útil: levantar Ollama.
</details>

**4. ¿Qué tests corren en GitHub y por qué no los demás?**

<details><summary>Ver respuesta</summary>

Solo los unitarios, que usan piezas falsas. Los e2e necesitan Ollama, Postgres y modelos de varios GB, que no están en GitHub. Además, la salida de un LLM varía, así que los e2e solo verifican comportamiento, nunca texto exacto.
</details>

**5. ¿Qué evita gitleaks?**

<details><summary>Ver respuesta</summary>

Que commitees una clave por accidente (por ejemplo, tu `GROQ_API_KEY`). Revisa cada commit y lo frena si encuentra algo que parece un secreto.
</details>

---

[← Fundamentos](../fundamentals/README.es.md) · [Índice](../../README.es.md) · [Siguiente: Paso 1, embeddings →](../01-embeddings/README.es.md)
