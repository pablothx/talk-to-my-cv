# Paso 6: Búsqueda híbrida con OpenSearch

🇬🇧 [Read in English](README.md)

Hasta acá buscábamos solo por significado. En este paso sumamos la búsqueda por **palabras exactas**, la de toda la vida, y probamos combinar las dos. Con la eval del paso 5 vamos a ver si sirve, con números.

## Qué vas a aprender

- Qué es **BM25** (búsqueda por palabras) y en qué se diferencia de la búsqueda por vectores.
- Cómo combinar las dos en una **búsqueda híbrida** con OpenSearch.
- A cambiar de base vectorial sin tocar el resto del código, gracias a una interfaz común.
- A comprobar una hipótesis con la eval, aunque el resultado no sea el esperado.

---

## Pieza 1 de 8: dos formas de buscar

| | Vectores | Palabras (BM25) |
|---|---|---|
| Compara | significados | palabras exactas |
| "trabajé con AWS" vs "I worked with AWS" | muy parecidas | sin palabras en común... salvo "AWS" |
| "Java" vs "JavaScript" | casi iguales (0.84, paso 1) | palabras distintas |
| Pregunta en español, CV en inglés | funciona (`bge-m3` es multilingüe) | casi siempre falla |

Cada una es buena donde la otra es mala.

## Pieza 2 de 8: qué es BM25

BM25 es la búsqueda de texto clásica, la que usan los buscadores hace décadas. Da más puntos a un chunk cuando:

- tiene **las palabras de la pregunta**;
- esas palabras son **raras** en el conjunto ("Kubernetes" vale más que "experience", que aparece en todos lados);
- el chunk es **corto** (una palabra en un texto corto pesa más que en uno largo).

No entiende significados: "nube" y "AWS" son palabras distintas y punto. Pero es exacta: "Java" nunca es "JavaScript".

## Pieza 3 de 8: la búsqueda híbrida

La **búsqueda híbrida** corre las dos y combina los resultados:

1. Cada búsqueda da sus scores, en escalas distintas.
2. Se normalizan los dos entre 0 y 1 (*min-max*: el mejor de cada lista vale 1 y el peor 0).
3. Se promedian, mitad y mitad.

La idea es quedarse con lo mejor de cada una.

## Pieza 4 de 8: nuestra hipótesis

"Java" y "JavaScript" dan 0.84 para el embedding. Esperábamos que BM25, que compara palabras exactas, arreglara la trampa de JavaScript.

Lo vamos a comprobar con la eval, no con una impresión.

## Pieza 5 de 8: OpenSearch

**OpenSearch** es un motor de búsqueda (el fork abierto de Elasticsearch). Hace las dos cosas en el mismo lugar: vectores y BM25. Lo sumamos a `compose.yaml`: un nodo, sin seguridad (solo para tu máquina) y 512 MB de memoria.

Para los vectores usa un índice **HNSW**: en vez de comparar la pregunta contra todos los chunks, salta por un grafo de "vecinos cercanos" y encuentra los mejores mucho más rápido. Es aproximado, pero con miles de documentos la diferencia de velocidad es enorme.

Cambiar de store son dos líneas en `.env`:

```bash
VECTOR_STORE=opensearch
SEARCH_MODE=hybrid      # vector | keyword | hybrid
```

El resto del código no se entera, porque `OpenSearchStore` implementa la misma interfaz `VectorStore` del paso 2. pgvector solo hace vectores: si le pedís `hybrid`, falla al arrancar con un mensaje claro ([ADR-0007](../../docs/adr/0007-pgvector-vector-only.md)).

## Pieza 6 de 8: un detalle que importa, el score

El umbral del paso 4 compara **similitud coseno**. Pero OpenSearch no la devuelve:

- en vectores devuelve `(1 + coseno) / 2`: un 0.769 de OpenSearch es un coseno de 0.538;
- BM25 no tiene tope y depende de todos los documentos;
- la híbrida con min-max deja **siempre** al primero en 1.0.

