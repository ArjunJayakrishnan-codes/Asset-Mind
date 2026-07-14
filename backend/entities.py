"""
Lightweight, dependency-free entity extraction tuned for industrial documents:
equipment tags, standards/regulations, dates, personnel/roles, work order & permit numbers.

This is a rule-based extractor (regex + keyword heuristics). It is intentionally
transparent and fast so it runs on CPU with no model download — swap in spaCy /
an LLM-based extractor later without changing the downstream knowledge graph API.
"""
import re
from typing import List, Dict

WORK_ORDER_RE = re.compile(r"\bWO[-#]?\d{3,7}\b", re.IGNORECASE)         # WO-10234
PERMIT_RE = re.compile(r"\b(?:PTW|PERMIT)[-#]?\d{2,7}\b", re.IGNORECASE)
_EQUIPMENT_EXCLUDE_PREFIXES = ("WO", "PTW", "STD", "IS", "ISO")
EQUIPMENT_TAG_RE = re.compile(r"\b[A-Z]{1,4}-\d{2,5}[A-Z]?\b")           # e.g. P-101A, HX-2201, V-405
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b"
)
STANDARD_RE = re.compile(
    r"\b(?:OISD(?:-STD)?[-\s]?\d{2,4}|DGMS\s?\w*|Factory Act(?:\s+\d{4})?|"
    r"TIA-942|BICSI|Uptime Institute Tier\s?(?:I{1,3}|IV)|IS\s?\d{3,5}|PESO|"
    r"ISO\s?\d{4,5}(?::\d{4})?)\b",
    re.IGNORECASE,
)
ROLE_RE = re.compile(
    r"\b(?:Shift Engineer|Safety Officer|Plant Manager|Maintenance Engineer|"
    r"Operator|Supervisor|Inspector|Contractor|QA Engineer|QC Inspector|"
    r"Site Engineer|Commissioning Engineer)\b",
    re.IGNORECASE,
)
INCIDENT_KEYWORDS = re.compile(
    r"\b(?:leak|explosion|fire|near[- ]miss|spill|entrapment|failure|breakdown|"
    r"non[- ]conformance|deviation|trip|shutdown|overrun|delay)\b",
    re.IGNORECASE,
)


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Return deduplicated entity lists found in a chunk of text."""
    raw_equipment = set(EQUIPMENT_TAG_RE.findall(text))
    equipment = {e for e in raw_equipment if e.split("-")[0].upper() not in _EQUIPMENT_EXCLUDE_PREFIXES}

    return {
        "equipment_tags": sorted(equipment),
        "work_orders": sorted(set(m.upper() for m in WORK_ORDER_RE.findall(text))),
        "permits": sorted(set(m.upper() for m in PERMIT_RE.findall(text))),
        "dates": sorted(set(DATE_RE.findall(text))),
        "standards": sorted(set(m.strip() for m in STANDARD_RE.findall(text))),
        "roles": sorted(set(m.title() for m in ROLE_RE.findall(text))),
        "incident_terms": sorted(set(m.lower() for m in INCIDENT_KEYWORDS.findall(text))),
    }


def has_entities(entities: Dict[str, List[str]]) -> bool:
    return any(len(v) > 0 for v in entities.values())
