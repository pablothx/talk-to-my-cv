# Paso 7: LangGraph y verificación

🇬🇧 [Read in English](README.md)

El chat todavía cae en la trampa de JavaScript: responde "No" con citas, cuando el CV no dice nada. En este paso agregamos una **verificación** antes de responder, y reescribimos el flujo como un **grafo**. Acá entra, por primera vez, un framework: LangGraph.

## Qué vas a aprender

- A escribir el flujo de un RAG como un **grafo**: nodos, estado y ruteo condicional.
- Por qué un modelo chico es **mal juez**, medido.
- Un patrón que sirve mucho con modelos chicos: **el LLM extrae, el código decide**.
- A **reformular** la pregunta para que la búsqueda por palabras entienda español.

---

## Pieza 1 de 7: de una función a un grafo

Hasta el paso 6, `answer()` era una función de arriba hacia abajo: buscar, cortar, preguntarle al LLM. Cada paso nuevo (reformular, verificar) agregaría un `if`, y la función se volvería difícil de leer y de testear.

LangGraph lo escribe como un **grafo**:

- cada **nodo** es una función que lee el **estado** (un diccionario con la pregunta, los chunks, etc.) y devuelve lo que cambia;
- las **aristas condicionales** deciden a qué nodo se va después.

```
   [reformular] → buscar → corte ─┬─ nada llega al umbral ───────────────→ rechazar
                                  └─ verificar ─┬─ falta un nombre ──────→ rechazar
                                                └─ si no → responder con citas
```

`reformular` solo corre en los modos `keyword` e `hybrid` (pieza 6).

¿Por qué LangGraph recién ahora? Porque hasta acá el flujo era una línea recta y no hacía falta ([ADR-0003](../../docs/adr/0003-own-seams-no-langchain-before-step-7.md)). Ahora hay ramas.

## Pieza 2 de 7: la verificación que no anduvo

El paso 5 pidió una verificación después de la búsqueda. La idea obvia es preguntarle al LLM: "¿este CONTEXTO responde la PREGUNTA? Contestá SÍ o NO".

La probamos con `qwen2.5:3b` en 6 preguntas con respuesta conocida, con tres prompts distintos:

| Pregunta | Esperado | Prompt A | Prompt B | Prompt C |
|---|:-:|:-:|:-:|:-:|
| How much did Project Lumen speed up reconciliation? | SÍ | ✓ | ✓ | ✗ |
| Has she used Kubernetes in production? | SÍ | ✗ | ✗ | ✗ |
| Has she worked with JavaScript? | NO | ✓ | ✓ | ✓ |
| ¿Trabajó con Azure? | NO | ✓ | ✓ | ✓ |
| ¿Dónde trabaja actualmente y qué rol tiene? | SÍ | ✗ | ✗ | ✗ |
| What is her tech stack? | SÍ | ✓ | ✓ | ✓ |

Ante la duda, el modelo dice que NO. Como verificador, rechazaría preguntas que sí tienen respuesta. **Un modelo de 3B es mal juez.**

## Pieza 3 de 7: el LLM extrae

El mismo modelo sí es bueno para una tarea más chica: **extraer** el nombre concreto por el que se pregunta.

| Pregunta | El LLM extrae |
|---|---|
| Has she worked with JavaScript? | `JavaScript` |
| ¿Trabajó con Azure? | `Azure` |
| ¿Usó Kubernetes? | `Kubernetes` |
| What is her tech stack? | `NONE` |
| ¿Dónde estudió? | `NONE` |

`NONE` quiere decir "esta pregunta no nombra nada específico".

## Pieza 4 de 7: el código decide

Después, **el código** se fija si ese nombre aparece en los chunks que pasaron el corte:

- palabra completa: "Java" **no** cuenta como "JavaScript";
- sin importar mayúsculas ni acentos.

| Resultado | Qué hace |
|---|---|
| El nombre está en el contexto | Sigue y responde. |
| El nombre **no** está | Rechaza, sin escribir una respuesta. |
| `NONE` (pregunta general) | Sigue: decide el prompt del paso 4. |

Si la pregunta nombra varias cosas ("¿Usó Kafka y Flink?"), alcanza con que **una** esté: la respuesta puede ser parcial ("Kafka sí; de Flink no hay información").

