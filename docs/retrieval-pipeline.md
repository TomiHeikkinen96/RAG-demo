# Retrieval Pipeline

This note describes the current retrieval pipeline in this repository.

It is intentionally short. It should stay aligned with the actual code and should be updated when the retrieval design changes in a meaningful way.

## Current Flow

1. PDFs are loaded and split into smaller retrieval units.
2. Prose is chunked using sentence-aware grouping.
3. Structured PDF content such as tables is chunked using smaller line-group logic with some local header/context retention.
4. Chunk metadata is stored in SQLite.
5. Normal ingest runs update the active FAISS index incrementally and record explicit vector-to-chunk mappings in SQLite.
6. Search retrieves candidate vector ids from FAISS.
7. Search resolves those vector ids back to chunk metadata through `indexed_chunks`.
8. Retrieved candidates are reranked using simple heuristic signals.
9. Search output shows the matched chunk and larger paragraph context when available.

## Retrieval Unit vs Display Context

There are two important text units in the current design:

- `chunk_text`
- `paragraph_text`

`chunk_text` is the retrieval unit.
It is the text that is embedded, indexed, searched, and reranked.

`paragraph_text` is display/context text.
It is stored so search can show a larger surrounding block after retrieval.

This separation is intentional:

- smaller chunks improve retrieval precision
- larger paragraph context improves readability and can be useful for downstream agent/LLM use

The current design treats retrieval precision and context expansion as separate steps.

## Index Identity And Inspectability

The repository no longer relies on FAISS row order matching a repeated SQLite sort.

Instead, the active index stores explicit retrieval metadata:

- `indexes`
- `indexed_chunks`

`indexes` records the active index metadata such as embedding model, update time, and chunk count.

`indexed_chunks` maps each FAISS `vector_id` to a durable `chunk_id`.

This makes the retrieval linkage explicit:

- FAISS returns `vector_id`
- SQLite resolves `vector_id -> chunk_id -> chunk metadata`

This design is easier to inspect and less fragile than relying on implicit row ordering across systems.

## Incremental Update Behavior

By default, ingestion now mutates the active index in place:

- deleted files remove their existing vectors
- changed files remove their old vectors and add newly embedded replacements
- new files add only their new vectors

`--force-rebuild` still exists as the clean rebuild path.
That mode clears storage and rebuilds the active index from scratch.

## File Deletion Handling

Ingestion now detects PDFs that were removed from `data/`.

When a tracked file disappears:

- its chunks are deleted from SQLite
- its file-tracking record is marked as no longer present
- the active FAISS index removes its vectors automatically

The current design prefers deletion over soft-deactivation so the demo database stays small and easy to reason about while retrieval behavior is still being evaluated.

## Current Reranking

FAISS returns a candidate set using semantic similarity over chunk embeddings.

The current reranker then applies:

- semantic score from FAISS
- lexical overlap over `chunk_text`
- a small penalty for low-value chunk content such as revision-history or contents-like material
- paragraph-level deduplication so repeated hits from the same paragraph do not dominate the result list

Current formula:

```text
rerank_score = semantic_score + (LEXICAL_WEIGHT * lexical_score) - penalty
```

Important limitation:
this is a heuristic reranker, not a learned reranker or cross-encoder.

## Score Meanings

- `Semantic Score`
  Raw embedding similarity from FAISS over the chunk vector.

- `Lexical Score`
  Exact token overlap between the query and the matched `chunk_text`.

- `Penalty`
  Hand-written downweight for low-value chunk content.

- `Final Score` / `Rerank Score`
  The final ordering score after heuristic reranking.

## Current Tradeoffs

What is working better now:

- chunk-level retrieval is more precise than paragraph-level retrieval
- heuristic reranking helps strong literal matches rise
- display-time paragraph expansion keeps results easier to read
- standardized benchmarking is now possible with `benchmark_search.py`

What is still weak:

- table-heavy PDF content is still noisy
- weak semantic matches can still survive in lower-ranked results
- result presentation for table-derived chunks is still rough

## Practical Commands

Interactive or multi-query search:

```bash
python3 search_index.py
python3 search_index.py "maximum current" "ADC pins"
```

Batch benchmarking:

```bash
python3 benchmark_search.py
python3 benchmark_search.py --file benchmark_queries.txt
```

Database inspection:

```bash
python3 db_inspect.py stats
python3 db_inspect.py index-status
python3 db_inspect.py page-chunks --path-contains esp32-wroom-32d_esp32-wroom-32u_datasheet_en.pdf --page 25
```
