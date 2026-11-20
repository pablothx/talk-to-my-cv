# Paso 2: Chunking e ingesta

🇬🇧 [Read in English](README.md)

En este paso convertimos el CV en filas de una base de datos: cada fila es un pedazo con su texto, su origen y su embedding. Es la **ingesta**, y se corre una vez (y cada vez que cambia el CV).

## Qué vas a aprender

- Por qué un RAG no busca documentos enteros, sino **pedazos** (chunks).
- Cómo cortar un CV para que cada pedazo se pueda **citar**.
- Qué se guarda en cada columna de la tabla, y por qué.
- Cómo hacer una ingesta **idempotente**: correrla diez veces da lo mismo que correrla una.
- Por qué nunca hay que mezclar vectores de dos modelos.

---

## Pieza 1 de 10: por qué cortar

Si embebés un CV entero en un solo vector, ese vector habla "de todo un poco" y no se parece mucho a ninguna pregunta concreta. Por eso cortamos el documento en pedazos chicos, cada uno con un tema claro, y embebemos cada uno.

## Pieza 2 de 10: el CV de ejemplo

`kb.example/` es el CV de **Valentina Ríos**, una persona ficticia. Son 6 archivos Markdown:

```
kb.example/
├── profile.md                       resumen, idiomas, contacto
├── skills.md                        tecnologías
├── education.md
├── projects.md
└── experience/
    ├── northwind-payments.md        su trabajo actual
    └── brightcart.md                su trabajo anterior
```

Tiene **datos plantados**: cosas imposibles de adivinar, como que Project Lumen bajó la conciliación "de 9 horas a 14 minutos". Si el chat responde eso, sabemos que lo leyó del documento y no lo inventó. También tiene **trampas** para la evaluación (paso 5).

## Pieza 3 de 10: cómo cortamos

Cortamos **por títulos de Markdown**, que es como una persona ya organizó su CV:

- cada `##` (H2) es un chunk;
- si el H2 tiene `###` (H3) adentro, cada H3 es su propio chunk;
- si una sección pasa de ~1500 caracteres (media página), se corta por párrafos, **nunca a mitad de un párrafo**.

Cada línea del documento cae en algún chunk: no se pierde nada. El CV de Valentina queda en **19 chunks**.

## Pieza 4 de 10: el frontmatter

Cada archivo empieza con un bloque de datos, el *frontmatter*:

```yaml
---
type: experience
title: Northwind Payments
company: Northwind Payments
role: Senior Backend Engineer
start: 2021-04
end: present
tags: [java, aws, kafka, payments]
---
```

Se copia como `metadata` a cada chunk del archivo. El `title` se usa en la ruta de títulos (pieza 6). El resto se guarda pero **hoy no se usa** para buscar: queda listo para filtrar en el futuro (por ejemplo, "solo experiencia" o "solo esta persona"), sin tener que volver a ingestar.

## Pieza 5 de 10: la tabla

Cada chunk es una fila de la tabla `chunks` en Postgres:

| Columna | Ejemplo | Para qué |
|---|---|---|
| `id` | `7e9435d0b4dacd6f` | Identifica el chunk (pieza 7). |
| `content_hash` | `d9d676b4151156a9` | Detecta si el chunk cambió (pieza 7). |
| `file` | `experience/northwind-payments.md` | De dónde salió. |
| `section` | `Senior Backend Engineer > Project Lumen` | La ruta de títulos. Con `file`, forma la **cita**. |
| `text` | `Led Project Lumen, a ledger…` | El texto del pedazo, limpio. |
| `embed_text` | `Northwind Payments > Senior Backend Engineer > Project Lumen` + el texto | Lo que se embebe y lo que lee el LLM (pieza 6). |
| `metadata` | `{"company": "Northwind Payments", ...}` | El frontmatter. |
| `embedding` | `[-0.028, 0.012, ...]` | 1024 números, de `embed_text`. |

Podés mirarla vos mismo:

```bash
docker compose exec postgres psql -U postgres -d talk_to_my_cv
```

```sql
\d chunks
select file, section from chunks;
```

## Pieza 6 de 10: por qué `embed_text` lleva los títulos adelante

El chunk de Project Lumen dice *"Led Project Lumen, a ledger reconciliation engine..."*. En ninguna parte dice **Northwind Payments**: eso está en el título del archivo.

Si preguntás "¿qué hizo en Northwind?", sin los títulos ese chunk no se parecería a la pregunta. Por eso el texto que se embebe es **la ruta de títulos + el texto**:

```
Northwind Payments > Senior Backend Engineer > Project Lumen

Led Project Lumen, a ledger reconciliation engine...
```

Y el LLM recibe **lo mismo**: si la búsqueda encontró el chunk gracias a "Northwind", el LLM tiene que poder leer "Northwind". Esto lo aprendimos a la fuerza en el paso 5.

## Pieza 7 de 10: la ingesta idempotente