Es la señal que encontramos en el paso 6 ("ninguna palabra de la pregunta está en el CV"), pero ahora anda en **cualquier** store y modo, también con pgvector, y con preguntas en español, porque el extractor escribe los nombres en inglés ([ADR-0011](../../docs/adr/0011-verify-by-extracting-names-not-by-judging.md)).

> **El patrón:** no le pidas a un modelo chico que juzgue. Pedile que extraiga algo concreto, y hacé la comparación con código, que no se equivoca ni se deja convencer.

## Pieza 5 de 7: cuando el extractor responde cualquier cosa

Un modelo chico a veces no responde lo pedido: escribe una oración, explica, o lista categorías ("technologies"). El código (`parse_terms()`) se protege:

- si algún "nombre" tiene más de 4 palabras, es charla y no una lista: se descarta todo y se toma como "no hay nombres";
- se limpian comillas, asteriscos y puntos que el modelo agrega.

Ante la duda, **no rechaza**: deja que siga el flujo normal. Es mejor perder una verificación que rechazar una pregunta buena.

## Pieza 6 de 7: reformular para la búsqueda por palabras

BM25 no traduce: "¿Qué idiomas habla?" no comparte palabras con "Spanish, English, Esperanto". En los modos `keyword` e `hybrid`, el grafo primero le pide al LLM que reescriba la pregunta como palabras clave en inglés, y esa es la consulta de BM25.

El **vector** sigue saliendo de la pregunta original. Así el umbral sigue valiendo, porque se calibró con preguntas, no con palabras clave. En modo `vector` no hay nada que reformular y el nodo no corre.

## Pieza 7 de 7: mismo contrato, otro motor

Ahora hay dos **motores** (*engines*), dos formas de convertir una pregunta en respuesta:

- **pipeline**: la cadena fija de los pasos 3 a 6, `answer()` en `rag.py`. Siempre los mismos pasos, en el mismo orden.
- **graph**: el grafo de este paso, `answer_with_graph()` en `graph.py`, con desvíos (reformular, verificar).

`answer_with_graph()` recibe los mismos argumentos y devuelve el mismo `Answer` que `answer()`. Por eso el chat, la eval y la API no saben cuál están usando:

```bash
ENGINE=graph            # en .env; pipeline es el default
```

El pipeline queda como lo escribieron las lecciones 3 a 6.

| Archivo | Qué hace |
|---------|----------|
| `src/talk_to_my_cv/graph.py` | Los nodos `reformulate`, `retrieve`, `verify`, `generate` y `refuse`; `parse_terms()`, `mentions()` y `answer_with_graph()`. |
| `src/talk_to_my_cv/engines.py` | `ENGINES`: `pipeline` o `graph`. |
| `src/talk_to_my_cv/rag.py` | El pipeline, sin cambios. `Answer` suma `verified` y `query`. |

Los tests unitarios prueban cada camino del grafo con un `ScriptedChatModel`, un LLM falso que responde lo que le guionás, en orden.

---

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

1. **JavaScript se arregla en todos los stores y modos.** El extractor saca `JavaScript`, el código no lo encuentra y rechaza.
2. **Azure ahora se rechaza por una regla, no por suerte.** Antes lo rechazaba el LLM cuando quería; ahora el código, siempre igual.
3. **Las métricas de las preguntas puntuadas no cambian.** Las que fallan, fallan por otra cosa: en `degree` el chunk con la respuesta no pasa el corte (0.41); en `team-size` el único chunk que lo pasa es `Contact`; `talk` traduce el título de la charla (paso 5). **Verificar no puede agregar lo que la búsqueda no trajo.**
4. **Reformular salva a la búsqueda por palabras:** hit@5 pasa de 0.64 a 0.82, porque las preguntas en español llegan a BM25 en inglés.
5. **Cuesta poco.** Extraer un nombre genera muy pocas palabras: el grafo tarda casi lo mismo que el pipeline.

**CRM sigue sin arreglo,** y ahora se rechaza a propósito: el extractor saca `CRM` y el CV nunca lo nombra. La solución sigue siendo "HubSpot (CRM)".

