#!/usr/bin/env python3
"""
Unit tests for WPI Course Prerequisite & Alias Scraper
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from prerequisite_scraper import (
    extract_course_codes_from_text,
    parse_prerequisites,
    parse_aliases,
    build_course_graph,
)

SAMPLE_COURSES = [
    {
        "course_code": "CS 1101",
        "department_code": "CS",
        "department_name": "Computer Science",
        "course_number": "1101",
        "course_name": "Introduction To Program Design",
        "course_description": "Introductory programming course. Recommended background: None."
    },
    {
        "course_code": "CS 2102",
        "department_code": "CS",
        "department_name": "Computer Science",
        "course_number": "2102",
        "course_name": "Object-Oriented Design Concepts",
        "course_description": "Recommended background: CS 1101 or CS 1102. Students cannot receive credit for both CS 2102 and CS 2103."
    },
    {
        "course_code": "CS 2103",
        "department_code": "CS",
        "department_name": "Computer Science",
        "course_number": "2103",
        "course_name": "Accelerated Object-Oriented Design Concepts",
        "course_description": "Recommended background: CS 1101 or CS 1102."
    },
    {
        "course_code": "AE 3703",
        "department_code": "AE",
        "department_name": "Aerospace Engineering",
        "course_number": "3703",
        "course_name": "Introduction to Control",
        "course_description": "Recommended background: ordinary differential equations (MA 2051), dynamics (ES 2503). Also offered as ME 3703."
    },
    {
        "course_code": "ME 3703",
        "department_code": "ME",
        "department_name": "Mechanical Engineering",
        "course_number": "3703",
        "course_name": "Introduction to Control",
        "course_description": "Recommended background: MA 2051, ES 2503."
    }
]


class TestPrerequisiteScraper(unittest.TestCase):

    def test_extract_course_codes(self):
        text1 = "Recommended background: (MA 1021, 1022, or 1024), mechanics (PH 1110, PH 1111)."
        codes1 = extract_course_codes_from_text(text1)
        self.assertIn("MA 1021", codes1)
        self.assertIn("MA 1022", codes1)
        self.assertIn("MA 1024", codes1)
        self.assertIn("PH 1110", codes1)
        self.assertIn("PH 1111", codes1)

        text2 = "Also offered as AE/ME 3703 or AE 3713."
        codes2 = extract_course_codes_from_text(text2)
        self.assertIn("AE 3703", codes2)
        self.assertIn("ME 3703", codes2)
        self.assertIn("AE 3713", codes2)

        text3 = "PH 1120 / 1121 or equivalent"
        codes3 = extract_course_codes_from_text(text3)
        self.assertIn("PH 1120", codes3)
        self.assertIn("PH 1121", codes3)

    def test_parse_prerequisites_or_clause(self):
        desc = "Recommended background: CS 1101 or CS 1102; MA 1021."
        codes, struct, raw = parse_prerequisites(desc)
        self.assertIn("CS 1101", codes)
        self.assertIn("CS 1102", codes)
        self.assertIn("MA 1021", codes)
        self.assertTrue(any(group["type"] == "OR" for group in struct))

    def test_parse_aliases(self):
        desc = "Students cannot receive credit for both BUS 2060 and ACC 2060."
        aliases, raw = parse_aliases(desc, "BUS 2060")
        self.assertIn("ACC 2060", aliases)
        self.assertNotIn("BUS 2060", aliases)

    def test_build_course_graph_symmetry(self):
        graph = build_course_graph(SAMPLE_COURSES)
        self.assertIn("CS 2103", graph["CS 2102"]["aliases"])
        self.assertIn("CS 2102", graph["CS 2103"]["aliases"])
        self.assertIn("ME 3703", graph["AE 3703"]["aliases"])
        self.assertIn("AE 3703", graph["ME 3703"]["aliases"])


if __name__ == "__main__":
    unittest.main()
