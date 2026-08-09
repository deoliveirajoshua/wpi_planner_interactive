#!/usr/bin/env python3
"""
WPI Course Prerequisite & Alias Scraper / Parser

Parses course descriptions from planner.wpi.edu / Workday JSON to extract:
1. Prerequisite course dependencies (with structured AND/OR logic)
2. Alias & cross-listed relationships (e.g. PY/RE 1731, CS/ECE 2039)
3. Mutually exclusive credit restrictions (e.g. "Credit not allowed for both...")

Features:
- Local LLM inference engine (Ollama Gemma / Hugging Face Gemma on CPU) with few-shot prompting
- Persistent content-hash caching (data/.cache_llm_prereqs.json)
- Deterministic Non-LLM Final Sanitization Layer guaranteeing graph invariants:
  * Zero self-prerequisites
  * Strict alias / prerequisite disjointness
  * Zero self-aliases
  * Bidirectional alias symmetry
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Set, Tuple, Any, Optional

# Enable importing from scripts directory regardless of current working directory
sys.path.insert(0, os.path.dirname(__file__))

KNOWN_DEPTS = {
    "AB", "ACC", "AE", "AM", "AR", "AREN", "AS", "BB", "BCB", "BME", "BUS",
    "CE", "CH", "CHE", "CN", "CS", "DS", "ECE", "ECON", "EDU", "EN", "ENV",
    "ER", "ES", "ET", "FIN", "FP", "FY", "GE", "GN", "GOV", "HI", "HU", "ID",
    "IGS", "IMGD", "ISE", "MA", "ME", "MFE", "MIS", "ML", "MME", "MTE", "MU",
    "NE", "OIE", "OJL", "OR", "PH", "PSY", "PY", "RE", "RBE", "SD", "SEL",
    "SP", "SS", "STS", "SYS", "TH", "WR"
}


def extract_course_codes_from_text(text: str, valid_codes: Set[str] = None) -> List[str]:
    """
    Extract course codes (e.g. CS 1101, PY/RE 1731, MA 1021/1022, CS 2102/3) from raw text snippet.
    """
    if not text:
        return []

    found = []

    # Handle slashed department pairs like PY/RE 1731 or CS/ECE 2039
    for m in re.finditer(r'\b([A-Z]{2,4})\s*/\s*([A-Z]{2,4})\s*(\d{4}[A-Z]?)\b', text):
        d1, d2, num = m.groups()
        for d in (d1, d2):
            code = f"{d} {num}"
            if d in KNOWN_DEPTS and (not valid_codes or code in valid_codes):
                found.append(code)

    # Handle slashed number pairs with full 4-digit numbers like MA 1021/1022 or PH 1110 / 1111
    for m in re.finditer(r'\b([A-Z]{2,4})\s*(\d{4}[A-Z]?)\s*/\s*(\d{4}[A-Z]?)\b', text):
        d, n1, n2 = m.groups()
        if d in KNOWN_DEPTS:
            for num in (n1, n2):
                code = f"{d} {num}"
                if not valid_codes or code in valid_codes:
                    found.append(code)

    # Handle shorthand slash numbers like CS 2102/3 or CS 2301/3 -> CS 2102, CS 2103
    for m in re.finditer(r'\b([A-Z]{2,4})\s*(\d{3,4}[A-Z]?)\s*/\s*(\d{1,2}[A-Z]?)\b', text):
        d, n1, n2_suffix = m.groups()
        if d in KNOWN_DEPTS:
            code1 = f"{d} {n1}"
            if not valid_codes or code1 in valid_codes:
                found.append(code1)
            # Reconstruct second course code
            prefix_len = len(n1) - len(n2_suffix)
            if prefix_len > 0:
                n2 = n1[:prefix_len] + n2_suffix
                code2 = f"{d} {n2}"
                if not valid_codes or code2 in valid_codes:
                    found.append(code2)

    # Handle sequences like CS 1101, 2102, or 2301
    seq_pat = r'\b([A-Z]{2,4})\s*(\d{4}[A-Z]?)(?:(?:\s*,\s*or\s*|\s*,\s*and\s*|\s*,\s*|\s+or\s+|\s+and\s+)(\d{4}[A-Z]?))+'
    for m in re.finditer(seq_pat, text, re.IGNORECASE):
        dept = m.group(1)
        if dept in KNOWN_DEPTS:
            nums = re.findall(r'\b(\d{4}[A-Z]?)\b', m.group(0))
            for num in nums:
                code = f"{dept} {num}"
                if not valid_codes or code in valid_codes:
                    found.append(code)

    # Standard DEPT NUM pattern
    for m in re.finditer(r'\b([A-Z]{2,4})\s*(\d{4}[A-Z]?)\b', text):
        d, n = m.groups()
        if d in KNOWN_DEPTS:
            code = f"{d} {n}"
            if not valid_codes or code in valid_codes:
                found.append(code)

    unique_codes = []
    for code in found:
        if code not in unique_codes:
            unique_codes.append(code)

    return unique_codes


def parse_prerequisites(description: str, valid_codes: Set[str] = None) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """
    Extract prerequisite course codes, structured AND/OR groups, and raw snippet.
    """
    if not description:
        return [], [], ""

    # Check for explicit negative background statements first
    neg_patterns = [
        r'recommended\s+background\s*[:\-]?\s*none\b',
        r'no\s+prerequisites\s+(?:are\s+suggested|are\s+required|suggested|required)',
        r'there\s+are\s+no\s+prerequisites',
        r'recommended\s+background\s*[:\-]?\s*no\s+prerequisites'
    ]
    for np in neg_patterns:
        if re.search(np, description, re.IGNORECASE):
            # If description explicitly says no prerequisites, return empty unless followed by specific course
            m_neg = re.search(np, description, re.IGNORECASE)
            raw_snippet = m_neg.group(0).strip()
            # Double check if any actual course code is in the negative snippet
            codes_in_neg = extract_course_codes_from_text(raw_snippet, valid_codes)
            if not codes_in_neg:
                return [], [], raw_snippet

    prereq_pattern = r'(recommended background|prerequisite[s]?|pre-requisite[s]?|background)\s*[:\-]\s*(.*?)(?=\.\s+[A-Z]|\.\s*Students|\.\s*~Note|\.$|\n|$)'
    m = re.search(prereq_pattern, description, re.IGNORECASE)

    if not m:
        return [], [], ""

    raw_snippet = m.group(0).strip()
    body_text = m.group(2).strip()

    # If body is simply 'None'
    if re.match(r'^(?:none|no prerequisites|n/a)\.?$', body_text, re.IGNORECASE):
        return [], [], raw_snippet

    # Strip inner parenthetical text to accurately evaluate top-level group logic
    clean_body_text = re.sub(r'\(.*?\)', '', body_text)
    has_explicit_top_or = bool(re.search(r'\bor\b', clean_body_text, re.IGNORECASE)) and ("and" not in clean_body_text.lower() and ";" not in clean_body_text)

    # Split body into clauses on ';', newlines, or commas separating topics
    raw_clauses = re.split(r';|\n|,\s*and\b|;\s*and\b|,\s*(?=[a-zA-Z])', body_text, flags=re.IGNORECASE)

    structured_groups = []
    all_codes_set = set()

    for clause in raw_clauses:
        clause_codes = extract_course_codes_from_text(clause, valid_codes)
        if not clause_codes:
            continue

        all_codes_set.update(clause_codes)

        # Check if clause contains slash pattern (e.g. PH 1110 / 1111) or 'or'
        has_slash = "/" in clause
        has_or = bool(re.search(r'\bor\b', clause, re.IGNORECASE)) or has_slash

        group_type = "OR" if (has_or and len(clause_codes) > 1) else "AND"

        structured_groups.append({
            "type": group_type,
            "courses": clause_codes,
            "text": clause.strip(),
            "connector": "OR" if has_explicit_top_or else "AND"
        })

    sorted_all_codes = sorted(list(all_codes_set))
    return sorted_all_codes, structured_groups, raw_snippet


def parse_aliases(description: str, current_code: str, valid_codes: Set[str] = None) -> Tuple[List[str], str]:
    """
    Extract course aliases, cross-listings, and mutually exclusive credit restrictions.
    """
    if not description:
        return [], ""

    alias_set = set()
    raw_texts = []

    patterns = [
        r'(?:credit\s+is\s+not\s+allowed|cannot\s+receive\s+credit|may\s+not\s+receive\s+credit|will\s+not\s+get\s+credit)\s+for\s+both\s+[^.]+',
        r'replaces\s+[^.]+',
        r'(?:students\s+)?(?:may\s+not|cannot|can\s+not|will\s+not\s+get)\s+receive\s+credit\s+for\s+both\s+[^.]+',
        r'(?:students\s+)?(?:may\s+not|cannot|can\s+not|will\s+not)\s+(?:receive\s+credit|get\s+credit)\s+for\s+this\s+course\s+if\s+they\s+have\s+taken\s+[^.]+',
        r'(?:students\s+who\s+previously\s+took\s+[^.]+\s+will\s+not\s+get\s+credit)',
        r'(?:students\s+who\s+have\s+received\s+credit\s+for\s+[^.]+\s+may\s+not\s+receive\s+credit)',
        r'also\s+offered\s+as\s+[^.]+',
        r'cross-listed\s+as\s+[^.]+',
        r'equivalent\s+course\s*:\s*[^.]+'
    ]

    for pat in patterns:
        for m in re.finditer(pat, description, re.IGNORECASE):
            match_text = m.group(0).strip()
            raw_texts.append(match_text)

            codes = extract_course_codes_from_text(match_text, valid_codes)
            for code in codes:
                if code != current_code:
                    alias_set.add(code)

    raw_snippet = " ".join(raw_texts)
    return sorted(list(alias_set)), raw_snippet


def clean_course_description(description: str, prereq_raw: str = "", alias_raw: str = "") -> str:
    """
    Remove prerequisite statements, notes, and credit restrictions from course description text.
    """
    if not description:
        return ""

    text = description.strip()

    prereq_pattern = r'(recommended background|prerequisite[s]?|pre-requisite[s]?|background)\s*[:\-].*?(?=\.\s+[A-Z]|\.\s*Students|\.\s*~Note|\.$|\n|$)'
    text = re.sub(prereq_pattern, '', text, flags=re.IGNORECASE).strip()

    restriction_patterns = [
        r'(?:students\s+)?(?:may\s+not|cannot|can\s+not|credit\s+is\s+not\s+allowed)\s+(?:receive\s+credit|allowed)\s+for\s+both\s+.*?(?=\.|\n|$)',
        r'(?:students\s+)?(?:may\s+not|cannot|can\s+not)\s+receive\s+credit\s+for\s+this\s+course\s+if\s+they\s+have\s+taken\s+.*?(?=\.|\n|$)',
        r'(?:students\s+who\s+previously\s+took\s+.*?\s+will\s+not\s+get\s+credit.*?(?=\.|\n|$))',
        r'(?:students\s+who\s+have\s+received\s+credit\s+for\s+.*?\s+may\s+not\s+receive\s+credit.*?(?=\.|\n|$))',
        r'replaces\s+.*?(?=\.|\n|$)',
        r'also\s+offered\s+as\s+.*?(?=\.|\n|$)',
        r'cross-listed\s+as\s+.*?(?=\.|\n|$)',
        r'equivalent\s+course\s*:.*?(?=\.|\n|$)'
    ]
    for pat in restriction_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE).strip()

    if prereq_raw and prereq_raw.strip() in text:
        text = text.replace(prereq_raw.strip(), '').strip()

    if alias_raw and alias_raw.strip() in text:
        text = text.replace(alias_raw.strip(), '').strip()

    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'(\.\s*){2,}', '. ', text).strip()
    text = re.sub(r'\.\s*\.+$', '.', text).strip()
    return text


# ============================================================================
# DETERMINISTIC NON-LLM FINAL SANITIZATION & INVARIANT VALIDATION LAYER
# ============================================================================

def sanitize_and_validate_course_graph(graph: Dict[str, Dict[str, Any]], verbose: bool = False) -> Dict[str, Any]:
    """
    Final deterministic non-LLM pass that guarantees:
    1. Zero Self-Prerequisites: Course X cannot be a prerequisite for itself.
    2. Strict Disjointness: Aliases / mutual credit exclusions are NOT prerequisites.
    3. Zero Self-Aliases: Course X cannot be an alias for itself.
    4. Bidirectional Alias Symmetry: If A has alias B, then B has alias A, and neither is prereq of other.
    5. Clean Structured Pruning: Removes empty prerequisite groups and invalid course codes.
    6. Returns validation summary report and enforces zero invariant violations.
    """
    dept_names = {
        n["department_code"]: n["department_name"]
        for n in graph.values()
        if n.get("department_code") and n.get("department_name")
    }

    # Pass 1: Self-Prerequisite & Self-Alias Purge + Alias-Prerequisite Separation
    for code, node in list(graph.items()):
        # Remove self-alias
        node["aliases"] = [a for a in node.get("aliases", []) if a != code]

        # Collect aliases for this node
        alias_set = set(node["aliases"])

        # Purge self from prerequisites and purge any aliases from prerequisites
        cleaned_prereqs = []
        for p in node.get("prerequisites", []):
            if p != code and p not in alias_set:
                if p not in cleaned_prereqs:
                    cleaned_prereqs.append(p)
        node["prerequisites"] = sorted(cleaned_prereqs)

        # Clean structured prerequisite groups
        cleaned_groups = []
        for grp in node.get("prerequisites_structured", []):
            filtered_courses = [
                c for c in grp.get("courses", [])
                if c != code and c not in alias_set
            ]
            if filtered_courses:
                grp_copy = dict(grp)
                grp_copy["courses"] = filtered_courses
                cleaned_groups.append(grp_copy)
        node["prerequisites_structured"] = cleaned_groups

    # Pass 2: Enforce Bidirectional Alias Symmetry & Cross-Prerequisite Purge
    for code, node in list(graph.items()):
        for alias_code in list(node["aliases"]):
            if alias_code == code:
                continue

            # Create placeholder node if alias course code is not in graph
            if alias_code not in graph:
                parts = alias_code.split(" ", 1)
                dept = parts[0] if len(parts) > 0 else ""
                num = parts[1] if len(parts) > 1 else ""
                graph[alias_code] = {
                    "course_code": alias_code,
                    "course_name": f"Course {alias_code}",
                    "department_code": dept,
                    "department_name": dept_names.get(dept, ""),
                    "course_number": num,
                    "course_description": "",
                    "min_credits": "",
                    "max_credits": "",
                    "academic_year": node.get("academic_year", "2026 - 2027 Academic Year"),
                    "terms": [],
                    "prerequisites": [],
                    "prerequisites_structured": [],
                    "raw_prerequisite_text": "",
                    "aliases": [code],
                    "raw_alias_text": f"Equivalent/Restricted with {code}",
                    "prerequisite_for": []
                }
            else:
                # Ensure symmetrical link
                if code not in graph[alias_code]["aliases"]:
                    graph[alias_code]["aliases"].append(code)
                    graph[alias_code]["aliases"].sort()

            # Ensure neither has the other in prerequisites
            if alias_code in graph[code]["prerequisites"]:
                graph[code]["prerequisites"].remove(alias_code)
            if code in graph[alias_code]["prerequisites"]:
                graph[alias_code]["prerequisites"].remove(code)

            # Clean structured groups for both
            graph[code]["prerequisites_structured"] = [
                grp for grp in graph[code].get("prerequisites_structured", [])
                if [c for c in grp.get("courses", []) if c != alias_code]
            ]
            graph[alias_code]["prerequisites_structured"] = [
                grp for grp in graph[alias_code].get("prerequisites_structured", [])
                if [c for c in grp.get("courses", []) if c != code]
            ]

    # Pass 3: Final deduplication, sorting, and invariant validation
    self_prereq_violations = 0
    alias_prereq_violations = 0
    self_alias_violations = 0

    for code, node in graph.items():
        node["prerequisites"] = sorted(list(set(node.get("prerequisites", []))))
        node["aliases"] = sorted(list(set(node.get("aliases", []))))

        if code in node["prerequisites"]:
            self_prereq_violations += 1
        if code in node["aliases"]:
            self_alias_violations += 1

        overlap = set(node["aliases"]).intersection(set(node["prerequisites"]))
        if overlap:
            alias_prereq_violations += len(overlap)

    if verbose or self_prereq_violations > 0 or alias_prereq_violations > 0:
        print("[Sanitization Pass] Validation Metrics:")
        print(f"  - Self-Prerequisite Violations: {self_prereq_violations}")
        print(f"  - Alias in Prerequisite Violations: {alias_prereq_violations}")
        print(f"  - Self-Alias Violations: {self_alias_violations}")

    assert self_prereq_violations == 0, f"Critical invariant failure: {self_prereq_violations} self-prerequisites detected!"
    assert alias_prereq_violations == 0, f"Critical invariant failure: {alias_prereq_violations} alias/prereq overlaps detected!"
    assert self_alias_violations == 0, f"Critical invariant failure: {self_alias_violations} self-aliases detected!"

    report = {
        "status": "PASSED",
        "total_nodes": len(graph),
        "courses_with_prerequisites": sum(1 for n in graph.values() if n.get("prerequisites")),
        "courses_with_aliases": sum(1 for n in graph.values() if n.get("aliases")),
        "self_prerequisite_violations": self_prereq_violations,
        "alias_prerequisite_violations": alias_prereq_violations,
        "self_alias_violations": self_alias_violations
    }
    return report


# ============================================================================
# COURSE GRAPH BUILDER
# ============================================================================

def build_course_graph(
    courses: List[Dict[str, Any]],
    extractor: Optional[Any] = None,
    verbose: bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    Build course dependency and alias graph from course dataset.
    Uses LLM extractor if provided or available, and runs the final
    deterministic non-LLM sanitization layer.
    """
    valid_codes = set(c["course_code"] for c in courses if c.get("course_code"))
    graph = {}

    for c in courses:
        code = c["course_code"]
        name = c.get("course_name", "")
        desc = c.get("course_description", "")

        if extractor:
            extraction = extractor.extract_course(code, name, desc)
            prereq_codes = extraction["prerequisites"]
            prereq_struct = extraction["prerequisites_structured"]
            prereq_raw = extraction["raw_prerequisite_text"]
            alias_codes = extraction["aliases"]
            alias_raw = extraction["raw_alias_text"]
            clean_desc = extraction["clean_description"]
        else:
            prereq_codes, prereq_struct, prereq_raw = parse_prerequisites(desc, valid_codes)
            alias_codes, alias_raw = parse_aliases(desc, code, valid_codes=None)
            clean_desc = clean_course_description(desc, prereq_raw, alias_raw)

        graph[code] = {
            "course_code": code,
            "course_name": name,
            "department_code": c.get("department_code", ""),
            "department_name": c.get("department_name", ""),
            "course_number": c.get("course_number", ""),
            "course_description": desc,
            "min_credits": c.get("min_credits", ""),
            "max_credits": c.get("max_credits", ""),
            "academic_year": c.get("academic_year", "2026 - 2027 Academic Year"),
            "terms": c.get("terms", []),
            "prerequisites": prereq_codes,
            "prerequisites_structured": prereq_struct,
            "raw_prerequisite_text": prereq_raw,
            "aliases": alias_codes,
            "raw_alias_text": alias_raw
        }

    # Save extractor cache if present
    if extractor and hasattr(extractor, "save_cache"):
        extractor.save_cache()

    # Deterministic Non-LLM Final Sanitization Pass
    sanitize_and_validate_course_graph(graph, verbose=verbose)

    return graph


