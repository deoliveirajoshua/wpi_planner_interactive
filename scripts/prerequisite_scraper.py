#!/usr/bin/env python3
"""
WPI Course Prerequisite & Alias Scraper / Parser

Parses course descriptions from planner.wpi.edu / Workday JSON to extract:
1. Prerequisite course dependencies (with structured AND/OR logic)
2. Alias & cross-listed relationships (e.g. PY/RE 1731, CS/ECE 2039)
3. Mutually exclusive credit restrictions (e.g. "Credit not allowed for both...")
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Set, Tuple, Any

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
    Extract course codes (e.g. CS 1101, PY/RE 1731, MA 1021/1022) from raw text snippet.
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

    # Handle slashed number pairs like MA 1021/1022 or PH 1110 / 1111
    for m in re.finditer(r'\b([A-Z]{2,4})\s*(\d{4}[A-Z]?)\s*/\s*(\d{4}[A-Z]?)\b', text):
        d, n1, n2 = m.groups()
        if d in KNOWN_DEPTS:
            for num in (n1, n2):
                code = f"{d} {num}"
                if not valid_codes or code in valid_codes:
                    found.append(code)

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

    prereq_pattern = r'(recommended background|prerequisite[s]?|pre-requisite[s]?|background)\s*[:\-]\s*(.*?)(?=\.\s+[A-Z]|\.$|\n|$)'
    m = re.search(prereq_pattern, description, re.IGNORECASE)

    if not m:
        return [], [], ""

    raw_snippet = m.group(0).strip()
    body_text = m.group(2).strip()

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
        r'(?:credit\s+is\s+not\s+allowed|cannot\s+receive\s+credit|may\s+not\s+receive\s+credit)\s+for\s+both\s+[^.]+',
        r'replaces\s+[^.]+',
        r'(?:students\s+)?(?:may\s+not|cannot|can\s+not)\s+receive\s+credit\s+for\s+both\s+[^.]+',
        r'(?:students\s+)?(?:may\s+not|cannot|can\s+not)\s+receive\s+credit\s+for\s+this\s+course\s+if\s+they\s+have\s+taken\s+[^.]+',
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


def build_course_graph(courses: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Build course dependency and alias graph from course dataset.
    Enforces alias symmetry across courses.
    """
    valid_codes = set(c["course_code"] for c in courses if c.get("course_code"))

    graph = {}

    for c in courses:
        code = c["course_code"]
        desc = c.get("course_description", "")

        prereq_codes, prereq_struct, prereq_raw = parse_prerequisites(desc, valid_codes)
        alias_codes, alias_raw = parse_aliases(desc, code, valid_codes=None)

        graph[code] = {
            "course_code": code,
            "course_name": c.get("course_name", ""),
            "department_code": c.get("department_code", ""),
            "department_name": c.get("department_name", ""),
            "course_number": c.get("course_number", ""),
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

    dept_names = {c["department_code"]: c["department_name"] for c in courses if c.get("department_code") and c.get("department_name")}

    for code, node in list(graph.items()):
        for alias_code in node["aliases"]:
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
            elif code not in graph[alias_code]["aliases"]:
                graph[alias_code]["aliases"].append(code)
                graph[alias_code]["aliases"].sort()

    return graph


def main():
    default_input = os.path.join("data", "wpi_courses.json")
    default_output = os.path.join("data", "wpi_course_dag.json")

    parser = argparse.ArgumentParser(
        description="Scrape/Parse course prerequisites and build course DAG"
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
        "-v", "--verbose",
        action="store_true",
        help="Print status messages"
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Loading courses from {args.input}...")

    with open(args.input, "r", encoding="utf-8") as f:
        courses = json.load(f)

    if args.verbose:
        print(f"Parsing prerequisites for {len(courses)} courses...")

    dag = build_course_graph(courses)

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
