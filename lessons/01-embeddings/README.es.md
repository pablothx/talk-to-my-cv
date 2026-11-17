# Paso 1: Embeddings

🇬🇧 [Read in English](README.md)

## Qué vas a aprender

- Qué es un embedding y por qué sirve para buscar por significado.
- Cómo se comparan dos embeddings (similitud coseno).
- Qué captura un embedding y, sobre todo, **qué no captura**.

## El concepto

Un **embedding** es una lista de números (un vector) que representa el significado de un texto. `bge-m3` convierte cualquier texto en 1024 números. Textos con significado parecido quedan cerca en ese espacio de 1024 dimensiones.

Para medir qué tan cerca están dos vectores usamos la **similitud coseno**: el coseno del ángulo entre ellos. Da 1 si apuntan en la misma dirección y 0 si no tienen nada que ver.

Todo RAG empieza acá. En el paso 2 vamos a embeber cada pedazo del CV; en el paso 3, la pregunta. Buscar es encontrar los pedazos con mayor similitud coseno a la pregunta.

Elegimos `bge-m3` porque es **multilingüe**: una pregunta en español encuentra un texto en inglés. Por eso la base de ejemplo está en inglés y la evaluación mezcla los dos idiomas.

## El código

Todo está en `src/talk_to_my_cv/embeddings.py`:

```python
def cosine_similarity(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        raise ValueError(f"vectors differ in dimension: {len(a)} vs {len(b)}")
    norms = math.hypot(*a) * math.hypot(*b)
    if norms == 0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return sum(x * y for x, y in zip(a, b, strict=True)) / norms
```

`OllamaEmbedder` implementa la interfaz `Embedder` ([ADR-0003](../../docs/adr/0003-own-seams-no-langchain-before-step-7.md)) y hace dos cosas además de llamar a Ollama:

- **Manda los textos en tandas** (`batch_size`) y devuelve los vectores **en el mismo orden**. Parece un detalle, pero si el orden se rompe, en el paso 2 cada pedazo del CV quedaría guardado con el embedding de otro, y nada avisaría.
- **Verifica la dimensión** contra `config/models.yaml`. Si alguien cambia de modelo sin darse cuenta, falla fuerte en vez de mezclar vectores incomparables.

Los tests unitarios usan un cliente de Ollama falso. Los tests e2e hablan con el `bge-m3` real.

## Cómo comprobar que anda

```bash
make check-01
make embed TEXT="hola"
```

```
model: bge-m3
dimension: 1024
first values: [+0.0094, +0.0229, -0.0431, +0.0009, -0.0314, ...]
```

`make check-01` incluye tres tests contra el modelo real: que devuelve 1024 dimensiones, que una paráfrasis puntúa más alto que una oración sin relación, y que una oración en español y su traducción al inglés también.

## Para jugar

Usá `make similarity A="..." B="..."` y anotá tus resultados. Estos son los nuestros, con `bge-m3`:

| A | B | Score |
|---|---|------:|
| Trabajé con AWS | I worked with AWS *(traducción)* | 0.95 |
| Trabajé con AWS | Trabajé con Azure *(otra cosa)* | 0.83 |
| Trabajé con AWS | Usé Amazon Web Services en mi trabajo *(sinónimo)* | 0.79 |
| Trabajé con AWS | Nunca trabajé con AWS *(negación)* | **0.75** |
| Trabajé con AWS | Me gusta cocinar pasta los domingos *(sin relación)* | 0.45 |

Tres cosas para mirar:

1. **La negación casi no mueve el score.** "Trabajé con AWS" y "Nunca trabajé con AWS" dicen lo contrario, pero dan 0.75, casi lo mismo que el sinónimo. Un embedding captura **de qué habla** un texto, no **qué afirma**. Por eso la búsqueda solo trae candidatos; quien lee y decide qué dicen es el LLM (paso 3).
2. **"Azure" puntúa más que el sinónimo.** Comparte casi todas las palabras y el tema (la nube), aunque el dato clave sea distinto. Si alguien pregunta "¿trabajó con Azure?", la búsqueda va a traer el pedazo sobre AWS. De nuevo: decide el LLM.
3. **"Sin relación" no da 0, da 0.45.** Los scores de un modelo viven en un rango comprimido y propio. Por eso el umbral de relevancia del paso 4 se configura **por modelo** y se calibra con datos en el paso 5, no a ojo.

Probá con tus propias oraciones: dos tecnologías parecidas (Postgres vs MySQL), dos fechas distintas, tu nombre contra otro nombre.
