"""
Agent layer built on top of the vector store + knowledge graph.

- answer_query(): RAG Q&A with source citations (uses Groq API if
  GROQ_API_KEY is set, else falls back to a transparent extractive answer).
- maintenance_rca_agent(): correlates equipment across documents to produce
  RCA-style findings and predictive-maintenance flags.
- compliance_agent(): scans retrieved chunks for regulatory standard mentions
  vs. a checklist and flags gaps.
- orchestrate_query(): multi-agent pipeline (Retrieval -> Knowledge Graph ->
  Compliance -> RCA -> Final Reasoning) that chains the agents above and
  returns a step-by-step trace, not just the final answer.
- executive_summary_agent(): one-shot management-ready report (incident
  summary, RCA highlights, compliance issues, recommended actions).
- dashboard_summary(): aggregate counters for the operations dashboard.
"""
import os
from datetime import datetime, timezone
from typing import List, Dict

REQUIRED_STANDARDS = [
    "OISD", "DGMS", "Factory Act", "PESO", "TIA-942", "BICSI", "Uptime Institute", "ISO"
]


def _format_sources(hits: List[tuple]) -> List[Dict]:
    sources = []
    for record, score in hits:
        sources.append({
            "doc_name": record["doc_name"],
            "page": record["page_number"],
            "snippet": record["text"][:280] + ("…" if len(record["text"]) > 280 else ""),
            "relevance": round(score, 3),
        })
    return sources


def _extractive_answer(query: str, hits: List[tuple]) -> str:
    """No-LLM-key fallback: transparently stitches the most relevant retrieved
    passages into a cited answer instead of pretending to 'generate' one."""
    if not hits:
        return ("I couldn't find anything relevant in the ingested documents yet. "
                "Try uploading more documents or rephrasing the question.")
    lines = [f"Based on the ingested documents, here's what's most relevant to: \"{query}\"\n"]
    for i, (record, score) in enumerate(hits[:4], 1):
        lines.append(f"[{i}] ({record['doc_name']}, p.{record['page_number']}): {record['text'][:400]}")
    return "\n\n".join(lines)


def _groq_completion(prompt: str, max_tokens: int) -> str:
    import urllib.request
    import json
    import os

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured.")

    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AssetMind/1.0"
        },
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=30) as response:
        res = json.loads(response.read().decode("utf-8"))
        return res["choices"][0]["message"]["content"]


def _llm_answer(query: str, hits: List[tuple]) -> str:
    context = "\n\n".join(
        f"[Source {i+1} — {r['doc_name']}, page {r['page_number']}]\n{r['text']}"
        for i, (r, _) in enumerate(hits)
    )
    prompt = (
        "You are an industrial knowledge assistant. Answer the question ONLY using the "
        "provided sources. Cite sources inline like [Source 1]. If the sources don't "
        "contain the answer, say so plainly.\n\n"
        f"SOURCES:\n{context}\n\nQUESTION: {query}\n\nANSWER:"
    )
    return _groq_completion(prompt, max_tokens=700)


def answer_query(query: str, vector_store, top_k: int = 5) -> Dict:
    hits = vector_store.search(query, top_k=top_k)
    use_llm = bool(os.environ.get("GROQ_API_KEY", ""))
    try:
        answer = _llm_answer(query, hits) if use_llm else _extractive_answer(query, hits)
    except Exception as e:
        answer = _extractive_answer(query, hits) + f"\n\n(LLM synthesis failed: {e})"
    return {
        "query": query,
        "answer": answer,
        "sources": _format_sources(hits),
        "mode": "llm" if use_llm else "extractive",
    }


def maintenance_rca_agent(kg) -> Dict:
    """Cross-document Root-Cause / predictive-maintenance signal surfacing."""
    patterns = kg.recurring_incident_patterns(min_occurrences=1)
    findings = []
    for p in patterns:
        severity = "high" if p["occurrence_count"] >= 2 or len(p["incident_terms"]) >= 3 else "medium"
        findings.append({
            "equipment": p["equipment"],
            "severity": severity,
            "recurring_terms": p["incident_terms"],
            "documents": p["documents_affected"],
            "recommendation": (
                f"Equipment {p['equipment']} appears alongside "
                f"{', '.join(p['incident_terms'])} across {p['occurrence_count']} document(s). "
                "Recommend targeted inspection and review of maintenance history before next work order."
            ),
        })
    return {"findings": findings, "total_flagged_equipment": len(findings)}