Si usáramos esos números, el 0.42 calibrado dejaría de tener sentido. Por eso, en todos los stores y modos, **el score es el coseno**, calculado con el vector guardado. El modo solo decide **qué chunks vuelven y en qué orden** ([ADR-0010](../../docs/adr/0010-score-is-cosine-in-every-mode.md)).

## Pieza 7 de 8: otro detalle, las palabras vacías

Con el analizador estándar, "Has she worked with JavaScript?" encontraba chunks por "she" y "with". La lista de palabras vacías de Lucene en inglés no incluye "she" ni "has".

Un **analizador** es lo que prepara el texto para BM25. Usamos uno propio que:

- descarta palabras vacías en inglés y en español ("the", "de", "with"...);
- descarta palabras de pregunta ("she", "did", "qué", "usó"...);
- saca los acentos ("tecnología" = "tecnologia");
- usa un *stemmer* suave (`kstem`), que lleva las palabras a su raíz ("leads" → "lead").

## Pieza 8 de 8: los tests de contrato, ahora con tres stores

Los tests de contrato del paso 2 ahora corren contra **tres** stores (memoria, pgvector y OpenSearch) y exigen lo mismo a los tres, incluido que el score sea exactamente el coseno.

| Archivo | Qué hace |
|---------|----------|
| `compose.yaml` | Agrega OpenSearch 2.19. |
| `src/talk_to_my_cv/store_opensearch.py` | `OpenSearchStore`: índice de vectores (HNSW) + texto con el analizador propio, y la búsqueda híbrida. |
| `src/talk_to_my_cv/store.py` | `supported_modes` por store, y `build_store()` para elegir por configuración. |

---

## Cómo comprobar que anda

```bash
docker compose up -d        # OpenSearch tarda ~1 minuto en arrancar
make check-06
VECTOR_STORE=opensearch make ingest
VECTOR_STORE=opensearch SEARCH_MODE=hybrid make ask DEBUG=1 Q="How big is the team she leads?"
make eval-all               # todas las combinaciones: ~9 min en CPU
```

## Los resultados

`make eval-all`, con las mismas 20 preguntas y el umbral 0.42:

| Store · modo | hit@5 | MRR | refusal accuracy | answer accuracy |
|---|---:|---:|---:|---:|
| pgvector · vector | 1.00 | 0.82 | 0.88 | 0.82 |
| opensearch · vector | 1.00 | 0.82 | 0.88 | 0.82 |
| opensearch · keyword | 0.64 | 0.52 | 0.71 | 0.71 |
| **opensearch · hybrid** | 1.00 | **0.86** | 0.88 | 0.82 |
| pgvector · hybrid | *skipped* | | | |

Las trampas:

| Trampa | vector | keyword | hybrid |
|---|:-:|:-:|:-:|
| JavaScript (debe rechazar) | ✗ dice "No" | **✓ rechaza** | ✗ dice "No" |
| CRM / HubSpot (debe responder) | ✗ | ✗ | ✗ |
| Kubernetes (debe decir "no") | ✓ | ✓ | ✓ |

Cuatro cosas para mirar:

1. **pgvector y OpenSearch dan exactamente lo mismo en modo vector.** Es la prueba de que el score coseno es consistente entre stores.
2. **La híbrida mejora el orden, no los aciertos.** El MRR sube de 0.82 a 0.86. En "How big is the team she leads?", vectores ponía primero `Contact`; la híbrida pone primero `Senior Backend Engineer`, que contiene "team" y "leads".
3. **La hipótesis de JavaScript era a medias correcta.** BM25 sí sirve: como "JavaScript" no aparece en ningún chunk, **la búsqueda por palabras devuelve cero resultados** y se rechaza sin llamar al LLM. Pero la híbrida **pierde esa señal**, porque su mitad vectorial siempre trae algo. La información útil ("ninguna palabra clave de la pregunta está en el CV") existe, pero la mezcla la tapa. Es un buen candidato para el paso 7.
4. **Solo por palabras es mucho peor** (0.71), sobre todo en español: "¿Qué idiomas habla?" no comparte ninguna palabra con "Spanish, English, Esperanto". BM25 no traduce.

