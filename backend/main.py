import shutil
import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ingest import process_document
from vector_store import VectorStore
from knowledge_graph import KnowledgeGraph
import agents

logger = logging.getLogger("assetmind")

UPLOAD_DIR = Path(__file__).parent / "uploaded_docs"
UPLOAD_DIR.mkdir(exist_ok=True)

SAMPLE_DOCS_DIR = Path(__file__).parent.parent / "sample_docs"

vector_store = VectorStore()
knowledge_graph = KnowledgeGraph()
documents_registry = {}  # doc_id -> metadata


def _ingest_file(filepath: Path, doc_type: str = "general_document"):
    """Ingest a single file into the vector store and knowledge graph."""
    doc_id = str(uuid.uuid4())
    try:
        records = process_document(filepath, doc_id, filepath.name, doc_type)
        if not records:
            return 0
        for r in records:
            try:
                knowledge_graph.add_chunk(r)
            except Exception:
                r.setdefault("entities", {})
        vector_store.add(records)
        documents_registry[doc_id] = {
            "doc_id": doc_id,
            "name": filepath.name,
            "type": doc_type,
            "chunks": len(records),
            "ocr_used": any(r.get("source_ocr") for r in records),
        }
        return len(records)
    except Exception as e:
        logger.warning(f"Auto-ingest skipped {filepath.name}: {e}")
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-ingest sample documents on startup so the app is ready out of the box."""
    if SAMPLE_DOCS_DIR.exists():
        files = sorted(f for f in SAMPLE_DOCS_DIR.iterdir() if f.is_file())
        logger.info(f"Auto-ingesting {len(files)} sample documents from {SAMPLE_DOCS_DIR}…")
        total_chunks = 0
        for f in files:
            chunks = _ingest_file(f, _guess_doc_type(f.name))
            total_chunks += chunks
        logger.info(f"Auto-ingest complete: {len(documents_registry)} docs, {total_chunks} chunks indexed.")
    else:
        logger.info("No sample_docs/ directory found — skipping auto-ingest.")
    yield  # app runs here


app = FastAPI(title="AssetMind API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Last-resort safety net: never let an unhandled error crash the app or
    return a bare 500 HTML page — always JSON the frontend can render."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"Something went wrong ({type(exc).__name__}). Please try again."},
    )


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class EntityLookup(BaseModel):
    category: str
    value: str


@app.get("/api/health")
def health():
    return {"status": "ok", "vector_backend": vector_store.backend}


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.strip():
        raise HTTPException(400, "No file selected. Please choose a file to upload.")

    allowed = {".pdf", ".txt", ".md", ".log", ".csv", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type '{suffix or 'none'}'. Allowed: {', '.join(sorted(allowed))}")

    doc_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{doc_id}{suffix}"
    try:
        with save_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception:
        raise HTTPException(500, "Could not save the uploaded file. Please try again.")

    if save_path.stat().st_size == 0:
        save_path.unlink(missing_ok=True)
        raise HTTPException(400, f"'{file.filename}' is empty (0 bytes). Please upload a non-empty file.")

    doc_type_guess = _guess_doc_type(file.filename)

    try:
        records = process_document(save_path, doc_id, file.filename, doc_type_guess)
    except Exception as e:
        # Corrupted PDF, unreadable image, unsupported encoding, missing OCR
        # binaries, etc. — never crash the request, tell the user plainly.
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            422,
            f"Couldn't read '{file.filename}' — the file may be corrupted, password-protected, "
            f"or in an unsupported format. ({type(e).__name__})",
        )

    if not records:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            422,
            f"No extractable text found in '{file.filename}'. If this is a scanned document, "
            "OCR may be unavailable on this server — try a text-based file instead.",
        )

    for r in records:
        try:
            knowledge_graph.add_chunk(r)  # enriches r["entities"] in place
        except Exception:
            r.setdefault("entities", {})

    try:
        vector_store.add(records)
    except Exception:
        raise HTTPException(500, "Indexing failed while adding this document to the search index.")

    used_ocr = any(r.get("source_ocr") for r in records)
    documents_registry[doc_id] = {
        "doc_id": doc_id,
        "name": file.filename,
        "type": doc_type_guess,
        "chunks": len(records),
        "ocr_used": used_ocr,
    }

    return {
        "doc_id": doc_id,
        "name": file.filename,
        "chunks_indexed": len(records),
        "vector_backend": vector_store.backend,
        "ocr_used": used_ocr,
    }


def _guess_doc_type(filename: str) -> str:
    name = filename.lower()
    if any(k in name for k in ["permit", "ptw"]):
        return "permit"
    if any(k in name for k in ["maintenance", "wo-", "workorder"]):
        return "maintenance_record"
    if any(k in name for k in ["incident", "near-miss", "nearmiss"]):
        return "incident_report"
    if any(k in name for k in ["spec", "standard", "oisd", "dgms"]):
        return "specification"
    if any(k in name for k in ["sop", "procedure"]):
        return "operating_procedure"
    if any(k in name for k in ["scan", "handwritten", "photo", "manual"]):
        return "scanned_manual_or_log"
    return "general_document"


@app.get("/api/documents")
def list_documents():
    return {"documents": list(documents_registry.values())}


@app.post("/api/query")
def query(req: QueryRequest):
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty. Please type a question.")
    try:
        return agents.answer_query(req.query, vector_store, top_k=req.top_k)
    except Exception as e:
        raise HTTPException(500, f"Query failed: {type(e).__name__}. Please try again.")


@app.post("/api/agents/orchestrate")
def orchestrate(req: QueryRequest):
    """Multi-agent pipeline: Retrieval -> Knowledge Graph -> Compliance -> RCA -> Final Reasoning."""
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty. Please type a question.")
    try:
        return agents.orchestrate_query(req.query, vector_store, knowledge_graph, top_k=req.top_k)
    except Exception as e:
        raise HTTPException(500, f"Agent pipeline failed: {type(e).__name__}. Please try again.")


@app.get("/api/agents/executive-summary")
def executive_summary():
    try:
        return agents.executive_summary_agent(knowledge_graph, vector_store)
    except Exception as e:
        raise HTTPException(500, f"Report generation failed: {type(e).__name__}. Please try again.")


@app.get("/api/dashboard")
def dashboard():
    try:
        return agents.dashboard_summary(knowledge_graph, vector_store, documents_registry)
    except Exception:
        return {
            "documents_processed": len(documents_registry),
            "equipment_monitored": 0,
            "active_permits": 0,
            "compliance_score_pct": 0,
            "critical_alerts": 0,
            "recurring_failures": 0,
            "top_findings": [],
        }


@app.get("/api/equipment")
def list_equipment():
    return {"equipment": knowledge_graph.top_entities(category="equipment_tags", limit=200)}


@app.get("/api/graph")
def get_graph():
    try:
        return knowledge_graph.export_graph_json()
    except Exception:
        return {"nodes": [], "edges": []}


@app.get("/api/graph/stats")
def graph_stats():
    try:
        return knowledge_graph.summary_stats()
    except Exception:
        return {"documents": 0, "total_nodes": 0, "total_edges": 0, "entities_by_category": {}}


@app.get("/api/graph/top-entities")
def top_entities(category: str = None, limit: int = 25):
    return {"entities": knowledge_graph.top_entities(category=category, limit=limit)}


@app.post("/api/graph/entity")
def entity_lookup(req: EntityLookup):
    if not req.value or not req.value.strip():
        raise HTTPException(400, "Entity value cannot be empty.")
    return knowledge_graph.entity_neighbors(req.category, req.value)


@app.get("/api/agents/maintenance-rca")
def maintenance_rca():
    try:
        return agents.maintenance_rca_agent(knowledge_graph)
    except Exception:
        return {"findings": [], "total_flagged_equipment": 0}


@app.get("/api/agents/compliance")
def compliance():
    try:
        return agents.compliance_agent(knowledge_graph)
    except Exception:
        return {
            "coverage_pct": 0,
            "standards_referenced_in_corpus": [],
            "checklist_covered": [],
            "checklist_gaps": list(agents.REQUIRED_STANDARDS),
        }


@app.get("/api/vector-stats")
def vector_stats():
    return vector_store.stats()


# Serve the frontend (single-page app) if present
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
