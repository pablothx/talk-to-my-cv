# Step 1: Embeddings

🇪🇸 [Leer en español](README.es.md)

## What you'll learn

- What an embedding is, and why it lets you search by meaning.
- How two embeddings are compared (cosine similarity).
- What an embedding captures and, above all, **what it doesn't**.

## The concept

An **embedding** is a list of numbers (a vector) that represents the meaning of a text. `bge-m3` turns any text into 1024 numbers, and texts with similar meanings end up close together in that 1024-dimensional space.

To measure how close two vectors are, we use **cosine similarity**: the cosine of the angle between them. It is 1 when they point the same way and 0 when they have nothing to do with each other.

Every RAG starts here. In step 2 we embed each piece of the CV; in step 3, the question. Searching means finding the pieces with the highest cosine similarity to the question.

We chose `bge-m3` because it is **multilingual**: a question in Spanish finds a text in English. That's why the example KB is in English and the eval mixes both languages.

## The code

Everything lives in `src/talk_to_my_cv/embeddings.py`:

```python
def cosine_similarity(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        raise ValueError(f"vectors differ in dimension: {len(a)} vs {len(b)}")
    norms = math.hypot(*a) * math.hypot(*b)
    if norms == 0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return sum(x * y for x, y in zip(a, b, strict=True)) / norms
```

`OllamaEmbedder` implements the `Embedder` interface ([ADR-0003](../../docs/adr/0003-own-seams-no-langchain-before-step-7.md)). Besides calling Ollama, it does two things:

- **It sends texts in batches** (`batch_size`) and returns the vectors **in the same order**. It looks like a detail, but if the order broke, in step 2 every piece of the CV would be stored with someone else's embedding, and nothing would warn you.
- **It checks the dimension** against `config/models.yaml`. If someone switches models without noticing, it fails loudly instead of mixing vectors that can't be compared.

Unit tests use a fake Ollama client. The e2e tests talk to the real `bge-m3`.

## Check that it works

```bash
make check-01
make embed TEXT="hello"
```

```
model: bge-m3
dimension: 1024
first values: [+0.0094, +0.0229, -0.0431, +0.0009, -0.0314, ...]
```

`make check-01` includes three tests against the real model: it returns 1024 dimensions, a paraphrase scores higher than an unrelated sentence, and so does a Spanish sentence paired with its English translation.

## Play with it

Use `make similarity A="..." B="..."` and write down your results. These are ours, with `bge-m3`:

| A | B | Score |
|---|---|------:|
| Trabajé con AWS | I worked with AWS *(translation)* | 0.95 |
| Trabajé con AWS | Trabajé con Azure *(something else)* | 0.83 |
| Trabajé con AWS | Usé Amazon Web Services en mi trabajo *(synonym)* | 0.79 |
| Trabajé con AWS | Nunca trabajé con AWS *(negation)* | **0.75** |
| Trabajé con AWS | Me gusta cocinar pasta los domingos *(unrelated)* | 0.45 |

The Spanish sentences mean "I worked with AWS", "I worked with Azure", "I used Amazon Web Services at work", "I never worked with AWS" and "I like cooking pasta on Sundays".

Three things to notice:

1. **Negation barely moves the score.** "I worked with AWS" and "I never worked with AWS" say opposite things, yet they score 0.75, almost the same as the synonym. An embedding captures **what a text is about**, not **what it claims**. That's why search only fetches candidates; it's the LLM that reads them and decides what they say (step 3).
2. **"Azure" scores higher than the synonym.** It shares almost every word and the topic (the cloud), even though the key fact differs. If someone asks "did she work with Azure?", search will bring back the AWS chunk. Again: the LLM decides.
3. **"Unrelated" doesn't score 0, it scores 0.45.** Each model's scores live in their own compressed range. That's why the relevance threshold in step 4 is set **per model** and calibrated with data in step 5, not by eye.

Two more cases, from testing with a real CV:

| A | B | Score | Risk |
|---|---|------:|------|
| Salesforce | CRM | 0.58 | **False refusal**: the tool and its category end up far apart. |
| Java | JavaScript | 0.84 | **False positive**: similar names, different technologies. |

4. **Salesforce vs CRM.** If your KB says "Salesforce" and someone asks "does she have CRM experience?", the chunk may fall below the threshold, and the chat will refuse something it actually knows. The fix is in how you write the KB: name the tool **and its category** ("Salesforce (CRM)").
5. **Java vs JavaScript.** To the embedding, they're nearly the same. A question about Java can bring back the JavaScript chunk with a high score. We come back to this in step 6: exact-word search (BM25) tells "Java" from "JavaScript" apart, and hybrid search combines the best of both.

Try your own sentences: two similar technologies (Postgres vs MySQL), two different dates, your name against someone else's.