def main():
    default_input = os.path.join("data", "wpi_courses.json")
    default_output = os.path.join("data", "wpi_course_dag.json")
    default_cache = os.path.join("data", ".cache_llm_prereqs.json")

    parser = argparse.ArgumentParser(
        description="Scrape/Parse course prerequisites and build course DAG (Local Gemma CPU / Ollama / HF)"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=default_input,
        help=f"Input courses JSON file (default: {default_input})"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=default_output,
        help=f"Output DAG JSON file (default: {default_output})"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=["auto", "ollama", "huggingface", "fallback"],
        help="LLM inference provider for parsing prerequisites (default: auto)"
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default="gemma:2b",
        help="Ollama model name (default: gemma:2b)"
    )
    parser.add_argument(
        "--ollama-host",
        type=str,
        default="http://localhost:11434",
        help="Ollama host endpoint (default: http://localhost:11434)"
    )
    parser.add_argument(
        "--hf-model",
        type=str,
        default="google/gemma-2b-it",
        help="HuggingFace model ID for CPU inference (default: google/gemma-2b-it)"
    )
    parser.add_argument(
        "--cache-file",
        type=str,
        default=default_cache,
        help=f"Cache file for LLM extractions (default: {default_cache})"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable LLM extraction cache"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force re-extraction of all courses, ignoring existing cache"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline deterministic fallback extractor (no LLM calls)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print status messages and sanitization metrics"
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Loading courses from {args.input}...")

    with open(args.input, "r", encoding="utf-8") as f:
        courses = json.load(f)

    # Initialize Extractor
    provider = "fallback" if args.offline else args.provider

    from llm_prerequisite_parser import LLMPrerequisiteExtractor
    extractor = LLMPrerequisiteExtractor(
        provider_name=provider,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
        hf_model=args.hf_model,
        cache_path=args.cache_file,
        use_cache=not args.no_cache,
        force_refresh=args.force_refresh
    )

    if args.verbose:
        print(f"Parsing prerequisites for {len(courses)} courses using provider: {extractor.provider.__class__.__name__}...")

    dag = build_course_graph(courses, extractor=extractor, verbose=args.verbose)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(dag, f, indent=2, ensure_ascii=False)

    if args.verbose or True:
        print(f"Successfully parsed prerequisites and created course DAG with {len(dag)} nodes.")
        print(f"Saved DAG to {args.output}")


if __name__ == "__main__":
    main()
