#!/usr/bin/env python3
"""
WPI Historical Course Catalog Scraper

Queries the Wayback Machine API for historical snapshots of planner.wpi.edu/new.schedb,
parses course metadata for each available academic year, and outputs year-suffixed
JSON, CSV, DAG, and Graph datasets into data/historical/.
"""

import argparse
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Enable importing from scripts directory regardless of current working directory
sys.path.insert(0, os.path.dirname(__file__))

try:
    from scraper import parse_schedb_xml, export_courses, fetch_data, USER_AGENT
    from prerequisite_scraper import build_course_graph as build_dag_graph
    from wpi_course_graph import build_undirected_course_graph
except ImportError:
    # Fallback when running directly or from root directory
    from scripts.scraper import parse_schedb_xml, export_courses, fetch_data, USER_AGENT
    from scripts.prerequisite_scraper import build_course_graph as build_dag_graph
    from scripts.wpi_course_graph import build_undirected_course_graph

CDX_API_URL = "http://web.archive.org/cdx/search/cdx?url=planner.wpi.edu/new.schedb&output=json&fl=timestamp,original,statuscode,digest&filter=statuscode:200"


import time

def fetch_cdx_snapshots(timeout: int = 30, max_retries: int = 4) -> List[Dict[str, str]]:
    """
    Query Internet Archive CDX API for available 200 OK snapshots of planner.wpi.edu/new.schedb.
    Retries automatically on HTTP 503 / 429 rate limits.
    """
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(CDX_API_URL, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP Error {resp.status} fetching Wayback CDX index")
                data = json.loads(resp.read().decode("utf-8"))

            if not data or len(data) < 2:
                return []

            header = data[0]
            records = []

            for row in data[1:]:
                rec = dict(zip(header, row))
                records.append(rec)

            return records
        except Exception as err:
            if attempt < max_retries - 1:
                wait_sec = (attempt + 1) * 3
                print(f"Wayback CDX API query failed ({err}). Retrying in {wait_sec}s...")
                time.sleep(wait_sec)
            else:
                raise

    return []


def extract_academic_year_from_xml(xml_bytes: bytes, fallback_timestamp: str = "") -> Tuple[str, str]:
    """
    Mine the actual Academic Year directly from XML content:
    1. Root <schedb generated="... Month DD, YYYY"> tag timestamp attribute.
    2. Section `part-of-term="A Term 2023"` attributes.
    3. Fallback to snapshot timestamp calculation if XML does not specify.
    """
    if xml_bytes:
        try:
            text = xml_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = str(xml_bytes)

        # 1. Check root schedb generated attribute e.g. <schedb generated="11:15 PM Oct 16, 2021"> or <schedb generated="Jul 17, 2024">
        m_gen = re.search(r'<schedb[^>]*?generated=\x22[^\x22]*?([A-Za-z]+)\s+\d{1,2},\s*(\d{4})\x22', text, re.IGNORECASE)
        if m_gen:
            month_str = m_gen.group(1).lower()
            year = int(m_gen.group(2))
            if month_str in ["may", "jun", "june", "jul", "july", "aug", "august", "sep", "september", "oct", "october", "nov", "november", "dec", "december"]:
                start_year = year
                end_year = year + 1
            else:
                start_year = year - 1
                end_year = year
            return f"{start_year}_{end_year}", f"{start_year} - {end_year} Academic Year"

        # 3. Search for section part-of-term year patterns e.g. "A Term 2023" or "C Term 2024"
        ab_years = [int(y) for y in re.findall(r'[AB]\s+Term\s+(\d{4})', text, re.IGNORECASE)]
        cd_years = [int(y) for y in re.findall(r'[CD]\s+Term\s+(\d{4})', text, re.IGNORECASE)]

        if ab_years:
            from collections import Counter
            start_year = Counter(ab_years).most_common(1)[0][0]
            end_year = start_year + 1
            return f"{start_year}_{end_year}", f"{start_year} - {end_year} Academic Year"

        if cd_years:
            from collections import Counter
            end_year = Counter(cd_years).most_common(1)[0][0]
            start_year = end_year - 1
            return f"{start_year}_{end_year}", f"{start_year} - {end_year} Academic Year"

        # 4. Search for explicit "20XX - 20YY Academic Year" pattern
        m_exp = re.search(r'(\d{4})\s*[\-\–\—]\s*(\d{4})\s+Academic\s+Year', text, re.IGNORECASE)
        if m_exp:
            y1, y2 = int(m_exp.group(1)), int(m_exp.group(2))
            return f"{y1}_{y2}", f"{y1} - {y2} Academic Year"

    return get_academic_year_suffix(fallback_timestamp)


def get_academic_year_suffix(timestamp: str) -> Tuple[str, str]:
    """
    Fallback estimate of academic year suffix from a Wayback timestamp string YYYYMMDDhhmmss
    used for preliminary CDX snapshot grouping prior to XML extraction.
    """
    if len(timestamp) < 6:
        return "unknown", "Unknown Academic Year"

    year = int(timestamp[:4])
    month = int(timestamp[4:6])

    if month >= 5:
        start_year = year
        end_year = year + 1
    else:
        start_year = year - 1
        end_year = year

    suffix = f"{start_year}_{end_year}"
    display_str = f"{start_year} - {end_year} Academic Year"
    return suffix, display_str


def select_best_snapshots(cdx_records: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """
    Group CDX records by Academic Year suffix and pick the latest timestamp snapshot per academic year.
    """
    grouped = {}

    for rec in cdx_records:
        timestamp = rec.get("timestamp", "")
        if not timestamp:
            continue

        suffix, display_str = get_academic_year_suffix(timestamp)
        rec["suffix"] = suffix
        rec["display_str"] = display_str

        # Overwrite to keep the latest timestamp per academic year
        if suffix not in grouped or timestamp > grouped[suffix]["timestamp"]:
            grouped[suffix] = rec

    return grouped


def fetch_raw_snapshot(timestamp: str, timeout: int = 45) -> bytes:
    """
    Fetch un-modified raw XML bytes for a given Wayback Machine snapshot timestamp.
    Using 'id_' flag avoids Wayback HTML toolbar injection.
    """
    raw_url = f"https://web.archive.org/web/{timestamp}id_/https://planner.wpi.edu/new.schedb"
    return fetch_data(raw_url, timeout=timeout)


def process_historical_year(
    timestamp: str,
    suffix: str,
    display_str: str,
    out_dir: str,
    verbose: bool = False
) -> Optional[Dict[str, int]]:
    """
    Fetch, parse, and generate wpi_courses, wpi_course_dag, and wpi_course_graph datasets
    for a specific historical academic year. Academic year is mined directly from XML content.
    """
    if verbose:
        print(f"\n--- Processing Academic Year {suffix} (Snapshot {timestamp}) ---")

    try:
        xml_bytes = fetch_raw_snapshot(timestamp)
    except Exception as err:
        print(f"Error fetching snapshot {timestamp} for {suffix}: {err}")
        return None

    # Mine academic year directly from the XML document content
    mined_suffix, mined_display_str = extract_academic_year_from_xml(xml_bytes, fallback_timestamp=timestamp)
    if mined_suffix != "unknown":
        suffix = mined_suffix
        display_str = mined_display_str
        if verbose:
            print(f"Mined Academic Year from XML content: {display_str} ({suffix})")

    try:
        courses = parse_schedb_xml(xml_bytes, clean_html=True, academic_year=display_str)
    except Exception as err:
        print(f"Error parsing XML for {suffix}: {err}")
        return None

    if not courses:
        print(f"No courses parsed for {suffix}")
        return None

    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, f"wpi_courses_{suffix}.json")
    csv_path = os.path.join(out_dir, f"wpi_courses_{suffix}.csv")
    dag_path = os.path.join(out_dir, f"wpi_course_dag_{suffix}.json")
    graph_path = os.path.join(out_dir, f"wpi_course_graph_{suffix}.json")

    # 1. Export courses JSON & CSV
    export_courses(courses, json_path, fmt="json")
    export_courses(courses, csv_path, fmt="csv")

    # 2. Export DAG JSON
    dag = build_dag_graph(courses)
    with open(dag_path, "w", encoding="utf-8") as f:
        json.dump(dag, f, indent=2)

    # 3. Export Bidirectional Graph JSON
    graph = build_undirected_course_graph(dag)
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

    stats = {
        "courses": len(courses),
        "dag_nodes": len(dag),
        "graph_nodes": len(graph)
    }

    if verbose:
        print(f"[{suffix}] Successfully processed:")
        print(f"  - Courses: {stats['courses']} -> {json_path}")
        print(f"  - CSV: {csv_path}")
        print(f"  - DAG: {stats['dag_nodes']} nodes -> {dag_path}")
        print(f"  - Graph: {stats['graph_nodes']} nodes -> {graph_path}")

    return stats


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_out_dir = os.path.join(base_dir, "data", "historical")

    parser = argparse.ArgumentParser(
        description="Scrape Wayback Machine for historical WPI course catalogs from planner.wpi.edu"
    )
    parser.add_argument(
        "-o", "--outdir",
        type=str,
        default=default_out_dir,
        help=f"Output directory for historical datasets (default: {default_out_dir})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print verbose execution and snapshot details"
    )
    parser.add_argument(
        "--years",
        type=str,
        nargs="+",
        help="Filter specific academic year suffixes to process (e.g. 2022_2023 2023_2024)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Query CDX index and list available snapshots without downloading"
    )

    args = parser.parse_args()

    if args.verbose:
        print(f"Querying Wayback Machine CDX API for planner.wpi.edu/new.schedb...")

    try:
        cdx_records = fetch_cdx_snapshots()
    except Exception as err:
        print(f"Error querying CDX index: {err}")
        sys.exit(1)

    if not cdx_records:
        print("No Wayback Machine snapshots found for planner.wpi.edu/new.schedb")
        sys.exit(0)

    best_snapshots = select_best_snapshots(cdx_records)
    sorted_suffixes = sorted(best_snapshots.keys())

    if args.verbose or args.dry-run:
        print(f"Found {len(cdx_records)} total CDX snapshots across {len(sorted_suffixes)} academic years:")
        for s in sorted_suffixes:
            rec = best_snapshots[s]
            print(f"  - {s}: Timestamp {rec['timestamp']} ({rec['display_str']})")

    if args.dry_run:
        print("\nDry run completed. Exiting without downloading.")
        sys.exit(0)

    if args.years:
        target_years = set(args.years)
        sorted_suffixes = [s for s in sorted_suffixes if s in target_years]
        if not sorted_suffixes:
            print(f"No matching snapshots found for requested years: {args.years}")
            sys.exit(0)

    results = {}
    for suffix in sorted_suffixes:
        rec = best_snapshots[suffix]
        res = process_historical_year(
            timestamp=rec["timestamp"],
            suffix=suffix,
            display_str=rec["display_str"],
            out_dir=args.outdir,
            verbose=args.verbose
        )
        if res:
            results[suffix] = res

    print(f"\nSuccessfully generated historical catalog datasets for {len(results)} academic years in {args.outdir}.")


if __name__ == "__main__":
    main()
