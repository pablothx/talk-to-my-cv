# Own Embedder/ChatModel seams; no LangChain before step 7

Steps 1–6 talk to models through two small interfaces of our own, `Embedder.embed(texts) -> list[vector]` and `ChatModel.complete(messages) -> str`, implemented with the providers' official clients. We avoid LangChain abstractions until LangGraph is introduced in step 7, so the tutorial shows the RAG mechanics plainly and the unit tests can swap in fakes. In step 7, LangGraph orchestrates these same functions; it does not replace them.
