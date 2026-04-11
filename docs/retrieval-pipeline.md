# Retrieval Pipeline

This note describes the current retrieval pipeline in this repository.

It is intentionally short. It should stay aligned with the actual code and should be updated when the retrieval design changes in a meaningful way.

## Current Flow

1. PDFs are loaded and split into smaller retrieval units.
2. Prose is chunked using sentence-aware grouping.
3. Structured PDF content such as tables is chunked using smaller line-group logic with some local header/context retention.
4. Each chunk is embedded and stored in FAISS.
5. Chunk metadata is stored in SQLite.
6. Search retrieves candidate chunks from FAISS.
7. Retrieved candidates are reranked using simple heuristic signals.
8. Search output shows the matched chunk and larger paragraph context when available.

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
- FAISS-to-metadata mapping is still order-based and should be made more explicit later

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
python3 db_inspect.py page-chunks --path-contains esp32-wroom-32d_esp32-wroom-32u_datasheet_en.pdf --page 25
```
