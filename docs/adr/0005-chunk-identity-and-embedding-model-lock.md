# Deterministic chunk identity and an embedding-model lock

Ingestion is idempotent:

- **Chunk id:** derived from the file path, the heading path and the split index.
- **Content hash:** a chunk whose hash is unchanged is not re-embedded.
- **Orphans:** chunks from deleted files or sections are removed.

The store keeps the embedding model name and dimension in a `kb_meta` table. If they differ from the configured ones, ingestion fails loudly and tells the user to run `make ingest REBUILD=1`. It never migrates or mixes models silently, because vectors from different models are not comparable.

The ingestion itself creates the schema (`CREATE EXTENSION/TABLE IF NOT EXISTS`) rather than Docker init scripts, so it works against any Postgres that has pgvector.
