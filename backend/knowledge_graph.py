"""
Knowledge graph layer.

Builds a graph connecting Documents <-> Chunks <-> Entities (equipment tags,
work orders, permits, standards, roles, incident terms). This is what lets the
platform answer "what connects to Pump P-101A across every system" type
questions, and is the backbone for cross-document pattern detection
(e.g. Lessons-Learned / RCA agent).
"""
import networkx as nx
from typing import Dict, List
from collections import defaultdict

from entities import extract_entities


class KnowledgeGraph:
    def __init__(self):
        self.g = nx.Graph()

    def add_chunk(self, chunk: Dict):
        doc_node = f"doc::{chunk['doc_id']}"
        chunk_node = f"chunk::{chunk['chunk_id']}"

        self.g.add_node(doc_node, type="document", name=chunk["doc_name"], doc_type=chunk["doc_type"])
        self.g.add_node(chunk_node, type="chunk", page=chunk["page_number"], doc_id=chunk["doc_id"])
        self.g.add_edge(doc_node, chunk_node, relation="contains")

        entities = extract_entities(chunk["text"])
        chunk["entities"] = entities

        for category, values in entities.items():
            for val in values:
                ent_node = f"{category}::{val}"
                if not self.g.has_node(ent_node):
                    self.g.add_node(ent_node, type="entity", category=category, label=val)
                self.g.add_edge(chunk_node, ent_node, relation="mentions")
                # also connect entity directly to document for fast doc-level queries
                self.g.add_edge(doc_node, ent_node, relation="mentions")

        return entities

    def entity_neighbors(self, category: str, value: str) -> Dict:
        """All documents/chunks/co-occurring entities linked to a given entity."""
        node = f"{category}::{value}"
        if not self.g.has_node(node):
            return {"found": False}

        docs, other_entities = set(), defaultdict(set)
        for neighbor in self.g.neighbors(node):
            data = self.g.nodes[neighbor]
            if data.get("type") == "document":
                docs.add(data.get("name"))
            # walk one more hop through connected chunks to find co-mentioned entities
            if data.get("type") == "chunk":
                for n2 in self.g.neighbors(neighbor):
                    d2 = self.g.nodes[n2]
                    if d2.get("type") == "entity" and n2 != node:
                        other_entities[d2["category"]].add(d2["label"])
                    if d2.get("type") == "document":
                        docs.add(d2.get("name"))

        return {
            "found": True,
            "entity": value,
            "category": category,
            "documents": sorted(docs),
            "co_occurring_entities": {k: sorted(v) for k, v in other_entities.items()},
        }

    def top_entities(self, category: str = None, limit: int = 25) -> List[Dict]:
        """Most-connected entities (by degree) — surfaces recurring equipment/standards/issues."""
        rows = []
        for node, data in self.g.nodes(data=True):
            if data.get("type") != "entity":
                continue
            if category and data.get("category") != category:
                continue
            rows.append({
                "label": data["label"],
                "category": data["category"],
                "connections": self.g.degree(node),
            })
        rows.sort(key=lambda r: r["connections"], reverse=True)
        return rows[:limit]

    def recurring_incident_patterns(self, min_occurrences: int = 2) -> List[Dict]:
        """
        Lessons-Learned style pattern detection: incident terms that co-occur with
        the SAME equipment tag across MULTIPLE distinct documents -> recurring risk.
        """
        equipment_nodes = [n for n, d in self.g.nodes(data=True)
                            if d.get("type") == "entity" and d.get("category") == "equipment_tags"]

        patterns = []
        for eq_node in equipment_nodes:
            docs_with_incident = set()
            incident_terms = set()
            for chunk_node in self.g.neighbors(eq_node):
                if self.g.nodes[chunk_node].get("type") != "chunk":
                    continue
                chunk_neighbors = list(self.g.neighbors(chunk_node))
                terms_here = [self.g.nodes[n]["label"] for n in chunk_neighbors
                              if self.g.nodes[n].get("type") == "entity"
                              and self.g.nodes[n].get("category") == "incident_terms"]
                if terms_here:
                    doc_node = [n for n in chunk_neighbors if self.g.nodes[n].get("type") == "document"]
                    if doc_node:
                        docs_with_incident.add(self.g.nodes[doc_node[0]]["name"])
                    incident_terms.update(terms_here)

            if len(docs_with_incident) >= min_occurrences:
                patterns.append({
                    "equipment": self.g.nodes[eq_node]["label"],
                    "incident_terms": sorted(incident_terms),
                    "documents_affected": sorted(docs_with_incident),
                    "occurrence_count": len(docs_with_incident),
                })

        patterns.sort(key=lambda p: p["occurrence_count"], reverse=True)
        return patterns

    def summary_stats(self) -> Dict:
        by_category = defaultdict(int)
        for _, d in self.g.nodes(data=True):
            if d.get("type") == "entity":
                by_category[d["category"]] += 1
        return {
            "total_nodes": self.g.number_of_nodes(),
            "total_edges": self.g.number_of_edges(),
            "documents": sum(1 for _, d in self.g.nodes(data=True) if d.get("type") == "document"),
            "entities_by_category": dict(by_category),
        }

    def export_graph_json(self, limit_nodes: int = 300) -> Dict:
        """Small JSON export for frontend graph visualization (nodes + edges)."""
        nodes, edges = [], []
        count = 0
        included = set()
        for node, data in self.g.nodes(data=True):
            if count >= limit_nodes:
                break
            nodes.append({
                "id": node,
                "type": data.get("type"),
                "label": data.get("label") or data.get("name") or node.split("::")[-1],
                "category": data.get("category", data.get("doc_type", "")),
            })
            included.add(node)
            count += 1
        for u, v in self.g.edges():
            if u in included and v in included:
                edges.append({"source": u, "target": v})
        return {"nodes": nodes, "edges": edges}
