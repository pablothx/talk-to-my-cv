# Before you start: the fundamentals

🇪🇸 [Leer en español](README.es.md)

This lesson has no code. It covers the ideas you need for everything else to make sense, explained one small piece at a time and from scratch. If you've never touched AI, start here. If you already know what an embedding is, you can skip to [step 0](../00-setup/README.md).

Time: about 30 minutes.

## What you'll learn

- What an LLM is, why it "hallucinates" and what makes one model smarter than another.
- What **RAG** is and what problem it solves.
- What **chunks**, **embeddings** and **cosine similarity** are, without hard formulas.
- How a RAG finds the right pieces, and why it needs a **gate**.

---

## Piece 1: an LLM knows nothing about you

An LLM (ChatGPT, Claude, the `qwen2.5:3b` we use here) learned by reading the internet. It knows a lot about the world, but **nothing about you**.

If you ask it "which companies has Valentina Ríos worked at?", one of two things happens:

- it says it doesn't know, or
- it **makes up** an answer that sounds perfect.

The second one is the dangerous one, because it doesn't warn you that it's making things up.

## Piece 2: hallucinating isn't lying

Making things up is called **hallucinating**. But careful: **hallucinating isn't lying**.

- **Lying** is saying something false *knowing* it's false.
- **Hallucinating** is saying something false *without knowing it*. The model has no intention to deceive.

Why does it happen? Because inside, an LLM does only one thing: **it predicts the most likely next word**, one after another.

If you ask where someone it doesn't know worked, it doesn't look anything up: it builds the answer that *sounds* most likely. "She worked at Globant as..." sounds perfect for an Argentine engineer, but it comes from statistics, not from a fact.

> **The danger:** a made-up answer sounds just as confident as a true one. No tone of voice tells them apart.

## Piece 3: what parameters are

Deep down, an LLM is a giant function. Think of a simple one:

```
y = a * x + b
```

`x` is the input and `y` the output. **`a` and `b` are the parameters**: the numbers that define how the function turns the input into the output.

An LLM is the same, but with **billions** of parameters, arranged in huge matrices:

- **Input:** your question, turned into numbers.
- **Output:** the probability of every possible word being the next one.
- **The parameters:** decide which word comes out as most likely.

Where do those numbers come from? **Training:**

1. They start random, and the model outputs garbage.
2. You give it real text ("The sky is...") and ask it to predict the next word.
3. If it said "pizza" and the answer was "blue", the numbers are nudged a little so "blue" becomes more likely.
4. Repeat that trillions of times, over the whole internet.

Nobody wrote those numbers by hand. When you run `ollama pull qwen2.5:3b` you download a file of about 2 GB: **that file is the parameters**. The model *is* that file.

## Piece 4: small models and big models

Every LLM works the same way inside: the same architecture (a *transformer*) and the same mechanism (predicting the next word). What changes is:

1. **Size.** The "3b" in `qwen2.5:3b` means 3 billion parameters. Big models have hundreds of billions.
2. **What it was trained on.** More and better text (books, code, languages) gives a model that knows more.
3. **How it was "taught" afterwards.** It's trained on examples of how to behave: follow instructions, say "I don't know", think step by step before answering.

It's like a child's brain and an adult's: the same neurons and mechanism, but the adult can reason about things the child can't. And some abilities **appear on their own** as models grow: nobody programmed a big model "how to reason".

| | Small model (`qwen2.5:3b`) | Big model |
|---|---|---|
| Follows "answer only with this" | Sometimes slips | Almost always |
| Hallucinates | More | Less (but not zero) |
| Runs on | Your CPU, for free | GPU servers, for a fee |
| Time per answer | 10 to 30 seconds on a CPU | Seconds |

This tutorial uses the small one because it runs on any computer and is free. Since it makes more mistakes, it forces us to build real safeguards. **If the system works with a small model, it works better with a big one.**

## Piece 5: RAG, an open-book exam

The fix for "the model doesn't know about you" is simple: **before asking the LLM, we search your documents for the pieces related to the question**, and pass them along with an instruction: *"answer only with this"*.

That technique is called **RAG** (*Retrieval-Augmented Generation*):

- **Retrieval:** find the pieces.
- **Augmented:** add them to the question.
- **Generation:** have the LLM write the answer.

It's like an open-book exam, with the right page already bookmarked.

## Piece 6: chunks

Before we can search, we cut the CV into pieces. Each piece is called a **chunk**. This tutorial's example CV (Valentina Ríos, a fictional person) becomes 19 chunks:

```
profile.md                       § Summary
profile.md                       § Languages
skills.md                        § Cloud
experience/northwind-payments.md § Senior Backend Engineer > Project Lumen
...
```

Why cut it instead of passing the whole CV?

1. **Precision.** A small piece is about one thing. A whole CV is about everything at once, and its "meaning" gets blurry.
2. **Citations.** If the answer came from "Project Lumen", the system can tell you *where* it got it.
3. **Scale.** A CV fits in a prompt, but 500 manuals don't. You have to choose.

