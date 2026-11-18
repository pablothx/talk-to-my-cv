# Paso 7: LangGraph y verificación

🇬🇧 [Read in English](README.md)

## Qué vas a aprender

- A escribir el flujo del RAG como un **grafo** con LangGraph: nodos, estado y ruteo condicional.
- A agregar una **verificación** antes de responder, y por qué un modelo chico es mal juez.
- Un patrón que sirve mucho con modelos chicos: **el LLM extrae, el código decide**.
- A **reformular** la pregunta para que la búsqueda por palabras entienda preguntas en español.

## El concepto

### De una función a un grafo

Hasta el paso 6, `answer()` era una función de arriba hacia abajo: buscar, cortar, preguntarle al LLM. Cada paso nuevo (reformular, verificar) agrega un `if`, y la función se vuelve difícil de leer y de testear.

LangGraph lo escribe como un grafo: cada **nodo** es una función que lee el **estado** y devuelve lo que cambia, y las **aristas condicionales** deciden a qué nodo se va después.

```
   [reformular] → buscar → corte ─┬─ nada supera el umbral ──────────────→ rechazar
                                  └─ verificar ─┬─ falta un nombre ──────→ rechazar
                                                └─ si no → responder con citas
```

`reformular` solo corre en los modos `keyword` e `hybrid` (más abajo, por qué).

### La verificación que no anduvo

El [ADR-0009](../../docs/adr/0009-top1-gate-does-not-separate-alone.md) pedía, después de la búsqueda, una verificación con el LLM. La idea obvia es preguntarle: "¿este CONTEXTO responde la PREGUNTA? Contestá SÍ o NO".

La probamos con `qwen2.5:3b` en 7 preguntas con respuesta conocida, con tres prompts distintos:

| Pregunta | Esperado | Prompt A | Prompt B | Prompt C |
|---|:-:|:-:|:-:|:-:|
| How much did Project Lumen speed up reconciliation? | SÍ | ✓ | ✓ | ✗ |
| Has she used Kubernetes in production? | SÍ | ✗ | ✗ | ✗ |
| Has she worked with JavaScript? | NO | ✓ | ✓ | ✓ |
| ¿Trabajó con Azure? | NO | ✓ | ✓ | ✓ |
| ¿Dónde trabaja actualmente y qué rol tiene? | SÍ | ✗ | ✗ | ✗ |
| What is her tech stack? | SÍ | ✓ | ✓ | ✓ |

Ante la duda, el modelo dice que NO. Como verificador, rechazaría preguntas que sí tienen respuesta. **Un modelo de 3B es mal juez.**

### El LLM extrae, el código decide

El mismo modelo sí es bueno para una tarea más chica: **extraer** el nombre concreto por el que se pregunta.

| Pregunta | El LLM extrae |
|---|---|
| Has she worked with JavaScript? | `JavaScript` |
| ¿Trabajó con Azure? | `Azure` |
| ¿Usó Kubernetes? | `Kubernetes` |
| What is her tech stack? | `NONE` |
| ¿Dónde estudió? | `NONE` |

Después, **el código** se fija si ese nombre aparece en los chunks que pasaron el corte: palabra completa, sin importar mayúsculas ni acentos. "Java" no cuenta como "JavaScript". Si falta, rechaza sin escribir una respuesta. Si la pregunta es general (`NONE`), deja que decida el prompt de respuesta del paso 4.

Es la señal que encontramos en el paso 6 ("ninguna palabra de la pregunta está en la KB"), pero ahora anda en **cualquier** store y modo, también con pgvector, y con preguntas en español, porque el extractor escribe los nombres en inglés ([ADR-0011](../../docs/adr/0011-verify-by-extracting-names-not-by-judging.md)).

> **El patrón:** no le pidas a un modelo chico que juzgue. Pedile que extraiga algo concreto, y hacé la comparación con código, que no se equivoca ni se deja convencer.

### Reformular para la búsqueda por palabras

BM25 no traduce: "¿Qué idiomas habla?" no comparte ninguna palabra con "Spanish, English, Esperanto". En los modos `keyword` e `hybrid`, el grafo primero le pide al LLM que reescriba la pregunta como palabras clave en inglés, y esa es la consulta de BM25.

El **vector** sigue saliendo de la pregunta original. Así el umbral calibrado en el paso 5 sigue valiendo, porque se calibró con preguntas, no con palabras clave. En modo `vector` no hay nada que reformular, y el nodo no corre.

## El código

| Archivo | Qué hace |
|---------|----------|
| `src/talk_to_my_cv/graph.py` | El grafo: los nodos `reformulate`, `retrieve`, `verify`, `generate` y `refuse`; `parse_terms()` y `mentions()`, y `answer_with_graph()`. |
| `src/talk_to_my_cv/rag.py` | El pipeline del paso 3, sin cambios. `Answer` suma `verified` y `query`. |
| `src/talk_to_my_cv/cli.py` | `ENGINE=pipeline` o `ENGINE=graph` elige cuál usar. |

`answer_with_graph()` recibe los mismos argumentos y devuelve el mismo `Answer` que `answer()`. Por eso el chat, la eval y los tests no saben cuál están usando. El pipeline queda como lo escribieron las lecciones 3 a 6.

```bash
ENGINE=graph            # en .env; pipeline es el default
```

