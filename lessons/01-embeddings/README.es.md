# Paso 1: Embeddings

🇬🇧 [Read in English](README.md)

Todo RAG empieza acá: convertir texto en números que se puedan comparar. En los [fundamentos](../fundamentals/README.es.md) viste la idea; ahora la tocás con las manos.

## Qué vas a aprender

- Qué es un embedding y por qué sirve para buscar por significado.
- Cómo se comparan dos embeddings (similitud coseno), en código.
- Qué captura un embedding y, sobre todo, **qué no captura**.

---

## Pieza 1 de 8: tu primer embedding

```bash
make embed TEXT="hola"
```

```
model: bge-m3
dimension: 1024
first values: [+0.0094, +0.0229, -0.0431, +0.0009, -0.0314, ...]
```

Eso es un embedding: **1024 números** que representan el significado de "hola". Ninguno significa nada por sí solo; sirven para compararlos con los de otro texto.

## Pieza 2 de 8: compararlos

```bash
make similarity A="Trabajé con AWS" B="I worked with AWS"
```

Da **0.95**: casi lo mismo, aunque estén en idiomas distintos. Eso es lo que buscamos: **mismo significado, números parecidos**.

El número es la **similitud coseno**: 1 es "mismo significado", 0 es "nada que ver".

## Pieza 3 de 8: el coseno, en código

Está en `src/talk_to_my_cv/embeddings.py`, y son pocas líneas:

```python
def cosine_similarity(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        raise ValueError(f"vectors differ in dimension: {len(a)} vs {len(b)}")
    norms = math.hypot(*a) * math.hypot(*b)
    if norms == 0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return sum(x * y for x, y in zip(a, b, strict=True)) / norms
```

Leelo así:

- **La última línea es la cuenta:** multiplicar posición por posición, sumar (el *producto punto*) y dividir por el largo de las dos flechas (`hypot`). Dividir hace que importe solo la **dirección**, no el tamaño.
- **Las dos validaciones** evitan errores silenciosos: comparar vectores de distinto tamaño, o dividir por cero.

## Pieza 4 de 8: por qué `bge-m3`

Es **multilingüe**: una pregunta en español encuentra un texto en inglés. Por eso el CV de ejemplo está en inglés y las preguntas de evaluación mezclan los dos idiomas.

Además es gratis, corre en CPU y da vectores de 1024 números. No es "el mejor del mundo": los modelos pagos de las nubes suelen ser algo mejores, pero para un CV la diferencia casi no se nota.

## Pieza 5 de 8: el `Embedder` y por qué una interfaz propia

El código no llama a Ollama directo. Llama a una **interfaz** nuestra:

```python
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
```

`OllamaEmbedder` la implementa. ¿Por qué no usar LangChain desde el principio? Porque queremos ver y controlar cada pieza, y porque con una interfaz propia, cambiar a otro proveedor (Bedrock en AWS, por ejemplo) es escribir otra clase de 30 líneas ([ADR-0003](../../docs/adr/0003-own-seams-no-langchain-before-step-7.md)). LangChain entra recién en el paso 7, cuando hay un problema real que lo justifica.

## Pieza 6 de 8: dos detalles de `OllamaEmbedder` que importan

**1. Manda los textos en tandas y devuelve los vectores en el mismo orden.** Parece un detalle, pero si el orden se rompe, en el paso 2 cada pedazo del CV quedaría guardado con el embedding de otro, y **nada avisaría**: las búsquedas devolverían basura con total normalidad.

**2. Verifica la dimensión** contra `config/models.yaml`. Si alguien cambia de modelo sin darse cuenta, falla fuerte en vez de mezclar vectores incomparables.

Los tests unitarios usan un cliente de Ollama falso. Los tests e2e hablan con el `bge-m3` real.

## Pieza 7 de 8: lo que un embedding NO captura

Estos son nuestros resultados con `make similarity`:

| A | B | Score |
|---|---|------:|
| Trabajé con AWS | I worked with AWS *(traducción)* | 0.95 |
| Trabajé con AWS | Trabajé con Azure *(otra cosa)* | 0.83 |
| Trabajé con AWS | Usé Amazon Web Services en mi trabajo *(sinónimo)* | 0.79 |
| Trabajé con AWS | Nunca trabajé con AWS *(negación)* | **0.75** |
| Trabajé con AWS | Me gusta cocinar pasta los domingos *(sin relación)* | 0.45 |

Tres cosas para mirar:

