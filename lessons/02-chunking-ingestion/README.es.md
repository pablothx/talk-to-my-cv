# Paso 2: Chunking e ingesta

🇬🇧 [Read in English](README.md)

## Qué vas a aprender

- Por qué un RAG no busca documentos enteros, sino **pedazos** (chunks).
- Cómo cortar Markdown de forma que cada pedazo se pueda **citar**.
- Cómo hacer una ingesta **idempotente**: correrla diez veces da el mismo resultado que correrla una.
- Por qué nunca hay que mezclar vectores de dos modelos distintos.

## El concepto

Si embebés un CV entero en un solo vector, ese vector habla "de todo un poco" y no se parece mucho a ninguna pregunta concreta. Por eso cortamos el documento en pedazos chicos y con un tema claro, y embebemos cada uno.

Elegimos cortar **por títulos de Markdown**, que es como una persona ya organizó su CV:

- cada `##` (H2) es un chunk;
- si el H2 tiene `###` (H3) adentro, cada H3 es su propio chunk;
- si una sección pasa de ~1500 caracteres, se corta por párrafos.

Cada chunk guarda **dos textos**:

| Campo | Ejemplo | Para qué |
|-------|---------|----------|
| `text` | `Led Project Lumen, a ledger…` | Lo que ve el LLM y lo que citamos. |
| `embed_text` | `Northwind Payments > Senior Backend Engineer > Project Lumen` + el texto | Lo que se embebe. |

La ruta de títulos le da contexto al embedding: "Led Project Lumen…" solo no dice en qué empresa pasó, pero con la ruta adelante sí. La sección guardada para citar queda limpia.

### Idempotencia

Cada chunk tiene:

- un **ID** que sale del archivo, la sección y el número de pedazo, y que no cambia entre corridas;
- un **hash del contenido**, que cambia solo si cambia el texto o el frontmatter.

Con eso, `make ingest` compara lo que hay en disco con lo que hay en la base:

- **ID nuevo:** se agrega.
- **Hash distinto:** se re-embebe solo ese chunk.
- **ID que ya no existe en disco:** se borra.
- **Lo demás:** no se toca.

Embeber es lo caro, así que esto importa en cuanto tu KB crece.

### El candado del modelo

La base guarda con qué modelo y con qué dimensión se armó el índice, en la tabla `kb_meta`. Si cambiás `EMBED_MODEL`, la ingesta **falla** y te pide `make ingest REBUILD=1`. Vectores de dos modelos distintos no se pueden comparar: mezclarlos daría búsquedas que parecen andar pero devuelven basura ([ADR-0005](../../docs/adr/0005-chunk-identity-and-embedding-model-lock.md)).

## El código

| Archivo | Qué hace |
|---------|----------|
| `src/talk_to_my_cv/chunking.py` | `chunk_document(path, markdown)`: frontmatter, títulos, cortes, IDs y hashes. |
| `src/talk_to_my_cv/store.py` | La interfaz `VectorStore`, más `InMemoryStore` (para tests) y `PgVectorStore`. |
| `src/talk_to_my_cv/ingest.py` | `ingest(kb_dir, embedder, store)`: compara, embebe lo que cambió y borra lo huérfano. |
| `kb.example/` | Valentina Ríos, una persona ficticia, con datos plantados y trampas para la eval. |
| `eval/questions.yaml` | Primeras preguntas de evaluación. Cada trampa está explicada en un comentario. |

Un truco de testing que vale la pena: **los mismos tests de contrato corren contra el store en memoria y contra pgvector.** Así, si los tests de ingesta pasan contra el fake (rápidos, sin Docker), sabemos que también valen para Postgres.

Los archivos dentro de carpetas que empiezan con `_` (por ejemplo `kb/_drafts/`) se ignoran: son borradores.

## Cómo comprobar que anda

```bash
make check-02
make ingest
```

```
kb.example: 19 added, 0 updated, 0 unchanged, 0 deleted
```

La segunda vez:

```
kb.example: 0 added, 0 updated, 19 unchanged, 0 deleted
```

## Para jugar

1. **Editá una sección** de `kb.example/profile.md` y corré `make ingest`: tiene que decir `1 updated`. Borrá un archivo: `N deleted`.
2. **Mirá qué trae la búsqueda para las trampas.** Estos son nuestros top-1 con `bge-m3`:

   | Pregunta | Top-1 | Score | ¿Es el chunk correcto? |
   |----------|-------|------:|------------------------|
   | How much did Project Lumen speed up reconciliation? | Project Lumen | 0.65 | ✓ |
   | ¿Usó Kubernetes? | Infrastructure | 0.51 | ✓ |
   | Has she worked with JavaScript? | profile § Summary | 0.50 | no hay chunk correcto |
   | ¿Tiene experiencia en CRM? | skills § Data and messaging | 0.52 | ✗ (era Integrations, con HubSpot) |
   | What is her favourite football team? | profile § Contact | 0.41 | no hay chunk correcto |

   Tres cosas para mirar:

   - **Los scores son más bajos que en el paso 1.** Un chunk entero tiene más palabras que una oración suelta, y eso diluye la similitud.
   - **La trampa de CRM se reproduce:** el chunk de HubSpot ni siquiera entra en el top 3. Cambiá "HubSpot" por "HubSpot (CRM)" en `kb.example/experience/northwind-payments.md`, re-ingestá y volvé a mirar.
   - **La trampa de JavaScript no salió como esperábamos.** El chunk de Java no aparece arriba: dentro de un chunk largo, "Java" pesa poco. Pero el score (0.50) queda **casi igual** al de la pregunta de Kubernetes (0.51), que sí tiene respuesta. Ningún umbral los separa bien. Lo vamos a ver en los pasos 4 y 5.
3. **Cambiá `EMBED_MODEL`** a otro modelo (por ejemplo `nomic-embed-text`, después de `ollama pull` y de agregarlo a `config/models.yaml`) y corré `make ingest`. Leé el error.
