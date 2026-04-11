# Todo

This file is the living work log for the repository.

It should track:

- what has already been done
- what was learned from the work
- what still needs to be done
- which follow-up recommendations are worth testing

Agents should update this file when priorities become clearer, when work is completed, or when investigation changes the recommended next step.

## Search Quality

- [x] Move indexing away from paragraph-sized chunks.
  Notes:
  Sentence-oriented chunking has now been implemented for prose, and smaller line-group chunking has been added for structured PDF content such as tables.

- [x] Return the whole paragraph as retrieval context.
  Notes:
  Search ranking is now based on `chunk_text`, while the user-facing result display prefers `paragraph_text` when available.
  Reasoning:
  This keeps retrieval focused on a smaller, more precise unit while still allowing larger context to be shown or passed downstream when needed.

- [x] Review whether chunking is actually being applied.
  Findings:
  After rebuilding the index, the system now stores `14,429` chunks derived from `834` source paragraphs.
  Average chunk length is about `97` characters, while average paragraph length is about `1,775` characters.
  This confirms that indexing is now happening on smaller units than the displayed paragraph context.

- [x] Add a first-pass boilerplate filter before indexing.
  Notes:
  Chunk preparation now strips several repeated PDF furniture lines such as `Not Recommended For New Designs (NRND)`, `GoBack`, `Contents`, and similar repeated headings before chunk generation.
  Remaining concern:
  The current filter is heuristic-based and will likely need refinement after more query testing.

- [x] Add a first-pass low-information chunk filter.
  Notes:
  Chunk generation now rejects very short, weak, or obviously low-information chunks, including common header-only fragments.
  Remaining concern:
  The current heuristics are conservative and may still allow some weak table fragments through or accidentally remove some useful edge cases.

- [x] Add a first-pass table-aware chunking improvement.
  Notes:
  Structured blocks now try to carry table context and header context into each emitted row-group chunk instead of indexing isolated table shards without semantic anchors.
  Remaining concern:
  This is still layout-agnostic text processing, not true table extraction.

- [ ] Rebuild the index and review the impact of the new filtering heuristics.
  Why:
  The new boilerplate filtering, low-information filtering, and table-aware chunk changes need to be tested against real queries.
  Recommendation:
  Re-run ingestion from scratch, inspect chunk samples with `inspect_db.py`, and compare search quality for known test queries such as `maximum current`.

- [x] Add paragraph-level deduplication and first-pass lexical reranking in search.
  Notes:
  Search now avoids showing multiple hits from the same paragraph and applies a lightweight lexical overlap boost so exact query terms matter more alongside semantic similarity.
  Why:
  This directly addresses repeated false positives such as multiple `APB_SARADC_MAX_MEAS_NUM` hits for the same paragraph when querying `maximum current`.
  Remaining concern:
  The reranker is intentionally simple and heuristic-based. It improves obvious cases but is not yet a full hybrid retrieval system.

- [x] Add a first-pass low-value section penalty in reranking.
  Notes:
  Search now penalizes obvious low-value sections such as revision history, contents-like pages, and similar material that tends to match shared terms without being useful technical context.
  Why:
  This is intended to push genuinely relevant technical references above administrative or navigational pages.
  Remaining concern:
  The current penalty list is short and heuristic-based, so it should be refined only after testing with more real queries.

- [x] Keep reranking chunk-only for conceptual clarity.
  Notes:
  Lexical overlap and low-value penalties now operate on `chunk_text` only.
  `paragraph_text` remains display-only context.
  Why:
  This keeps retrieval, reranking, and explanation aligned to the same unit instead of giving a chunk lexical credit for words that only appear in surrounding context.

- [ ] Improve weak-match suppression in the heuristic reranker.
  Why:
  The current reranker is good at promoting strong matches, but weaker semantic hits can still survive in the lower results.
  Recommendation:
  Test small, explicit heuristics such as:
  requiring at least one meaningful chunk-token overlap for full rerank eligibility,
  applying a mild penalty when semantic similarity is moderate but lexical overlap is zero,
  or expanding the low-value section penalties carefully.