def _llm_orchestrated_answer(query: str, hits, kg_context: Dict, compliance: Dict, rca: Dict) -> str:
    """Final Reasoning Agent's LLM call — synthesizes retrieval + graph +
    compliance + RCA context (rather than retrieval alone) into one answer."""
    context = "\n\n".join(
        f"[Source {i+1} — {r['doc_name']}, page {r['page_number']}]\n{r['text']}"
        for i, (r, _) in enumerate(hits)
    )
    graph_summary = "\n".join(
        f"- {tag}: linked documents {v.get('documents', [])}, co-occurring: {v.get('co_occurring_entities', {})}"
        for tag, v in kg_context.items()
    ) or "none"
    rca_summary = "\n".join(
        f"- {f['equipment']} ({f['severity']}): {f['recommendation']}" for f in rca.get("findings", [])[:5]
    ) or "none"
    compliance_summary = f"{compliance['coverage_pct']}% coverage; gaps: {compliance['checklist_gaps']}"

    prompt = (
        "You are the Final Reasoning Agent in a multi-agent industrial knowledge system. "
        "You receive outputs from upstream specialist agents and must synthesize ONE grounded "
        "answer. Cite retrieved sources inline like [Source 1]. If sources don't contain the "
        "answer, say so plainly. Weave in relevant knowledge-graph connections, RCA findings, "
        "or compliance gaps ONLY if they are relevant to the question.\n\n"
        f"RETRIEVED SOURCES:\n{context}\n\n"
        f"KNOWLEDGE GRAPH CONTEXT (equipment cross-references):\n{graph_summary}\n\n"
        f"RCA AGENT FINDINGS:\n{rca_summary}\n\n"
        f"COMPLIANCE AGENT STATUS:\n{compliance_summary}\n\n"
        f"QUESTION: {query}\n\nANSWER:"
    )
    return _groq_completion(prompt, max_tokens=800)


def orchestrate_query(query: str, vector_store, kg, top_k: int = 5) -> Dict:
    """
    Agentic pipeline: User Question -> Retrieval Agent -> Knowledge Graph Agent
    -> Compliance Agent -> RCA Agent -> Final Reasoning Agent.

    Returns the final answer PLUS a step-by-step trace of what each agent did,
    so the reasoning chain is visible rather than a single opaque call.
    """
    trace = []

    # 1) Retrieval Agent
    hits = vector_store.search(query, top_k=top_k)
    trace.append({
        "agent": "Retrieval Agent",
        "action": f"Semantic search across {len(vector_store.records)} indexed chunks",
        "output": f"Retrieved {len(hits)} relevant passage(s)" if hits else "No relevant passages found",
    })

    # 2) Knowledge Graph Agent — expand any equipment mentioned in the retrieved hits
    mentioned_equipment = set()
    for record, _ in hits:
        for tag in record.get("entities", {}).get("equipment_tags", []):
            mentioned_equipment.add(tag)
    kg_context = {tag: kg.entity_neighbors("equipment_tags", tag) for tag in list(mentioned_equipment)[:6]}
    linked_docs = {d for v in kg_context.values() for d in v.get("documents", [])}
    trace.append({
        "agent": "Knowledge Graph Agent",
        "action": f"Traversed graph for {len(mentioned_equipment)} equipment entit{'y' if len(mentioned_equipment)==1 else 'ies'} found in retrieval",
        "output": f"Cross-referenced {len(linked_docs)} additional document(s) via graph edges" if kg_context else "No equipment entities to expand",
    })

    # 3) Compliance Agent
    compliance = compliance_agent(kg)
    trace.append({
        "agent": "Compliance Agent",
        "action": "Checked corpus-wide standards coverage against regulatory checklist",
        "output": f"{compliance['coverage_pct']}% checklist coverage, {len(compliance['checklist_gaps'])} gap(s): {', '.join(compliance['checklist_gaps']) or 'none'}",
    })

    # 4) RCA Agent
    rca = maintenance_rca_agent(kg)
    trace.append({
        "agent": "RCA Agent",
        "action": "Correlated equipment tags with incident/failure language across documents",
        "output": f"{rca['total_flagged_equipment']} recurring pattern(s) flagged" if rca["findings"] else "No recurring failure patterns detected",
    })

    # 5) Final Reasoning Agent
    use_llm = bool(os.environ.get("GROQ_API_KEY", ""))
    try:
        final_answer = (
            _llm_orchestrated_answer(query, hits, kg_context, compliance, rca)
            if use_llm else _extractive_answer(query, hits)
        )
    except Exception as e:
        final_answer = _extractive_answer(query, hits) + f"\n\n(LLM synthesis failed: {e})"
    trace.append({
        "agent": "Final Reasoning Agent",
        "action": "Synthesized retrieval + graph + compliance + RCA context into one grounded answer",
        "output": "Answer generated" + (" (LLM synthesis)" if use_llm else " (extractive fallback — set GROQ_API_KEY for LLM synthesis)"),
    })

    return {
        "query": query,
        "answer": final_answer,
        "sources": _format_sources(hits),
        "graph_context": {
            tag: {"documents": v.get("documents", []), "co_occurring_entities": v.get("co_occurring_entities", {})}
            for tag, v in kg_context.items() if v.get("found")
        },
        "compliance_snapshot": compliance,
        "rca_snapshot": rca,
        "trace": trace,
        "mode": "llm" if use_llm else "extractive",
    }