Cutting **covers the whole document**: no line is left out. But careful: **storing everything isn't using everything**. For each question, the LLM only sees the 5 most similar chunks. If the answer is spread over 15 chunks (for example, "how many years has she worked in total?"), it may answer wrong. That's a built-in limitation of RAG.

## Piece 7: searching by meaning, not by words

How does the system know which chunks "are related" to the question? The obvious way is to search for words, like Ctrl+F.

- You ask: *"Has she worked with the cloud?"*
- The CV says: *"Designed architectures on AWS using Lambda"*.

"Cloud" doesn't appear in that sentence, so Ctrl+F **doesn't find it**. But anyone knows AWS *is* the cloud. And if you ask in Spanish while the CV is in English, almost no words match.

The fix is to search by **meaning**. For that, every text is turned into a list of numbers that represents what it means. That list is called an **embedding**.

## Piece 8: what an embedding is

An embedding is **a list of numbers** (also called a *vector*). To get the idea, a toy example: describe each text with **3 scores** from 0 to 1.

| Text | Tech? | Food? | Sports? | The vector |
|---|---:|---:|---:|---|
| "worked with AWS" | 0.9 | 0.0 | 0.1 | `[0.9, 0.0, 0.1]` |
| "used Amazon's cloud" | 0.8 | 0.1 | 0.0 | `[0.8, 0.1, 0.0]` |
| "empanada recipe" | 0.0 | 0.9 | 0.1 | `[0.0, 0.9, 0.1]` |

The first two lists **look alike** (high on tech), so they mean something similar. The third is different.

Real embeddings differ from the toy in two ways:

1. It's not 3 numbers: the model we use (`bge-m3`) gives **1024**.
2. **The numbers have no names.** No position means "tech": the model learned on its own what to measure in each slot.

So if you look at an embedding, you'll see `[-0.028, 0.012, -0.032, ...]` and understand nothing. **An embedding on its own means nothing; it's only useful to compare with another one.** It's like a GPS coordinate: `-34.6, -58.4` tells you nothing until you compare it with another.

## Piece 9: comparing two embeddings (cosine)

Picture each embedding as an **arrow** starting at the center:

```
          ↑  "worked with the cloud"
         ↗   "architectures on AWS"
        /
  ─────●──────────→  "empanada recipe"
```

"Cloud" and "AWS" point almost the same way; "empanada", another way. To compare them, we measure the angle between the arrows with **cosine similarity**:

| Cosine | Means |
|---|---|
| **1** | Same direction: same meaning |
| **0** | Perpendicular: unrelated |
| **-1** | Opposite (almost never happens with text) |

Why cosine and not sine? Because with cosine, **higher = more similar**. Sine gives 0 both for "identical" and for "opposite", so it can't tell them apart.

And it's easy to compute, without measuring any angle: multiply the two lists position by position, add it up, and divide by the length of each arrow. Just sums and products.

With 1024 numbers it's the same, we just can't draw it.

## Piece 10: two different models

This project has **two models**, and each does one job:

| Model | What it does | In | Out |
|---|---|---|---|
| `bge-m3` | Turns text into numbers | "worked with AWS" | 1024 numbers |
| `qwen2.5:3b` | Writes the answer | question + chunks | "Valentina worked with AWS at..." |

The first can't write; the second can't search. Both run in **Ollama**, a program that serves models on your machine.

We chose `bge-m3` because it's **multilingual**: it understands that "¿qué idiomas habla?" and "Languages: Spanish, English" mean the same thing. The clouds have others (on AWS, Amazon Titan or Cohere), and each gives a different number of values.

> **A golden rule:** the question and the chunks must go through **the same** embedding model. Each model has its own "language of numbers", and comparing vectors from two models is like comparing GPS coordinates with street addresses.

## Piece 11: the search

When you ask a question:

1. The question is turned into an embedding.
2. The cosine is computed against **every** stored chunk.
3. They're sorted from highest to lowest, and the **top 5** are kept.

This is real, against Valentina's CV:

```
How much did Project Lumen speed up reconciliation?
  0.65  experience/northwind-payments.md § Senior Backend Engineer > Project Lumen   ← ✓
  0.33  experience/northwind-payments.md § Senior Backend Engineer
  0.32  experience/brightcart.md § Backend Developer > Hackathon
  0.30  experience/brightcart.md § Backend Developer > Database work
  0.27  profile.md § Summary

¿Sabe cocinar empanadas?  (Can she cook empanadas?)
  0.39  skills.md § Languages
  0.38  profile.md § Languages
  0.37  skills.md § Cloud
  0.34  skills.md § Data and messaging
  0.33  profile.md § Summary
```

Three things to notice:

1. **It works:** for Project Lumen, the right chunk comes first, far ahead of the rest.
2. **The numbers are low.** Don't expect 0.9: between a short question and a piece of CV, 0.6 is already "very related".
3. **The search always returns 5, even if they're unrelated.** The CV says nothing about empanadas and it still returned 5 chunks. The search can't say "there's nothing": it can only say "this is the *least far*".

