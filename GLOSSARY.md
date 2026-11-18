# talk-to-my-cv

A chat that answers questions about one person's professional experience, using only that person's own documents.

## Language

**Knowledge base (KB)**:
The set of Markdown documents about the person that the chat may answer from.
_Avoid_: corpus, dataset, docs

**Persona**:
The person the knowledge base describes and the chat talks about, always in the third person.
_Avoid_: user, owner, candidate

**Chunk**:
A unit of a KB document that is retrieved and cited.
_Avoid_: passage, fragment, document

**Section path**:
The chain of headings that locates a chunk inside its file. Together with the file name, it forms the citation.
_Avoid_: breadcrumb, anchor

**Relevance gate**:
The check that decides whether any retrieved chunk is related enough for the chat to answer at all.
_Avoid_: filter, guardrail

**Named term**:
A specific name a question asks about (a technology, company, project, certification). If the retrieved chunks never mention it, the chat refuses.
_Avoid_: keyword, entity

**Refusal**:
The fixed reply given when the relevance gate fails or the question is off-topic.
_Avoid_: fallback, error, "I don't know"

**Planted fact**:
A fact that exists only in the KB and is unguessable from general knowledge. It proves that an answer came from the documents.
_Avoid_: canary, trap

**Step**:
One lesson of the tutorial, with its own check and a frozen tag.
_Avoid_: chapter, module, part
