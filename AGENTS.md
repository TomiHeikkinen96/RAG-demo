# AGENTS.md

This is the instruction file future coding agents should read first in this repository.

## Project Idea

This project is a local RAG ingestion and retrieval demo focused on embedded software work, using ESP32 documentation as the current source corpus.

The point of the repo is not just to "make search work." The repo exists to evaluate whether better hardware-grounded context leads to better AI-assisted engineering outcomes: better answers, fewer hallucinations, and more useful embedded-development support.

That means changes should favor:

- repeatability
- inspectability
- simple local workflows
- clear experimental tradeoffs
- architecture that is easy to reason about and modify

## Current Architecture

Keep the current module boundaries explicit and understandable:

- `ingest.py` orchestrates discovery, change detection, chunking, embedding, SQLite updates, and FAISS rebuilds
- `search_index.py` performs local query embedding, FAISS lookup, and result rendering
- `chunkers/` owns chunking logic
- `processing/` owns document loading and embedding concerns
- `utils/db.py` owns SQLite access and schema helpers
- `utils/hashing.py` owns file hashing

The current implementation is intentionally local-first and intentionally simple. Do not add unnecessary abstraction, framework-style indirection, or premature generalization.

## Coding Priorities

Optimize for human readability first.

Preferred style:

- small functions with one clear job
- explicit data flow over cleverness
- obvious naming over short naming
- straightforward control flow over compact tricks
- modular changes that preserve clean boundaries between ingestion, chunking, storage, and retrieval

Avoid:

- hidden coupling between FAISS ordering and SQLite ordering unless it is made explicit and well-documented
- mixing search logic, storage logic, and presentation logic in one place
- broad refactors that make the experiment harder to inspect
- adding complexity only to make the code feel more "production-like"

When making architectural changes, prefer the smallest change that makes the system more reliable and easier to understand.

If the codebase starts getting messy, larger refactors are acceptable when they materially improve readability, modularity, and flow. Do not refactor just because the project is under source control; refactor when the result is clearly easier for humans to understand and maintain. If a bigger refactor seems justified, explain the tradeoff to the user clearly.

## Retrieval and Evaluation Direction

`todo.md` is the living task list for this repository.

Agents should read `todo.md` before starting substantial work, use it to understand current priorities, and update or improve it when that would make the next steps clearer. The goal is to keep task tracking in one place instead of rewriting the todo list inside `AGENTS.md`.

When investigation produces meaningful findings, record them in `todo.md`. Do not limit updates to unchecked boxes only; use the file as a concise engineering log for completed work, open questions, and recommended next steps.

`docs/retrieval-pipeline.md` is the short reference note for the current retrieval design.
If retrieval behavior, scoring, chunking, or display-context logic changes in a meaningful way, keep that document aligned with the code. Do not let it drift into a stale theory document.

## Working Rules for This Repo

- Preserve the local-first nature of the demo.
- Keep dependencies justified and minimal.
- Prefer incremental improvements over big rewrites.
- If a tradeoff is experimental, document it clearly in code or in `README.md`.
- When changing schemas or indexing behavior, keep the mapping between stored metadata and retrieval results explicit.
- If a change affects retrieval quality, add a simple way to inspect or validate the impact.
- Prefer reusable local inspection tools over long one-off shell commands when the same debugging task is likely to recur.
- If a debugging workflow becomes awkward, standardize it in a small script with clear parameters rather than repeating ad hoc command snippets.

## Notes for Future Changes

This repo is an experimentation platform, not just an application. Good changes make it easier to answer questions such as:

- What changed?
- Why did retrieval improve or regress?
- Which component caused the change?
- Can the result be reproduced locally?

If a proposed change makes those questions harder to answer, it is probably the wrong change for this repository.