## Piece 12: the gate

Point 3 is a problem: if those 5 "empanada" chunks reach the LLM, it may make something up. That's why there's a **gate** (the *relevance threshold*):

> If the most similar chunk doesn't reach **0.42**, the system answers "I don't have that information" **without calling the LLM**.

For empanadas, the best one scores 0.39: refused. For Project Lumen, 0.65: it passes.

The gate is a **trade-off**:

- Raise it, and it refuses more junk, but also more good questions.
- Lower it, and it answers more, but lets more junk through.

**There's no perfect number: you measure it with real questions.** We do that in step 5. And 0.42 was calibrated for the example CV: your CV may need a different value.

## The map of what's ahead

```
INGESTION (once)
  your CV ──► cut into chunks ──► embeddings (bge-m3) ──► Postgres
                  step 2               step 1               step 2

EVERY QUESTION
  question ──► embedding ──► top 5 ──► gate ──► LLM (qwen) ──► answer + citations
                 step 1      step 2   step 4     step 3           step 4

  + measure everything (step 5) · also search by words (step 6)
  + verify the answer (step 7) · a web page (step 8)
```

---

## FAQ

<details>
<summary><b>If I load the Bible and ask about "the prophet Mark", but my Bible doesn't have that book, what does it answer?</b></summary>

It depends on three filters, in order:

1. **The search always returns something:** the 5 pieces most similar to "prophet Mark", probably about other prophets.
2. **The gate:** the Bible talks a lot about prophets, so it will most likely pass.
3. **The LLM with "answer only with this":** here's the risk. A big model *knows* the Bible by heart. It may behave ("the text doesn't mention a prophet Mark"; it may even correct you that Mark was an evangelist, not a prophet) or **leak what it knows** and tell you about the Gospel of Mark as if it came from your text. A small model does that much more.

That's why step 7 exists: before writing the answer, the code checks that the names the question asks about ("Mark") appear literally in the retrieved pieces. If they don't, it refuses. And an extra trap: "Mark" does appear in Acts ("John Mark"). If that piece comes back, the name is there, and the answer will be about *that* Mark.

A bigger model hallucinates less, but not zero. That's why the system doesn't trust the model: it runs checks in code (the gate and verification) before letting it write.
</details>

<details>
<summary><b>If AI someday knew everything about everyone, would RAG become obsolete?</b></summary>

Partly. Some things no model can know from its training:

1. **Private data:** your CV or your company's contracts will never be in the training data, and you don't want them there.
2. **Changing data:** retraining a model costs millions; updating a row in Postgres, a second.
3. **Citations:** at a bank or a hospital, "I know" isn't enough; you need "this document says so". A model can't point to where it learned something.
4. **Permissions:** with RAG you filter which documents each user sees. What a model learned, it knows for everyone.
5. **Forgetting:** deleting data from RAG is deleting a row. You can't "peel" a fact out of a trained model.

What is changing: new models read a lot of text at once, and a 2-page CV already fits whole in the prompt. For small documents, cutting and searching matter less. For large volumes, they still matter. The core idea (give the model the right data at question time, and be able to check where the answer came from) doesn't go away.
</details>

<details>
<summary><b>Are embeddings always 1024 numbers?</b></summary>

No, it depends on the model. `bge-m3` gives 1024; Amazon Titan Text Embeddings V2 gives 1024 by default (or 256 and 512 if you ask); OpenAI's `text-embedding-3-small` gives 1536. If you switch models, you have to embed everything again. Step 2 shows how the project stops you if you forget.
</details>

---

## ✋ Review

**1. Why can an LLM say something false with total confidence?**

<details><summary>Show answer</summary>

Because it doesn't look facts up: it predicts the most likely next word. A made-up answer can be very "likely" and sound perfect. It isn't lying (it doesn't know it's false): it's hallucinating.
</details>

**2. What are you downloading when you run `ollama pull qwen2.5:3b`?**

<details><summary>Show answer</summary>

The parameters: about 3 billion numbers that came out of training. The model *is* that file.
</details>

**3. What does each number in an embedding mean?**

<details><summary>Show answer</summary>

Nothing, on its own. The meaning is spread across all the numbers, in a way nobody designed. An embedding is only useful to compare with another one.
</details>

**4. You ask about something the CV doesn't mention. How many chunks does the search return?**

<details><summary>Show answer</summary>

Five. The search always returns the 5 most similar, even if they're unrelated. That's why the gate exists.
</details>

**5. What happens if you embed the question with one model and the chunks with another?**

<details><summary>Show answer</summary>

Searches return junk with no visible error: each model has its own "language of numbers" and the vectors aren't comparable.
</details>

**6. If you raise the threshold from 0.42 to 0.55, what do you gain and what do you lose?**

<details><summary>Show answer</summary>

You gain: it refuses more questions that have no answer. You lose: it also refuses questions that did have an answer but scored between 0.42 and 0.55. There's no perfect number: you measure it (step 5).
</details>

---

[Index](../../README.md) · [Next: Step 0, setup →](../00-setup/README.md)
