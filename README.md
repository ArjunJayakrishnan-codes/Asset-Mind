# AssetMind

### From Documents to Decisions.

**Transform Industrial Documents into Actionable Intelligence**

✔ Document Intelligence &nbsp;|&nbsp; ✔ Knowledge Graph &nbsp;|&nbsp; ✔ Multi-Agent AI &nbsp;|&nbsp; ✔ Predictive Maintenance &nbsp;|&nbsp; ✔ Compliance &nbsp;|&nbsp; ✔ Digital Twin

> **AI Industrial Knowledge Intelligence Platform — ET AI Hackathon 2026 (Problem Statement 8)**

---

## What is AssetMind?

AssetMind is a working prototype that ingests heterogeneous industrial documents (maintenance records, permits, incident reports, specifications, SOPs, scanned manuals, and photographed handwritten logs), extracts entities into a knowledge graph, and exposes an **agentic** reasoning layer on top — all accessible through a premium, modern single-page web UI.

### Feature Overview

| Panel | What it does |
|---|---|
| **Operations Dashboard** | Documents processed, equipment monitored, active permits, compliance score, critical alerts, recurring failures — at a glance |
| **AssetMind Copilot** | RAG chat with source citations, voice input (mic) and spoken replies |
| **Multi-Agent Workflow** | `Retrieval → KG → Compliance → RCA → Final Reasoning` chain with a visible step-by-step trace |
| **Knowledge Graph Explorer** | Documents ↔ Chunks ↔ Entities rendered as an interactive, draggable/zoomable graph (Cytoscape.js) |
| **AssetMind Twin** | Clickable SVG plant layout; each equipment tile opens a one-click dossier (permits, RCA timeline, linked docs) |
| **Maintenance / RCA Agent** | Surfaces equipment recurring across incident/failure language with a root-cause timeline |
| **Compliance Agent** | Checks which regulatory standards (OISD, DGMS, Factory Act, PESO, TIA-942, BICSI, Uptime Institute, ISO) are referenced in the corpus |
| **Executive Summary Generator** | One-click report: incident summary + RCA highlights + compliance gaps + recommended actions, downloadable as `.txt` |
| **▶ Guided Demo** | Built-in stepper in the sidebar walks a presenter through the golden path with pre-filled questions |

---

## Quick Start

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000
```

Open **http://localhost:8000** — the frontend is served automatically by the FastAPI backend.

**Optional — LLM answers:**
```bash
export GROQ_API_KEY=gsk_...   # Linux/macOS
set GROQ_API_KEY=gsk_...      # Windows
uvicorn main:app --port 8000
```
Without a key, every agent falls back to an extractive (raw-passage) answer — the platform fully works either way.

**Optional — OCR for scanned PDFs / handwritten photos:**
```bash
# Ubuntu/Debian
apt-get install tesseract-ocr poppler-utils
```
If not installed, ingestion silently skips OCR and keeps whatever native text was extracted.

---

## Sample Documents & Demo

`sample_docs/` ships with **31 documents** deliberately cross-referenced around one coherent asset story — **Pump P-101A** — spanning:

- Maintenance logs, inspection reports, permits-to-work
- OEM manuals, SOPs, near-miss & incident reports
- A site-wide compliance audit and a final RCA report
- Supporting equipment: `P-101B`, `M-330`, `CV-512`, `V-405`, `T-210`, `HX-2201`, `UPS-301`, `GEN-110`, `SW-220`

Upload the whole `sample_docs/` folder and every panel — dashboard, graph, digital twin, RCA timeline, compliance, executive summary — lights up around the same connected story.

**Good first questions to try in AssetMind Copilot:**
- *"Why is Pump P-101A failing?"*
- *"Summarize maintenance history for P-101A"*
- *"What compliance standards are referenced?"*
- *"What caused the HX-2201 incident?"*
- *"List all active permits"*

Then try the same question in **Agent Workflow** to watch all five agents reason step-by-step.

For a full walkthrough, click **▶ Guided Demo** in the sidebar — it walks the golden path (upload → dashboard → copilot → agent workflow → graph → twin → RCA → compliance → executive report) with Prev/Next controls and pre-filled questions.

---

## Architecture

```
┌─────────────┐      ┌──────────────────────────────────────────────────────┐
│  Frontend   │─────▶│                   FastAPI Backend                    │
│ (index.html │      │                                                      │
│  HTML/JS +  │      │  ingest.py          → PDF/TXT/image parsing + OCR    │
│  Cytoscape) │      │  entities.py        → rule-based entity extraction   │
└─────────────┘      │  vector_store.py    → embeddings + similarity search │
                      │  knowledge_graph.py → networkx graph                 │
                      │  agents.py          → RAG / multi-agent orchestration│
                      │                        RCA / Compliance / Exec report │
                      └──────────────────────────────────────────────────────┘
