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
- chunk generation for PDFs
- sentence-transformer embeddings
- SQLite metadata storage
- FAISS vector index rebuild
- simple local search over indexed content

The current implementation is intentionally local-first. Source data is processed locally for this demo and is not intended to be redistributed through the repository.

Current indexing tradeoff:
- the FAISS index is rebuilt from stored chunks after ingestion instead of being updated incrementally
- this is intentional for the current stage of the project

Why keep it this way for now:
- simple implementation
- minimal moving parts
- easier to reason about during experimentation
- faster to iterate on ingestion logic and storage design

Known downside:
- the mapping between stored chunk metadata and FAISS rows is implicit, so the approach is more fragile if modified incorrectly
- this is acceptable for the current demo, but more explicit indexing and update logic will matter as the project moves toward larger-scale evaluation

## Install

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
