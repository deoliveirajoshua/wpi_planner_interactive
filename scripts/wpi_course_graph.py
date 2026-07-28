#!/usr/bin/env python3
"""
WPI Course Graph Builder (Bidirectional / Undirected Graph)

Reads data/wpi_course_dag.json (or data/wpi_courses.json), adds reverse prerequisite relationships
('prerequisite_for'), and generates data/wpi_course_graph.json.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Any

# Enable importing from scripts directory regardless of current working directory
sys.path.insert(0, os.path.dirname(__file__))
from prerequisite_scraper import build_course_graph as build_dag_graph


def build_undirected_course_graph(dag: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Transform a course DAG into a fully connected bidirectional graph by adding
    'prerequisite_for' lists to every course node.
    """
    graph = json.loads(json.dumps(dag))

    for code, node in graph.items():
        node["prerequisite_for"] = []

    dept_names = {n["department_code"]: n["department_name"] for n in dag.values() if n.get("department_code") and n.get("department_name")}

    for code, node in list(graph.items()):
        for req in node.get("prerequisites", []):
            if req not in graph:
                parts = req.split(" ", 1)
                dept = parts[0] if len(parts) > 0 else ""
                num = parts[1] if len(parts) > 1 else ""
                graph[req] = {
                    "course_code": req,
                    "course_name": f"Course {req}",
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
                    "aliases": [],
                    "raw_alias_text": "",
                    "prerequisite_for": []
                }

            if code not in graph[req]["prerequisite_for"]:
                graph[req]["prerequisite_for"].append(code)

    for code, node in graph.items():
        node["prerequisite_for"].sort()

    for code, node in list(graph.items()):
        for alias_code in node.get("aliases", []):
            if alias_code in graph:
                if code not in graph[alias_code]["aliases"]:
                    graph[alias_code]["aliases"].append(code)
                    graph[alias_code]["aliases"].sort()

    return graph


def main():
    default_input = os.path.join("data", "wpi_course_dag.json")
    default_output = os.path.join("data", "wpi_course_graph.json")

    parser = argparse.ArgumentParser(
        description="Build bidirectional course graph with 'prerequisite_for' field into data/wpi_course_graph.json"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=default_input,
        help=f"Input course DAG JSON file (default: {default_input})"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=default_output,
        help=f"Output graph JSON file (default: {default_output})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print summary statistics"
    )

    args = parser.parse_args()

    input_file = args.input
    if not os.path.exists(input_file):
        fallback = os.path.join("data", "wpi_courses.json")
        if os.path.exists(fallback):
            input_file = fallback
        elif os.path.exists("wpi_course_dag.json"):
            input_file = "wpi_course_dag.json"
        elif os.path.exists("wpi_courses.json"):
            input_file = "wpi_courses.json"

    if args.verbose:
        print(f"Loading course DAG from {input_file}...")

    with open(input_file, "r", encoding="utf-8") as f:
        dag_data = json.load(f)
        if isinstance(dag_data, list):
            dag = build_dag_graph(dag_data)
        else:
            dag = dag_data

    if args.verbose:
        print("Adding reverse prerequisite edges ('prerequisite_for')...")

    graph = build_undirected_course_graph(dag)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)

    prereq_for_count = sum(1 for node in graph.values() if node["prerequisite_for"])
    prereq_count = sum(1 for node in graph.values() if node["prerequisites"])
    alias_count = sum(1 for node in graph.values() if node["aliases"])

    if args.verbose or True:
        print(f"Successfully generated bidirectional course graph with {len(graph)} nodes.")
        print(f"  - Courses that have prerequisites: {prereq_count}")
        print(f"  - Courses that serve as prerequisites ('prerequisite_for'): {prereq_for_count}")
        print(f"  - Courses with tracked aliases / credit restrictions: {alias_count}")
        print(f"Saved graph data to {args.output}")


if __name__ == "__main__":
    main()