1. **La negación casi no mueve el score.** "Trabajé con AWS" y "Nunca trabajé con AWS" dicen lo contrario y dan 0.75. Un embedding captura **de qué habla** un texto, no **qué afirma**. La búsqueda solo trae candidatos; quien lee y decide es el LLM (paso 3).
2. **"Azure" puntúa más que el sinónimo.** Comparte casi todas las palabras y el tema. Si alguien pregunta "¿trabajó con Azure?", la búsqueda va a traer el pedazo sobre AWS.
3. **"Sin relación" no da 0, da 0.45.** Cada modelo tiene su propio rango de scores. Por eso el umbral del paso 4 se configura **por modelo** y se calibra con datos en el paso 5.

## Pieza 8 de 8: dos trampas que vamos a perseguir todo el tutorial

Salieron de probar con un CV real:

| A | B | Score | Riesgo |
|---|---|------:|--------|
| Salesforce | CRM | 0.58 | **Falso rechazo**: la herramienta y su categoría quedan lejos. |
| Java | JavaScript | 0.84 | **Falso positivo**: nombres parecidos, tecnologías distintas. |

- **Salesforce vs CRM.** Si tu CV dice "Salesforce" y alguien pregunta "¿tiene experiencia con CRMs?", el chat puede rechazar algo que sí sabe. La solución está en cómo escribís el CV: nombrá la herramienta **y su categoría** ("Salesforce (CRM)").
- **Java vs JavaScript.** Para el embedding son casi lo mismo. Lo retomamos en el paso 6 (búsqueda por palabras exactas) y lo resolvemos en el paso 7.

---

## Cómo comprobar que anda

```bash
make check-01
```

Incluye tres tests contra el modelo real: que devuelve 1024 dimensiones, que una paráfrasis puntúa más alto que una oración sin relación, y que una oración en español y su traducción al inglés también.

## Para jugar

Usá `make similarity A="..." B="..."` con tus propias oraciones:

- dos tecnologías parecidas (Postgres vs MySQL);
- dos fechas distintas ("en 2019" vs "en 2023");
- tu nombre contra otro nombre;
- una oración y su negación.

Anotá los números. ¿Qué captura el embedding y qué no?

---

## Preguntas frecuentes

<details>
<summary><b>¿Qué modelo de embeddings se usa en AWS?</b></summary>

En Amazon Bedrock, los más comunes son **Amazon Titan Text Embeddings V2** (1024 números por defecto, o 256 y 512) y **Cohere Embed Multilingual**. Se usan igual: mandás texto y te devuelven números. Con nuestra interfaz `Embedder`, sería una clase nueva. Ver la [guía de producción](../../docs/produccion-en-aws.md).
</details>

<details>
<summary><b>¿Por qué coseno y no seno?</b></summary>

Con el coseno, más alto = más parecido: 1 es "misma dirección" y 0 "nada que ver". El seno da 0 tanto para flechas idénticas como para opuestas, así que no las distingue. Además, el coseno se calcula sin medir ningún ángulo: solo multiplicaciones y sumas.
</details>

---

## ✋ Repaso

**1. 🧪 Probalo:** antes de correrlo, ¿cuánto creés que da `make similarity A="Java" B="JavaScript"`?

<details><summary>Ver respuesta</summary>

Alrededor de 0.84: para el embedding son casi lo mismo. Es una de las trampas que el tutorial persigue hasta el paso 7.
</details>

**2. "Trabajé con AWS" vs "Nunca trabajé con AWS" da 0.75. ¿Qué te dice eso?**

<details><summary>Ver respuesta</summary>

Que un embedding captura de qué habla un texto, no qué afirma. La búsqueda trae candidatos por tema; quien tiene que leer y entender la negación es el LLM.
</details>

**3. ¿Qué pasaría si `OllamaEmbedder` devolviera los vectores desordenados?**

<details><summary>Ver respuesta</summary>

Cada chunk quedaría guardado con el embedding de otro, y las búsquedas devolverían chunks equivocados sin ningún error. Por eso hay tests que verifican el orden.
</details>

**4. Una oración sin relación da 0.45, no 0. ¿Por qué importa?**

<details><summary>Ver respuesta</summary>

Porque cada modelo tiene su propio rango de scores. Un umbral pensado "a ojo" (por ejemplo 0.5) puede no tener sentido. Por eso el umbral es por modelo y se calibra con datos.
</details>

**5. Tu CV dice "Salesforce". ¿Cómo lo escribirías para que "¿tiene experiencia con CRMs?" lo encuentre?**

<details><summary>Ver respuesta</summary>

"Salesforce (CRM)": la herramienta y su categoría. Escribí el CV con las palabras que usaría quien pregunta.
</details>

---

[← Paso 0](../00-setup/README.es.md) · [Índice](../../README.es.md) · [Siguiente: Paso 2, chunking e ingesta →](../02-chunking-ingestion/README.es.md)
