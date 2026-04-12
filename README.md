# Engineering-Focused RAG Evaluation Platform for Embedded Development

Local demo project exploring how to improve AI-assisted embedded software development by providing better hardware-grounded context.

One of the biggest problems with using general AI models in embedded work is that the model is often oblivious to the actual hardware constraints, vendor documentation, and exact implementation details. The goal of this project is to test methods such as local RAG pipelines and custom tool support, and to evaluate their impact in an engineering-oriented way.

The current demo uses ESP32 documentation as the source corpus. The broader objective is improved practical use of AI models in embedded environments by measuring whether better retrieval and better data handling lead to better answers, fewer hallucinations, and more useful engineering output.

## Why This Exists

This repo is a lightweight experimentation platform for evaluating the impact of context-building methods in embedded development workflows.

Questions this repo is trying to answer:
- How should embedded reference material be ingested so it stays repeatable and inspectable?
- How can ingestion reprocess only changed data instead of rebuilding everything?
- How do chunking strategy, embedding model choice, and storage format affect retrieval quality?
- How well do these choices scale as the documentation set grows?
- What measurable impact do retrieval and tooling improvements have on embedded AI assistance?

## Current Demo

Right now this repo provides:
- local PDF ingestion from `data/`
- file-level change detection using hashes
- deleted-file detection for removed source PDFs
- chunk generation for PDFs
- sentence-transformer embeddings
- SQLite metadata storage
- explicit index-build metadata and vector-to-chunk mapping in SQLite
- FAISS vector indexing with durable vector ids
- simple local search over indexed content

The current implementation is intentionally local-first. Source data is processed locally for this demo and is not intended to be redistributed through the repository.

Current indexing tradeoff:
- normal ingest runs update FAISS incrementally by removing and adding only the affected document vectors
- `--force-rebuild` still clears storage and rebuilds the full active index from scratch
- this is intentional for the current stage of the project

Why keep it this way for now:
- simple implementation
- minimal moving parts
- easier to reason about during experimentation
- faster to iterate on ingestion logic and storage design

What is explicit now:
- each index build is recorded in SQLite
- each FAISS `vector_id` is mapped to a durable `chunk_id`
- search resolves FAISS hits through stored index metadata instead of relying on repeated row ordering
- when a tracked PDF is removed from `data/`, its chunks and vectors are deleted from the active index state

Current limitation:
- vector ids are durable within the active index state, but `--force-rebuild` intentionally assigns a fresh index from scratch
- larger corpora may still justify additional work such as embedding reuse across experimental rebuilds, richer index-version history, or more sophisticated update policies

## Install

Tested with:

```bash
python3 --version
Python 3.12.3
```

If you use an older Python such as `3.10.x`, setup or runtime behavior may fail. For now, prefer Python `3.12`.

```bash
source ./setup_venv.sh
```

Note: This script targets Linux/macOS shells. On Windows, use WSL or create the virtual environment manually:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The script creates `.venv` if needed, activates it with the standard Ubuntu shell command `source .venv/bin/activate`, upgrades `pip`, and installs from `requirements.txt`. If you run `./setup_venv.sh` instead of `source ./setup_venv.sh`, setup still runs, but the virtual environment will not stay active in your current terminal after the script exits.

If you have CUDA-enabled PyTorch already installed, the embedder will use GPU automatically.

## Run

Place PDFs anywhere under `./data/`, then run:

```bash
python ingest.py
```

To rebuild from scratch:

```bash
python ingest.py --force-rebuild
```

After ingesting documents:

```bash
python search_index.py
```

## Project Layout

```text
.
├── ingest.py
├── search_index.py
├── data/
├── storage/
├── chunkers/
├── processing/
└── utils/
```

## Roadmap

- Make chunking, embedding, and storage settings easier to configure for controlled experiments
- Define evaluation criteria for retrieval quality and downstream answer quality
- Compare different retrieval and tooling approaches for embedded development tasks
- Expand beyond PDFs into more realistic embedded-documentation sources
- Measure which approaches materially improve AI usefulness in embedded environments