Embeber es lo caro. No queremos re-embeber todo cada vez que cambia una coma. Cada chunk tiene dos huellas:

- un **`id`** que sale del archivo, la sección y el número de pedazo. No cambia entre corridas.
- un **`content_hash`** que sale del texto y la metadata. Cambia solo si cambia el contenido.

`make ingest` compara lo que hay en disco con lo que hay en la base:

| Situación | Qué hace |
|---|---|
| `id` nuevo | Lo agrega (y lo embebe). |
| Mismo `id`, otro `content_hash` | Lo re-embebe. |
| `id` que ya no está en disco | Lo borra. |
| Todo igual | No lo toca. |

```
kb.example: 19 added, 0 updated, 0 unchanged, 0 deleted      ← la primera vez
kb.example: 0 added, 0 updated, 19 unchanged, 0 deleted      ← la segunda
```

## Pieza 8 de 10: el candado del modelo

La base guarda con qué modelo se armó, en otra tabla, `kb_meta`:

```
 model  | dimension
--------+-----------
 bge-m3 |      1024
```

Si cambiás `EMBED_MODEL`, la ingesta **falla** con este mensaje:

```
The index was built with bge-m3 (1024 dims), but EMBED_MODEL is ... Vectors from
different models can't be compared: run `make ingest REBUILD=1` to start over.
```

Mezclar vectores de dos modelos daría búsquedas que **parecen andar pero devuelven basura**. Es mejor un error ruidoso que un error silencioso ([ADR-0005](../../docs/adr/0005-chunk-identity-and-embedding-model-lock.md)).

## Pieza 9 de 10: tu CV en PDF

Si ponés un PDF en `kb/`, la ingesta lo convierte a Markdown **en memoria**, con reglas fijas y **sin LLM** (así no puede inventar nada):

- la primera línea es el título (tu nombre);
- una línea en MAYÚSCULAS (`PROFESSIONAL EXPERIENCE`) abre una sección `##`;
- una línea que termina en un rango de años (`Senior Engineer, Acme (2021 – Present)`) abre una subsección `###`: un chunk por trabajo, con la empresa en la ruta de títulos.

Los archivos dentro de carpetas que empiezan con `_` (como `kb/_drafts/`) se ignoran.

## Pieza 10 de 10: los stores y los tests de contrato

El código no habla con Postgres directo, sino con una interfaz, `VectorStore` (`upsert`, `delete`, `search`...). Hay dos implementaciones:

- `InMemoryStore`: en memoria, para los tests. Rápido y sin Docker.
- `PgVectorStore`: Postgres con pgvector, para la vida real.

**Los mismos tests de contrato corren contra los dos.** Si la ingesta anda contra el de memoria, sabemos que anda contra Postgres. En el paso 6 se suma un tercero, OpenSearch, y los mismos tests lo validan.

| Archivo | Qué hace |
|---------|----------|
| `src/talk_to_my_cv/chunking.py` | `chunk_document(path, markdown)`: frontmatter, títulos, cortes, IDs y hashes. |
| `src/talk_to_my_cv/store.py` | `VectorStore`, `InMemoryStore` y `PgVectorStore`. |
| `src/talk_to_my_cv/ingest.py` | `ingest()`: compara, embebe lo que cambió y borra lo huérfano. |
| `src/talk_to_my_cv/pdf.py` | PDF → Markdown con reglas fijas. |

---

## Cómo comprobar que anda

```bash
make check-02
make ingest
```

## Para jugar

1. **Editá una sección** de `kb.example/profile.md` y corré `make ingest`: tiene que decir `1 updated`. Borrá un archivo: `N deleted`.
2. **Mirá qué trae la búsqueda para las trampas.** Estos son nuestros top-1:

   | Pregunta | Top-1 | Score | ¿Es el chunk correcto? |
   |----------|-------|------:|------------------------|
   | How much did Project Lumen speed up reconciliation? | Project Lumen | 0.65 | ✓ |
   | ¿Usó Kubernetes? | Infrastructure | 0.51 | ✓ |
   | Has she worked with JavaScript? | profile § Summary | 0.50 | no hay chunk correcto |
   | ¿Tiene experiencia en CRM? | skills § Data and messaging | 0.52 | ✗ (era Integrations, con HubSpot) |
   | What is her favourite football team? | profile § Contact | 0.41 | no hay chunk correcto |

   - **Los scores son más bajos que en el paso 1.** Un chunk tiene más palabras que una oración suelta, y eso diluye la similitud.
   - **La trampa de CRM se reproduce:** el chunk de HubSpot ni entra en el top 3. Cambiá "HubSpot" por "HubSpot (CRM)" en `kb.example/experience/northwind-payments.md`, re-ingestá y volvé a mirar.
   - **JavaScript y Kubernetes quedan pegados:** 0.50 y 0.51. Kubernetes tiene respuesta ("no en producción") y JavaScript no. **Un umbral sobre el top-1 no puede separarlas.** El paso 5 lo mide y el paso 7 lo resuelve.