Los tests unitarios prueban cada camino del grafo con un `ScriptedChatModel` que responde en orden: el corte rechaza sin llamar al LLM, un nombre que falta rechaza sin escribir una respuesta, `NONE` deja decidir al prompt, y reformular cambia la consulta de BM25 pero no el vector.

## Cómo comprobar que anda

```bash
make check-07
ENGINE=graph make ask DEBUG=1 Q="Has she worked with JavaScript?"
ENGINE=graph make ask DEBUG=1 Q="Has she used Kubernetes in production?"
make eval ENGINE=graph                                   # ~1.5 min en CPU
make eval ENGINE=graph STORE=opensearch MODE=keyword     # ~2 min
```

Con `DEBUG=1` ves la consulta reformulada (si hubo) y si los nombres de la pregunta estaban en el contexto.

## Los resultados

Las mismas 20 preguntas, umbral 0.42:

| Store · modo | Motor | hit@5 | MRR | refusal acc. | answer acc. | Tiempo |
|---|---|---:|---:|---:|---:|---:|
| pgvector · vector | pipeline | 1.00 | 0.82 | 0.88 | 0.82 | ~1:30 |
| pgvector · vector | **graph** | 1.00 | 0.82 | 0.88 | 0.82 | 1:35 |
| opensearch · hybrid | pipeline | 1.00 | 0.86 | 0.88 | 0.82 | — |
| opensearch · hybrid | **graph** | 1.00 | 0.86 | 0.88 | 0.82 | 2:02 |
| opensearch · keyword | pipeline | 0.64 | 0.52 | 0.71 | 0.71 | — |
| opensearch · keyword | **graph** | **0.82** | **0.77** | **0.82** | **0.76** | 1:55 |

Las trampas:

| Trampa | pipeline | graph |
|---|:-:|:-:|
| JavaScript (debe rechazar) | ✗ dice "No" | **✓ rechaza** |
| CRM / HubSpot (debe responder) | ✗ | ✗ |
| Kubernetes (debe decir "no") | ✓ | ✓ |

Lo que hay que mirar:

1. **JavaScript se arregla en todos los stores y modos.** El extractor saca `JavaScript`, el código no lo encuentra en el contexto y rechaza. Antes solo lo lograba el modo keyword del paso 6.
2. **Azure ahora se rechaza por una regla, no por suerte.** Con el pipeline también se rechazaba, pero porque el LLM decidía rechazar, y eso no siempre pasa (paso 4). Ahora lo rechaza el código, siempre igual.
3. **Las métricas de las preguntas puntuadas no cambian.** Las que fallan, fallan por otra cosa: en `degree` el chunk con la respuesta no pasa el corte (0.41); en `team-size` el único chunk que lo pasa es `Contact`, que no dice nada del equipo; y `talk` traduce el título de la charla (paso 5). Verificar no puede agregar lo que la búsqueda no trajo.
4. **Reformular salva a la búsqueda por palabras:** hit@5 pasa de 0.64 a 0.82 y MRR de 0.52 a 0.77, porque las preguntas en español llegan a BM25 en inglés.
5. **Cuesta poco.** Extraer un nombre genera muy pocos tokens: en CPU, el grafo tarda casi lo mismo que el pipeline.

**CRM sigue sin arreglo,** y ahora se rechaza a propósito: el extractor saca `CRM` y la KB nunca lo nombra. La solución sigue siendo escribir "HubSpot (CRM)" en la KB.

**El objetivo de refusal accuracy ≥ 0.9 sigue sin cumplirse (0.88).** Los dos errores que quedan son rechazos de más (`team-size` y `degree`), y en los dos el chunk con la respuesta no supera el umbral. Bajar el umbral ahora que hay verificación es tentador, pero se calibraría con las mismas 20 preguntas (paso 5).

## Para jugar

1. **Probá el juez.** En `graph.py`, cambiá `verify` para que le pregunte al LLM "¿el CONTEXTO responde la PREGUNTA? SÍ o NO" y use la respuesta directo. Corré `make eval ENGINE=graph`. ¿Cuántas preguntas con respuesta rechaza? Si tenés una key de Groq, probalo con `LLM_PROVIDER=groq`: ¿un modelo de 70B juzga mejor?
2. **Bajá el umbral.** Ahora que la verificación atrapa los nombres que faltan, probá `make eval ENGINE=graph THRESHOLD=0.40`. ¿Se salvan `team-size` y `degree`? ¿Qué preguntas sin respuesta pasan ahora? Acordate del sobreajuste.
3. **Engañá al extractor.** Escribí preguntas que nombren algo con otras palabras: "¿Usó K8s?", "¿Programó en JS?". ¿Qué extrae? ¿Rechaza aunque la KB diga "Kubernetes"?

## Limitaciones conocidas

- **Sinónimos y siglas:** "K8s" no encuentra "Kubernetes", y "CRM" no encuentra "HubSpot". La verificación es tan literal como la KB.
- **Preguntas sin nombres:** "¿Cuánto cobra?" no nombra nada, así que la verificación no la puede atrapar. Esas siguen dependiendo del corte y del prompt.
- **Una llamada más al LLM** por pregunta que pasa el corte (dos en `keyword` e `hybrid`). En CPU es poco, porque las respuestas son cortas; con un modelo remoto es una llamada de red más.