**CRM no lo arregla nadie:** la palabra "CRM" no está en el CV. La solución sigue siendo escribir "HubSpot (CRM)".

## Para jugar

1. **Mirá la señal que se pierde.** Con `VECTOR_STORE=opensearch`, compará `SEARCH_MODE=keyword` y `SEARCH_MODE=hybrid` en `make ask DEBUG=1 Q="Has she worked with JavaScript?"`. ¿Cómo combinarías las dos sin perder el "cero resultados"?
2. **Cambiá los pesos.** En `store_opensearch.py`, la híbrida promedia con pesos `[0.5, 0.5]`. Probá `[0.3, 0.7]` y `[0.7, 0.3]`, y corré `make eval STORE=opensearch MODE=hybrid`. Cuidado: elegir los pesos mirando estas 20 preguntas es sobreajustar (paso 5).
3. **Sacá el analizador propio.** Cambiá `embed_text` a `"analyzer": "standard"`, borrá el índice (`make ingest REBUILD=1` con `VECTOR_STORE=opensearch`) y mirá qué trae `SEARCH_MODE=keyword` para "Has she worked with JavaScript?".

## Limitaciones conocidas

- **El analizador mezcla dos idiomas** con un stemmer de inglés. Para un CV solo en español conviene el analizador `spanish` de OpenSearch.
- **Algunas palabras de pregunta están en la lista de vacías,** como "worked" y "used": no aportan al preguntar, pero es una heurística, no una ley.
- **OpenSearch corre sin seguridad.** Está bien en tu máquina; en AWS, ver la [guía de producción](../../docs/produccion-en-aws.md).

---

## Preguntas frecuentes

<details>
<summary><b>¿Necesito OpenSearch para un CV?</b></summary>

No. Para 20 chunks, pgvector alcanza y sobra. OpenSearch tiene sentido con miles de documentos, cuando la búsqueda por palabras exactas importa (códigos, nombres de productos) o para aprender la arquitectura que usarías en una empresa.
</details>

---

## ✋ Repaso

**1. ¿En qué es buena BM25 y en qué es mala?**

<details><summary>Ver respuesta</summary>

Buena: palabras exactas y nombres raros ("Java" nunca es "JavaScript"). Mala: sinónimos y otros idiomas ("nube" no encuentra "AWS"; "idiomas" no encuentra "languages").
</details>

**2. ¿Por qué el score es siempre el coseno, aunque OpenSearch devuelva otros números?**

<details><summary>Ver respuesta</summary>

Porque el umbral (0.42) se calibró con cosenos. Con los números de OpenSearch (`(1+coseno)/2`, BM25 sin tope, min-max) el umbral dejaría de tener sentido. El modo decide qué chunks vuelven; el score es siempre el mismo.
</details>

**3. ¿Por qué la híbrida no arregla JavaScript, si BM25 sola sí?**

<details><summary>Ver respuesta</summary>

Porque la mitad vectorial siempre trae algo con un coseno alto. El "cero resultados" de BM25 se pierde en la mezcla.
</details>

**4. 🧪 Probalo:** con `VECTOR_STORE=opensearch SEARCH_MODE=keyword`, preguntá "¿Qué idiomas habla?". ¿Qué esperás?

<details><summary>Ver respuesta</summary>

Que falle: "idiomas" y "habla" no aparecen en el CV en inglés. BM25 no traduce. El paso 7 lo arregla reformulando la pregunta en inglés.
</details>

**5. ¿Qué prueba que pgvector y OpenSearch den exactamente lo mismo en modo vector?**

<details><summary>Ver respuesta</summary>

Que la interfaz común y el score coseno funcionan: podés cambiar de base sin que cambien los resultados. Los tests de contrato lo exigen.
</details>

---

[← Paso 5](../05-evaluation/README.es.md) · [Índice](../../README.es.md) · [Siguiente: Paso 7, LangGraph →](../07-langgraph/README.es.md)
