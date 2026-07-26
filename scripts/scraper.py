#!/usr/bin/env python3
"""
WPI Planner Course Scraper

Scrapes course codes, course names, course descriptions, and metadata 
from planner.wpi.edu and WPI course listings.
"""

import argparse
import csv
import html
import json
import os
import re
import sys
import urllib.request
from typing import Dict, List, Optional

PLANNER_SCHEDB_URL = "https://planner.wpi.edu/new.schedb"
WORKDAY_JSON_URL = "https://courselistings.wpi.edu/assets/prod-data.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 WPI-Course-Scraper/1.0"
)


def clean_text(text: str) -> str:
    """
    Sanitize HTML tags, unescape HTML entities, and normalize whitespace in text.
    """
    if not text:
        return ""

    unencoded = html.unescape(text)
    no_html = re.sub(r"<[^>]+>", " ", unencoded)
    cleaned = no_html.replace("\xa0", " ").replace("\ufffd", "")
    normalized = re.sub(r"\s+", " ", cleaned).strip()
    return normalized


def fetch_data(url: str, timeout: int = 30) -> bytes:
    """
    Fetch raw bytes from a URL with custom User-Agent header.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP error {response.status} fetching {url}")
        return response.read()


def parse_schedb_xml(xml_bytes: bytes, clean_html: bool = True) -> List[Dict[str, str]]:
    """
    Parse WPI Planner's schedb XML format into structured course records.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_bytes)
    courses = []
    seen_codes = set()

    for dept_elem in root.findall("dept"):
        dept_abbrev = dept_elem.attrib.get("abbrev", "").strip()
        dept_name = dept_elem.attrib.get("name", "").strip()

        for course_elem in dept_elem.findall("course"):
            number = course_elem.attrib.get("number", "").strip()
            name = course_elem.attrib.get("name", "").strip()
            desc_raw = course_elem.attrib.get("course_desc", "").strip()
            min_credits = course_elem.attrib.get("min-credits", "").strip()
            max_credits = course_elem.attrib.get("max-credits", "").strip()

            code = f"{dept_abbrev} {number}".strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)

            description = clean_text(desc_raw) if clean_html else desc_raw

            courses.append({
                "course_code": code,
                "department_code": dept_abbrev,
                "department_name": dept_name,
                "course_number": number,
                "course_name": name,
                "course_description": description,
                "min_credits": min_credits,
                "max_credits": max_credits
            })

    return courses


def parse_workday_json(json_bytes: bytes, clean_html: bool = True) -> List[Dict[str, str]]:
    """
    Parse WPI Course Listings Workday JSON format into structured course records.
    """
    data = json.loads(json_bytes.decode("utf-8"))
    entries = data.get("Report_Entry", [])
    courses_dict = {}

    for entry in entries:
        title = entry.get("Course_Title", "").strip()
        desc_raw = entry.get("Course_Description", "").strip()
        subject = entry.get("Subject", "").strip()
        academic_level = entry.get("Academic_Level", "").strip()
        credits = entry.get("Credits", "").strip()

        if " - " in title:
            code, name = title.split(" - ", 1)
        else:
            code, name = title, ""

        code = code.strip()
        name = name.strip()
        if not code:
            continue

        description = clean_text(desc_raw) if clean_html else desc_raw

        if code not in courses_dict or (not courses_dict[code]["course_description"] and description):
            parts = code.split(" ", 1)
            dept_abbrev = parts[0] if len(parts) > 0 else ""
            course_num = parts[1] if len(parts) > 1 else ""

            courses_dict[code] = {
                "course_code": code,
                "department_code": dept_abbrev,
                "department_name": subject,
                "course_number": course_num,
                "course_name": name,
                "course_description": description,
                "academic_level": academic_level,
                "credits": credits
            }

    return list(courses_dict.values())


def scrape_courses(source: str = "planner", clean_html: bool = True, verbose: bool = False) -> List[Dict[str, str]]:
    """
    Scrape WPI course records from the specified data source ('planner' or 'workday').
    """
    if source == "planner":
        if verbose:
            print(f"Fetching WPI Planner database from {PLANNER_SCHEDB_URL}...")
        raw_bytes = fetch_data(PLANNER_SCHEDB_URL)
        if verbose:
            print("Parsing XML course records...")
        return parse_schedb_xml(raw_bytes, clean_html=clean_html)
    elif source in ("workday", "courselistings"):
        if verbose:
            print(f"Fetching Workday course listings JSON from {WORKDAY_JSON_URL}...")
        raw_bytes = fetch_data(WORKDAY_JSON_URL)
        if verbose:
            print("Parsing JSON course records...")
        return parse_workday_json(raw_bytes, clean_html=clean_html)
    else:
        raise ValueError(f"Unknown source: '{source}'. Choose 'planner' or 'workday'.")


def export_courses(courses: List[Dict[str, str]], filepath: str, fmt: str = "json") -> None:
    """
    Export scraped course list to JSON or CSV file.
    Creates parent directories if necessary.
    """
    out_dir = os.path.dirname(filepath)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    fmt = fmt.lower()
    if fmt == "json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(courses, f, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        if not courses:
            return
        fieldnames = list(courses[0].keys())
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(courses)
    else:
        raise ValueError(f"Unsupported format: '{fmt}'. Choose 'json' or 'csv'.")


def main():
    default_output = os.path.join("data", "wpi_courses.json")
    parser = argparse.ArgumentParser(
        description="Scrape course codes, names, and descriptions from planner.wpi.edu"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=default_output,
        help=f"Output filepath (default: {default_output})"
    )
    parser.add_argument(
        "-f", "--format",
        type=str,
        choices=["json", "csv"],
        default=None,
        help="Export format (json or csv, inferred from extension if omitted)"
    )
    parser.add_argument(
        "-s", "--source",
        type=str,
        choices=["planner", "workday"],
        default="planner",
        help="Data source: 'planner' (planner.wpi.edu XML) or 'workday' (courselistings JSON)"
    )
    parser.add_argument(
        "--raw-html",
        action="store_true",
        help="Keep raw HTML in course descriptions without cleaning"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print progress and stats"
    )

    args = parser.parse_args()

    fmt = args.format
    if not fmt:
        if args.output.endswith(".csv"):
            fmt = "csv"
        else:
            fmt = "json"

    try:
        courses = scrape_courses(
            source=args.source,
            clean_html=not args.raw_html,
            verbose=args.verbose
        )
        export_courses(courses, args.output, fmt=fmt)

        if args.verbose or True:
            print(f"Successfully scraped {len(courses)} courses from WPI {args.source.capitalize()}.")
            print(f"Saved dataset to {args.output} ({fmt.upper()} format).")

    except Exception as err:
        print(f"Error scraping courses: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