def executive_summary_agent(kg, vector_store) -> Dict:
    """One-click management report: incident summary, RCA, compliance, actions."""
    rca = maintenance_rca_agent(kg)
    compliance = compliance_agent(kg)
    stats = kg.summary_stats()
    vstats = vector_store.stats()

    high = [f for f in rca["findings"] if f["severity"] == "high"]
    medium = [f for f in rca["findings"] if f["severity"] == "medium"]

    incident_summary = (
        f"Corpus covers {stats.get('documents', 0)} document(s) / {vstats.get('total_chunks', 0)} indexed passages, "
        f"referencing {stats.get('entities_by_category', {}).get('equipment_tags', 0)} distinct equipment tags. "
        f"{len(high)} equipment item(s) show high-severity recurring risk signals and "
        f"{len(medium)} show medium-severity signals, based on cross-document correlation of "
        f"incident/failure language with equipment mentions."
    )

    recommended_actions = []
    for f in rca["findings"][:6]:
        recommended_actions.append(f"[{f['severity'].upper()}] {f['equipment']}: {f['recommendation']}")
    for gap in compliance["checklist_gaps"]:
        recommended_actions.append(f"[COMPLIANCE] No corpus reference found for {gap} — verify documentation is on file and current.")
    if not recommended_actions:
        recommended_actions.append("No urgent actions flagged — corpus shows no recurring failure patterns or compliance gaps yet.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "incident_summary": incident_summary,
        "rca_highlights": rca["findings"][:6],
        "compliance_coverage_pct": compliance["coverage_pct"],
        "compliance_issues": compliance["checklist_gaps"],
        "standards_referenced": compliance["standards_referenced_in_corpus"],
        "recommended_actions": recommended_actions,
        "critical_alerts": len(high),
    }


def dashboard_summary(kg, vector_store, documents_registry: Dict) -> Dict:
    """Aggregate counters that power the operations dashboard cards."""
    equipment = kg.top_entities(category="equipment_tags", limit=5000)
    permits = kg.top_entities(category="permits", limit=5000)
    rca = maintenance_rca_agent(kg)
    compliance = compliance_agent(kg)
    critical_alerts = sum(1 for f in rca["findings"] if f["severity"] == "high")

    return {
        "documents_processed": len(documents_registry),
        "equipment_monitored": len(equipment),
        "active_permits": len(permits),
        "compliance_score_pct": compliance["coverage_pct"],
        "critical_alerts": critical_alerts,
        "recurring_failures": len(rca["findings"]),
        "total_chunks_indexed": vector_store.stats().get("total_chunks", 0),
        "top_findings": rca["findings"][:4],
    }


def compliance_agent(kg) -> Dict:
    """Compares standards actually referenced in the corpus vs. an expected checklist."""
    mentioned = {e["label"].upper() for e in kg.top_entities(category="standards", limit=500)}
    gaps, covered = [], []
    for std in REQUIRED_STANDARDS:
        found = any(std.upper() in m for m in mentioned)
        (covered if found else gaps).append(std)
    return {
        "standards_referenced_in_corpus": sorted(mentioned),
        "checklist_covered": covered,
        "checklist_gaps": gaps,
        "coverage_pct": round(100 * len(covered) / len(REQUIRED_STANDARDS), 1),
    }