**El objetivo de ≥ 0.9 sigue sin cumplirse (0.88).** Los dos errores que quedan son rechazos de más, en los dos el chunk correcto no llega al umbral. Bajar el umbral ahora es tentador, pero se calibraría con las mismas 20 preguntas.

## Para jugar

1. **Probá el juez.** En `graph.py`, cambiá `verify` para que pregunte "¿el CONTEXTO responde la PREGUNTA? SÍ o NO" y use la respuesta directo. Corré `make eval ENGINE=graph`. ¿Cuántas preguntas buenas rechaza?
2. **Bajá el umbral.** Probá `make eval ENGINE=graph THRESHOLD=0.40`. ¿Se salvan `team-size` y `degree`? ¿Qué preguntas sin respuesta pasan ahora? Acordate del sobreajuste.
3. **Engañá al extractor.** "¿Usó K8s?", "¿Programó en JS?". ¿Qué extrae? ¿Rechaza aunque el CV diga "Kubernetes"?

## Limitaciones conocidas

- **Sinónimos y siglas:** "K8s" no encuentra "Kubernetes", y "CRM" no encuentra "HubSpot". La verificación es tan literal como el CV.
- **Preguntas sin nombres:** "¿Cuánto cobra?" no nombra nada, así que la verificación no la atrapa. Esas dependen del corte y del prompt.
- **Una llamada más al LLM** por pregunta que pasa el corte (dos en `keyword` e `hybrid`).

---

## Preguntas frecuentes

<details>
<summary><b>Si el CV nombra "Marcos" en otro contexto, ¿la verificación lo deja pasar?</b></summary>

Sí. La verificación solo comprueba que el nombre **aparezca** en los chunks recuperados, no que se hable de lo mismo. Si preguntás por el "profeta Marcos" y aparece "Juan Marcos" en un pedazo, pasa, y la respuesta va a hablar de ese Marcos. Es una verificación barata y literal, no una comprensión.
</details>

<details>
<summary><b>¿Con un modelo grande serviría el juez SÍ/NO?</b></summary>

Probablemente mucho mejor: los modelos grandes juzgan bastante bien. Pero hay que medirlo con la eval, igual que hicimos acá. Y el patrón "extraer + comparar con código" sigue siendo más barato y repetible.
</details>

---

## ✋ Repaso

**1. ¿Por qué pasar de una función a un grafo?**

<details><summary>Ver respuesta</summary>

Porque el flujo ahora tiene ramas (rechazar en el corte, rechazar en la verificación, responder). Con un grafo, cada paso es un nodo que se testea solo, y el ruteo queda explícito en vez de enterrado en `if`s.
</details>

**2. ¿Qué falló del juez SÍ/NO?**

<details><summary>Ver respuesta</summary>

Ante la duda, `qwen2.5:3b` dice NO: rechazaba preguntas con respuesta (Kubernetes, dónde trabaja). Un modelo chico es mal juez.
</details>

**3. ¿Qué es "el LLM extrae, el código decide"?**

<details><summary>Ver respuesta</summary>

Pedirle al modelo una tarea chica y concreta (sacar el nombre de la pregunta) y hacer la decisión con código determinístico (¿está ese nombre en los chunks?). El código no se equivoca ni se deja convencer.
</details>

**4. 🧪 Probalo:** `ENGINE=graph make ask DEBUG=1 Q="Has she worked with JavaScript?"`. ¿Qué esperás en el debug?

<details><summary>Ver respuesta</summary>

`named terms in the context: NO → refuse` y el rechazo fijo. El extractor saca "JavaScript", y ningún chunk la contiene como palabra completa ("Java" no cuenta).
</details>

**5. ¿Por qué el vector sale de la pregunta original y no de la reformulada?**

<details><summary>Ver respuesta</summary>

Porque el umbral se calibró con preguntas, no con listas de palabras clave. Si el vector saliera de la reformulación, los scores cambiarían y el 0.42 dejaría de valer.
</details>

---

[← Paso 6](../06-hybrid-search/README.es.md) · [Índice](../../README.es.md) · [Siguiente: Paso 8, API y web →](../08-api-and-web/README.es.md)
