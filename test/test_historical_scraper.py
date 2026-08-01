#!/usr/bin/env python3
"""
Unit tests for Historical Course Catalog Scraper (historical_scraper.py)
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from historical_scraper import (
    extract_academic_year_from_xml,
    get_academic_year_suffix,
    select_best_snapshots,
    process_historical_year
)

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<schedb generated="11:15 PM Oct 16, 2023">
  <dept abbrev="CS" name="Computer Science">
    <course number="1101" name="Introduction To Program Design" course_desc="Recommended background: none." min-credits="3.0">
      <section number="A01" part-of-term="A Term" term="202401"/>
    </course>
    <course number="2102" name="Object-Oriented Design Concepts" course_desc="Recommended background: CS 1101." min-credits="3.0">
      <section number="B01" part-of-term="B Term" term="202401"/>
    </course>
  </dept>
</schedb>
"""


class TestHistoricalScraper(unittest.TestCase):

    def test_extract_academic_year_from_xml(self):
        # XML containing part-of-term="A Term 2023" -> 2023_2024
        s1, d1 = extract_academic_year_from_xml(SAMPLE_XML)
        self.assertEqual(s1, "2023_2024")
        self.assertEqual(d1, "2023 - 2024 Academic Year")

        # Explicit string inside XML
        xml_explicit = b'<schedb title="2025 - 2026 Academic Year"></schedb>'
        s2, d2 = extract_academic_year_from_xml(xml_explicit)
        self.assertEqual(s2, "2025_2026")
        self.assertEqual(d2, "2025 - 2026 Academic Year")

    def test_academic_year_calculation(self):
        # October 2023 -> 2023_2024
        s1, d1 = get_academic_year_suffix("20231015120000")
        self.assertEqual(s1, "2023_2024")
        self.assertEqual(d1, "2023 - 2024 Academic Year")

        # March 2024 -> 2023_2024
        s2, d2 = get_academic_year_suffix("20240315120000")
        self.assertEqual(s2, "2023_2024")
        self.assertEqual(d2, "2023 - 2024 Academic Year")

        # June 2024 -> 2024_2025
        s3, d3 = get_academic_year_suffix("20240601000000")
        self.assertEqual(s3, "2024_2025")
        self.assertEqual(d3, "2024 - 2025 Academic Year")

    def test_select_best_snapshots(self):
        records = [
            {"timestamp": "20220901000000", "original": "url1"},
            {"timestamp": "20221101000000", "original": "url2"}, # Later timestamp for 2022_2023
            {"timestamp": "20230901000000", "original": "url3"}  # Timestamp for 2023_2024
        ]
        best = select_best_snapshots(records)
        self.assertIn("2022_2023", best)
        self.assertIn("2023_2024", best)
        self.assertEqual(best["2022_2023"]["timestamp"], "20221101000000")

    @patch("historical_scraper.fetch_raw_snapshot")
    def test_process_historical_year(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_XML
        out_dir = os.path.join("data", "test_historical")

        try:
            stats = process_historical_year(
                timestamp="20231015120000",
                suffix="2023_2024",
                display_str="2023 - 2024 Academic Year",
                out_dir=out_dir,
                verbose=False
            )

            self.assertIsNotNone(stats)
            self.assertEqual(stats["courses"], 2)

            json_file = os.path.join(out_dir, "wpi_courses_2023_2024.json")
            csv_file = os.path.join(out_dir, "wpi_courses_2023_2024.csv")
            dag_file = os.path.join(out_dir, "wpi_course_dag_2023_2024.json")
            graph_file = os.path.join(out_dir, "wpi_course_graph_2023_2024.json")

            self.assertTrue(os.path.exists(json_file))
            self.assertTrue(os.path.exists(csv_file))
            self.assertTrue(os.path.exists(dag_file))
            self.assertTrue(os.path.exists(graph_file))

            with open(graph_file, "r", encoding="utf-8") as f:
                graph_data = json.load(f)
                self.assertIn("CS 1101", graph_data)
                self.assertIn("CS 2102", graph_data)
                self.assertIn("CS 2102", graph_data["CS 1101"]["prerequisite_for"])
        finally:
            if os.path.exists(out_dir):
                import shutil
                shutil.rmtree(out_dir)


if __name__ == "__main__":
    unittest.main()
