# Live Demo Script — AssetMind

A ~5-minute narrative that walks judges through every capability in one
continuous story, instead of clicking through features in isolation. The
sample corpus (`sample_docs/`, 31 documents) is purpose-built around a single
asset — **Pump P-101A** — so every panel lights up around the same story.

> **Tip:** the app has a built-in **"▶ Guided Demo"** button in the sidebar
> that walks this exact golden path for you — Prev/Next controls, auto-filled
> questions, and it drives panel navigation so you can't accidentally wander
> into an unrelated asset mid-demo. Everything below is the same script, for
> when you want to narrate manually instead.

Start the backend, open the app, and upload all of `sample_docs/` before you
begin (or do the upload live as step 1 for full effect).

---

### 1. Upload (Documents panel) — "heterogeneous data in, one brain out"
Drag the whole `sample_docs/` folder onto the dropzone. Narrate while it
ingests: *"This is deliberately messy — maintenance logs, permits, SOPs, OEM
manuals, inspection reports, incident reports, a compliance audit — the exact
7-12 disconnected systems a plant normally has. It all gets chunked, OCR'd if
scanned, and entity-linked automatically."*

### 2. Dashboard — the 10-second overview
Switch to **Dashboard**. Point at the cards: documents processed, equipment
monitored, active permits, compliance score, critical alerts, recurring
failures. *"Before anyone asks a single question, the system already knows
something is wrong."* Point at the **P-101A** entry in the recurring-failure
list.

### 3. Ask the question (AssetMind Copilot)
Type — or tap the mic and say — **"Why is Pump P-101A failing?"**
The answer comes back grounded in retrieved passages with page-accurate
source citations. Toggle 🔊 spoken replies beforehand so the answer is read
aloud for effect.

### 4. Same question, but watch the agents work (Agent Workflow)
Ask the identical question in **Agent Workflow**. Narrate the pipeline as it
runs: *"Retrieval Agent finds the passages. Knowledge Graph Agent expands
P-101A to every cross-referenced document. Compliance Agent checks the
regulatory picture. RCA Agent checks for recurring failure patterns. Final
Reasoning Agent synthesizes all four into one grounded answer."* This is the
"Agentic AI" moment — five agents, one visible trace, not a black box.

### 5. Knowledge Graph — show the web
Switch to **Knowledge Graph**. Drag a few nodes, zoom in on the P-101A
cluster. *"Every maintenance log, permit, inspection, and incident touching
this pump is now one connected object instead of five separate filing
systems."*

### 6. AssetMind Twin — click into the asset
Switch to **AssetMind Twin**, click the `P-101A` tile (it's outlined in red —
flagged risk). The dossier panel opens in one click with everything about
this asset: **active permits**, its **maintenance/RCA timeline**, and every
**linked document** — plus a **"◈ View in Knowledge Graph"** button that jumps
straight back to panel 5 with the P-101A node highlighted and centered.
*"This is the unified operational view the problem statement asks for — one
click, everything about the asset, and it's the same graph you just saw."*

### 7. Maintenance / RCA — the root-cause timeline
Switch to **Maintenance / RCA**, run the analysis, and open the P-101A
finding. Walk the generated timeline left to right: **maintenance logs →
signal detected (vibration/seal deviation) → AI root cause**. Read the
recommendation aloud — it's the same escalation-gap story: *"Vibration and
seal-weep readings trended upward for seven months across four maintenance
logs and two inspection reports before the seal failed. The system catches
that pattern; the paper trail didn't."*

### 8. Compliance
Switch to **Compliance** and run the scan — show 100% checklist coverage
across OISD, DGMS, Factory Act, PESO, TIA-942, BICSI, Uptime Institute, and
ISO, all pulled from the actual corpus, not asserted.

### 9. Executive Summary — the close
Switch to **Executive Summary**, click **Generate report**, and download it.
*"One click turns everything you just watched — retrieval, graph, RCA,
compliance — into a report a plant manager can act on Monday morning."*

---

## Why this order works
Each step reuses the *same* asset (P-101A) and the *same* question, so the
audience isn't asked to context-switch — they watch one incident get
investigated from six different angles, which is the actual pitch: **the data
already existed, it just wasn't connected.**