- [ ] Make table handling a priority across chunking and presentation.
  Why:
  Tables are currently the noisiest source format in the corpus.
  Full paragraph reconstruction is useful for prose, but for tables it often expands a small useful hit back into a huge noisy block.
  Recommendation:
  Treat this as a focused workstream:
  improve table-aware chunk assembly,
  keep table title/header context attached to row groups,
  and show matched chunk plus compact table context instead of always expanding to the full paragraph.

- [ ] Select and compare a better embedding model after chunk filtering improves.
  Why:
  Current scores for queries such as `maximum current` are still modest, but chunk noise is still a confounding factor.
  Recommendation:
  Do not change the embedding model first. Clean the chunks first, then compare embedding models in a controlled way.

- [ ] Consider BM25 or hybrid retrieval.
  Why:
  Some engineering queries are driven strongly by exact terminology, while others benefit more from semantic similarity.
  Recommendation:
  Evaluate whether BM25 alone, or a hybrid of BM25 and vector retrieval, improves recall and weak-match suppression for technical queries.

- [ ] Test retrieval quality with repeatable queries and simple metrics.
  Why:
  Score expectations such as `0.7 or higher` are useful as a rough intuition, but they are not yet a reliable evaluation method for this dataset.
  Recommendation:
  Create a small benchmark query set with expected relevant pages or chunks, and compare top-k relevance before and after changes.

- [x] Add a standardized batch benchmark runner.
  Notes:
  `benchmark_search.py` can now run a list of queries from command-line arguments or a text file so retrieval quality can be checked repeatedly with one command.
  Recommendation:
  Add and maintain a small `benchmark_queries.txt` file with representative engineering queries.

- [ ] Fix fragile FAISS-to-metadata linking.
  Why:
  Search still relies on implicit row ordering between FAISS rows and SQLite chunk IDs.
  Recommendation:
  Replace order-based mapping with an explicit, durable mapping between indexed vectors and chunk metadata.

- [ ] Add better support for tables and images in PDFs.
  Why:
  The corpus contains information that is partly encoded in structured tables and non-paragraph layouts.
  Recommendation:
  Explore table extraction or layout-aware parsing before trying to support images.

## Debuggability And Tooling

- [x] Create `AGENTS.md`.
  Notes:
  The repo now has an `AGENTS.md` file that describes the project intent, coding priorities, and how agents should use `todo.md`.

- [x] Add non-interactive multi-query support to `search_index.py`.
  Notes:
  Search can now run from command-line arguments for quicker iterative testing, while still falling back to interactive input when no query arguments are provided.
  Example:
  `python3 search_index.py "maximum current" "ADC pins"`

- [x] Add a reusable SQLite inspection tool for agents and local debugging.
  Notes:
  A root-level script should exist for inspecting chunk stats and samples without relying on very long inline shell commands.

- [x] Standardize the most useful inspection workflows.
  Notes:
  The database inspection script now provides reusable commands for overall stats, per-document counts, largest chunk-to-paragraph expansions, page-specific chunk previews, and custom read-only SQL.

- [ ] Decide how much free-form SQL access the inspection tool should allow.
  Tradeoff:
  Fully custom SQL is flexible for debugging, but predefined reports are easier to use and less error-prone.
  Recommendation:
  Keep both:
  provide a few stable subcommands for common inspections, and keep an escape hatch for custom SQL queries with explicit parameters.

## Notes From Recent Investigation

- The third input PDF reported `Created 0 chunks`, and that is consistent with the final database contents.
  Only the two main ESP32 PDFs contributed rows to the index.

- The current retrieval weakness is no longer just "paragraphs are too large."
  The main remaining issue is that PDF extraction still produces noisy boilerplate, table headers, and fragmented low-information chunks.

- The next high-value implementation step is chunk filtering and better table-aware chunk assembly, not immediate embedding-model replacement.
