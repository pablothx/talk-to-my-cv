# Step 1: Embeddings

🇪🇸 [Leer en español](README.es.md)

Every RAG starts here: turning text into numbers that can be compared. You saw the idea in the [fundamentals](../fundamentals/README.md); now you get your hands on it.

## What you'll learn

- What an embedding is and why it lets you search by meaning.
- How two embeddings are compared (cosine similarity), in code.
- What an embedding captures and, above all, **what it doesn't**.

---

## Piece 1 of 8: your first embedding

```bash
make embed TEXT="hola"
```

```
model: bge-m3
dimension: 1024
first values: [+0.0094, +0.0229, -0.0431, +0.0009, -0.0314, ...]
```

That's an embedding: **1024 numbers** that represent the meaning of "hola". None of them means anything on its own; they're useful to compare with another text's.

## Piece 2 of 8: comparing them

```bash
make similarity A="Trabajé con AWS" B="I worked with AWS"
```

It gives **0.95**: almost the same, even though they're in different languages. That's what we want: **same meaning, similar numbers**.

The number is the **cosine similarity**: 1 is "same meaning", 0 is "unrelated".

## Piece 3 of 8: cosine, in code

It's in `src/talk_to_my_cv/embeddings.py`, and it's a few lines:

```python
def cosine_similarity(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        raise ValueError(f"vectors differ in dimension: {len(a)} vs {len(b)}")
    norms = math.hypot(*a) * math.hypot(*b)
    if norms == 0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return sum(x * y for x, y in zip(a, b, strict=True)) / norms
```

Read it like this:

- **The last line is the math:** multiply position by position, add it up (the *dot product*) and divide by the length of both arrows (`hypot`). Dividing makes only the **direction** matter, not the size.
- **The two checks** prevent silent errors: comparing vectors of different sizes, or dividing by zero.

## Piece 4 of 8: why `bge-m3`

It's **multilingual**: a question in Spanish finds a text in English. That's why the example CV is in English and the eval questions mix both languages.

It's also free, runs on a CPU and returns 1024-number vectors. It isn't "the best in the world": the clouds' paid models tend to be a bit better, but for a CV the difference is hard to notice.

## Piece 5 of 8: the `Embedder`, and why our own interface

The code doesn't call Ollama directly. It calls an **interface** of ours:

```python
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
```

`OllamaEmbedder` implements it. Why not use LangChain from the start? Because we want to see and control every piece, and because with our own interface, moving to another provider (Bedrock on AWS, for example) means writing one more small class ([ADR-0003](../../docs/adr/0003-own-seams-no-langchain-before-step-7.md)). LangChain only comes in at step 7, when there's a real problem that justifies it.

## Piece 6 of 8: two details of `OllamaEmbedder` that matter

**1. It sends texts in batches and returns the vectors in the same order.** It looks like a detail, but if the order broke, in step 2 every piece of the CV would be stored with another piece's embedding, and **nothing would warn you**: searches would return junk as if all were normal.

**2. It checks the dimension** against `config/models.yaml`. If someone changes models without noticing, it fails loudly instead of mixing incomparable vectors.

The unit tests use a fake Ollama client. The e2e tests talk to the real `bge-m3`.

## Piece 7 of 8: what an embedding does NOT capture

These are our results with `make similarity`:

| A | B | Score |
|---|---|------:|
| Trabajé con AWS | I worked with AWS *(translation)* | 0.95 |
| Trabajé con AWS | Trabajé con Azure *(something else)* | 0.83 |
| Trabajé con AWS | Usé Amazon Web Services en mi trabajo *(synonym)* | 0.79 |
| Trabajé con AWS | Nunca trabajé con AWS *(negation)* | **0.75** |
| Trabajé con AWS | Me gusta cocinar pasta los domingos *(unrelated)* | 0.45 |

Three things to notice:

1. **Negation barely moves the score.** "I worked with AWS" and "I never worked with AWS" say the opposite and score 0.75. An embedding captures **what a text is about**, not **what it claims**. Search only brings candidates; the LLM reads them and decides (step 3).
2. **"Azure" scores higher than the synonym.** It shares almost every word and the topic. If someone asks "has she worked with Azure?", search will bring the AWS piece.
3. **"Unrelated" doesn't score 0, it scores 0.45.** Each model has its own score range. That's why step 4's threshold is set **per model** and calibrated with data in step 5.

## Piece 8 of 8: two traps we'll chase through the whole tutorial

They came from testing with a real CV:

| A | B | Score | Risk |
|---|---|------:|------|
| Salesforce | CRM | 0.58 | **False refusal**: the tool and its category end up far apart. |
| Java | JavaScript | 0.84 | **False positive**: similar names, different technologies. |

- **Salesforce vs CRM.** If your CV says "Salesforce" and someone asks "does he have CRM experience?", the chat may refuse something it knows. The fix is in how you write the CV: name the tool **and its category** ("Salesforce (CRM)").
- **Java vs JavaScript.** For the embedding they're almost the same. We pick it up in step 6 (exact-word search) and solve it in step 7.

---

## Check that it works

```bash
make check-01
```

It includes three tests against the real model: that it returns 1024 dimensions, that a paraphrase scores higher than an unrelated sentence, and that a Spanish sentence and its English translation do too.

## Play with it

Use `make similarity A="..." B="..."` with your own sentences:

- two similar technologies (Postgres vs MySQL);
- two different dates ("in 2019" vs "in 2023");
- your name against another name;
- a sentence and its negation.

Write the numbers down. What does the embedding capture, and what doesn't it?

---

## FAQ

<details>
<summary><b>Which embedding model is used on AWS?</b></summary>

On Amazon Bedrock, the most common are **Amazon Titan Text Embeddings V2** (1024 numbers by default, or 256 and 512) and **Cohere Embed Multilingual**. They work the same way: you send text and get numbers back. With our `Embedder` interface, it would be one new class. See the [production guide](../../docs/production-on-aws.md).
</details>

<details>
<summary><b>Why cosine and not sine?</b></summary>

With cosine, higher = more similar: 1 is "same direction" and 0 "unrelated". Sine gives 0 both for identical and for opposite arrows, so it can't tell them apart. Also, cosine is computed without measuring any angle: just products and sums.
</details>

---

## ✋ Review

**1. 🧪 Try it:** before running it, how much do you think `make similarity A="Java" B="JavaScript"` gives?

<details><summary>Show answer</summary>

Around 0.84: for the embedding they're almost the same. It's one of the traps the tutorial chases until step 7.
</details>

**2. "Trabajé con AWS" vs "Nunca trabajé con AWS" gives 0.75. What does that tell you?**

<details><summary>Show answer</summary>

That an embedding captures what a text is about, not what it claims. Search brings candidates by topic; the LLM has to read them and understand the negation.
</details>

**3. What would happen if `OllamaEmbedder` returned the vectors out of order?**

<details><summary>Show answer</summary>

Every chunk would be stored with another one's embedding, and searches would return the wrong chunks with no error. That's why there are tests that check the order.
</details>

**4. An unrelated sentence scores 0.45, not 0. Why does that matter?**

<details><summary>Show answer</summary>

Because each model has its own score range. A threshold picked "by eye" (say 0.5) may make no sense. That's why the threshold is per model and calibrated with data.
</details>

**5. Your CV says "Salesforce". How would you write it so that "does he have CRM experience?" finds it?**

<details><summary>Show answer</summary>

"Salesforce (CRM)": the tool and its category. Write the CV with the words the person asking would use.
</details>

---

[← Step 0](../00-setup/README.md) · [Index](../../README.md) · [Next: Step 2, chunking and ingestion →](../02-chunking-ingestion/README.md)
