#!/usr/bin/env python3
"""
Batch re-run of LLM Prerequisite & Alias Parser across all active and historical catalogs.
Updates:
- data/wpi_course_dag.json & data/wpi_course_graph.json
- data/historical/wpi_course_dag_*.json & data/historical/wpi_course_graph_*.json
- data/.cache_llm_prereqs.json
"""

import glob
import json
import os
import sys

# Add scripts directory to module path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
scripts_dir = os.path.join(base_dir, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from llm_prerequisite_parser import LLMPrerequisiteExtractor
from prerequisite_scraper import build_course_graph
from wpi_course_graph import build_undirected_course_graph


def reparse_catalog(json_path: str, dag_out: str, graph_out: str, extractor: LLMPrerequisiteExtractor):
    print(f"\n=======================================================")
    print(f"Processing Catalog: {os.path.relpath(json_path, base_dir)}")
    print(f"=======================================================")

    with open(json_path, "r", encoding="utf-8") as f:
        courses = json.load(f)

    print(f"Loaded {len(courses)} courses.")
    dag = build_course_graph(courses, extractor=extractor, verbose=False)

    with open(dag_out, "w", encoding="utf-8") as f:
        json.dump(dag, f, indent=2, ensure_ascii=False)
    print(f"-> Saved DAG: {os.path.relpath(dag_out, base_dir)} ({len(dag)} nodes)")

    graph = build_undirected_course_graph(dag)
    with open(graph_out, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print(f"-> Saved Graph: {os.path.relpath(graph_out, base_dir)} ({len(graph)} nodes)")

    # Sample statistics
    prereq_count = sum(1 for n in dag.values() if n.get("prerequisites"))
    alias_count = sum(1 for n in dag.values() if n.get("aliases"))
    print(f"Stats: {prereq_count} courses have prerequisites, {alias_count} courses have aliases/restrictions.")


def main():
    data_dir = os.path.join(base_dir, "data")
    historical_dir = os.path.join(data_dir, "historical")
    cache_path = os.path.join(data_dir, ".cache_llm_prereqs.json")

    print(f"Initializing LLM Prerequisite Extractor with force_refresh=True...")
    extractor = LLMPrerequisiteExtractor(
        provider_name="auto",
        cache_path=cache_path,
        use_cache=True,
        force_refresh=True
    )

    # 1. Main Active Catalog
    main_courses_json = os.path.join(data_dir, "wpi_courses.json")
    main_dag_json = os.path.join(data_dir, "wpi_course_dag.json")
    main_graph_json = os.path.join(data_dir, "wpi_course_graph.json")

    if os.path.exists(main_courses_json):
        reparse_catalog(main_courses_json, main_dag_json, main_graph_json, extractor)

    # 2. Historical Catalogs
    pattern = os.path.join(historical_dir, "wpi_courses_*.json")
    hist_files = sorted(glob.glob(pattern))

    for hist_json in hist_files:
        basename = os.path.basename(hist_json)
        # e.g., wpi_courses_2024_2025.json -> suffix = 2024_2025
        suffix = basename.replace("wpi_courses_", "").replace(".json", "")
        hist_dag_json = os.path.join(historical_dir, f"wpi_course_dag_{suffix}.json")
        hist_graph_json = os.path.join(historical_dir, f"wpi_course_graph_{suffix}.json")

        reparse_catalog(hist_json, hist_dag_json, hist_graph_json, extractor)

    print("\nAll catalogs successfully parsed and synchronized!")


if __name__ == "__main__":
    main()