3. **Cambiá `EMBED_MODEL`** a otro modelo (por ejemplo `nomic-embed-text`, después de `ollama pull` y de agregarlo a `config/models.yaml`) y corré `make ingest`. Leé el error.

## Limitaciones conocidas

- **Un párrafo de más de 1500 caracteres queda como un chunk grande.** Nunca cortamos a mitad de párrafo. Con PDFs pasa seguido, porque el texto extraído no trae líneas en blanco entre párrafos.
- **El chunker no distingue un título real de un `#` dentro de un bloque de código.** En un CV es raro.
- **No hay índice en pgvector.** Con 19 chunks, comparar contra todos tarda milisegundos. Con miles hace falta un índice aproximado (HNSW); lo vemos en el paso 6.
- **La columna `text` hoy no se lee.** Desde el arreglo del paso 5, el LLM recibe `embed_text`. `text` queda guardada por si querés mostrar el pedazo limpio.
- **La metadata casi no se usa.** Solo el título. Para separar personas o filtrar por tipo, habría que agregar un filtro a `search()`.

---

## Preguntas frecuentes

<details>
<summary><b>Si le paso un CV de 20 hojas, ¿lo cubre entero?</b></summary>

Sí: cada línea cae en algún chunk. Las secciones largas se parten por párrafos, así que 20 hojas pueden dar 60 u 80 chunks. Pero guardar todo no es usar todo: en cada pregunta el LLM ve solo los 5 más parecidos. Una pregunta cuya respuesta está repartida en muchos chunks ("¿cuántos años trabajó en total?") puede salir mal.
</details>

<details>
<summary><b>¿Sirve para cargar 100 CVs y preguntar "traeme los 20 con más experiencia en Java"?</b></summary>

No, así como está. Hay dos problemas:

1. **Se mezclan las personas:** el top-5 puede traer chunks de 5 personas distintas, y el LLM las mezcla. Haría falta guardar un `candidate_id` en la metadata y filtrar por persona antes de buscar.
2. **"Los 20 con más..." no es una búsqueda, es un ranking.** Hay que mirar los 100, calcular años de Java en cada uno y ordenar. Un RAG trae lo que más se *parece*, no lo que más *tiene*. Para eso se usa **extracción estructurada**: al ingestar, un LLM saca una ficha fija de cada CV (skills, años por skill) a una tabla, y se responde con SQL (`ORDER BY java_years DESC LIMIT 20`).

Ojo además con los datos personales de terceros (necesitás base legal para procesarlos) y con rankear personas con IA: la ley europea de IA lo considera de alto riesgo.
</details>

<details>
<summary><b>¿Cómo entro a la base a mirar los chunks?</b></summary>

`docker compose exec postgres psql -U postgres -d talk_to_my_cv`, y adentro `select file, section from chunks;`. Con una interfaz gráfica (DBeaver, TablePlus): host `localhost`, puerto el de `POSTGRES_PORT` (5432 por defecto), base `talk_to_my_cv`, usuario y contraseña `postgres`.
</details>

---

## ✋ Repaso

**1. ¿Por qué no embebemos el CV entero en un solo vector?**

<details><summary>Ver respuesta</summary>

Porque un vector de todo el CV habla "de todo un poco" y no se parece a ninguna pregunta concreta. Además, sin pedazos no podríamos citar de qué sección salió la respuesta.
</details>

**2. 🧪 Probalo:** corré `make ingest` dos veces seguidas. ¿Qué esperás que diga la segunda?

<details><summary>Ver respuesta</summary>

`0 added, 0 updated, 19 unchanged, 0 deleted`. Los `content_hash` no cambiaron, así que no re-embebe nada.
</details>

**3. ¿Qué diferencia hay entre `id` y `content_hash`?**

<details><summary>Ver respuesta</summary>

El `id` dice **qué** chunk es (archivo + sección + número de pedazo) y no cambia si editás el texto. El `content_hash` dice **qué contiene**, y cambia si cambia el texto o la metadata. Con los dos, la ingesta sabe si un chunk es nuevo, cambió o desapareció.
</details>

**4. ¿Por qué `embed_text` lleva la ruta de títulos adelante?**

<details><summary>Ver respuesta</summary>

Porque el texto de un chunk muchas veces no nombra la empresa ni el puesto: eso está en los títulos. Con la ruta adelante, el embedding "sabe" de qué trabajo es ese pedazo, y una pregunta por la empresa lo encuentra.
</details>

**5. Cambiaste `EMBED_MODEL` y `make ingest` falla. ¿Es un bug?**

<details><summary>Ver respuesta</summary>

No, es el candado: la base fue armada con otro modelo y sus vectores no son comparables con los nuevos. `make ingest REBUILD=1` borra todo y re-embebe con el modelo nuevo.
</details>

---

[← Paso 1](../01-embeddings/README.es.md) · [Índice](../../README.es.md) · [Siguiente: Paso 3, primer RAG →](../03-first-rag/README.es.md)