```

### Backend Components

**`ingest.py`** — PDFs via `pypdf`; when a page yields near-zero extractable text (scanned page), it's rasterized (`pdf2image`) and OCR'd (`pytesseract`). Standalone images (photos of handwritten logs, nameplates, manual pages) are OCR'd directly. Sliding-window chunking (~900 chars, 150 overlap) keeps citations page-accurate.

**`entities.py`** — Transparent regex/heuristic extraction of equipment tags (e.g. `HX-2201`), work orders, permits, regulatory standards, roles, and incident keywords. Deliberately rule-based and inspectable — swap in spaCy or an LLM extractor later behind the same function signature.

**`vector_store.py`** — Tries `sentence-transformers` (`all-MiniLM-L6-v2`) + FAISS for semantic search. If the model can't be downloaded (offline environment), automatically falls back to scikit-learn TF-IDF + cosine similarity — the platform works end-to-end with zero external dependencies at runtime.

**`knowledge_graph.py`** — `networkx` graph of `Document ↔ Chunk ↔ Entity`. Powers entity-lookup (the AssetMind Twin dossier), graph visualization, and `recurring_incident_patterns()` — the cross-document pattern detection behind the RCA agent.

**`agents.py`** — Five agents:
- `answer_query()` — retrieval + optional Groq/LLM synthesis, always returns cited sources
- `orchestrate_query()` — multi-agent pipeline: Retrieval → Knowledge Graph → Compliance → RCA → Final Reasoning
- `maintenance_rca_agent()` — flags equipment mentioned alongside incident/failure language across ≥1 documents
- `compliance_agent()` — checklist coverage of regulatory standards found in the corpus
- `executive_summary_agent()` — compiles incident summary + RCA + compliance gaps + recommended actions
- `dashboard_summary()` — aggregate counters for the dashboard cards

**Frontend (`frontend/index.html`)** — Single-page app, no build step required. Knowledge graph via Cytoscape.js (CDN). AssetMind Twin is a dynamically generated, auto-scaling SVG grid. Voice copilot uses the browser's native `SpeechRecognition` and `speechSynthesis` APIs — no server-side speech infra.

---

## Reliability — Designed to Never Crash on Stage

| Scenario | Behavior |
|---|---|
| Empty upload / no file selected | `400` with a plain message; frontend never hangs |
| Corrupted or password-protected PDF | Caught in `ingest.py`/`main.py`, returns `422` with the reason |
| Empty search query | Blocked client- and server-side before hitting an agent |
| OCR unavailable (no Tesseract/poppler) | Silently skips OCR, keeps whatever native text was found |
| LLM unavailable (no `GROQ_API_KEY` or API down) | Every agent falls back to extractive answers from retrieved passages |
| No internet (embedding model can't download) | `vector_store.py` falls back to scikit-learn TF-IDF automatically at startup |
| Any other unexpected error | Global FastAPI exception handler returns JSON — UI always has something to render |

---

## Performance Targets

Every AI action shows a live step-by-step loading sequence instead of a static spinner:

- **Dashboard** — < 1s (in-memory counters)
- **Copilot** — < 2s (TF-IDF or MiniLM retrieval + optional LLM synthesis)
- **Multi-Agent Workflow (5 agents)** — < 5s; the visible per-agent trace makes the wait feel intentional

---

## Design System

The frontend uses a **neo-brutalist / sticker aesthetic**:
- Warm cream background (`#FFFDF5`) with a subtle dot-grid pattern
- Chunky `2px solid #1E293B` borders + hard offset `box-shadow` on every card
- Accent palette: Vivid Violet (`#8B5CF6`), Amber Yellow (`#FBBF24`), Mint Green (`#34D399`), Hot Pink (`#F472B6`)
- Typography: **Outfit** (display headings) + **Plus Jakarta Sans** (body) + **JetBrains Mono** (code)
- Micro-animations: bounce-spring transitions (`cubic-bezier(0.34, 1.56, 0.64, 1)`), hover lift + rotate, pop-in entrance animations

---

## Extending Toward Production

- Swap TF-IDF/MiniLM for a domain-tuned embedding model once real plant-scale document volume is available
- Replace regex entity extraction with a fine-tuned NER model or LLM-based extraction for higher recall on non-standard tag formats
- Move `networkx` (in-memory) to Neo4j for scale + Cypher queries (`knowledge_graph.py` is written so this swap touches only one file)
- Give the AssetMind Twin real plant coordinates (from a P&ID or facility GIS) instead of the auto-generated grid layout
- Add auth + per-plant multi-tenancy before any real deployment

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI + Uvicorn |
| Document parsing | pypdf, pdf2image, pytesseract |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) → FAISS, fallback: scikit-learn TF-IDF |
| Knowledge graph | networkx |
| LLM | Groq API (`llama-3.1-8b-instant`), optional |
| Frontend | Vanilla HTML + CSS + JavaScript (no build step) |
| Graph visualization | Cytoscape.js |

---

*AssetMind — From Documents to Decisions.*
