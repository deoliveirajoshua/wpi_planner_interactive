#!/usr/bin/env python3
"""
Unit tests for WPI Course Graph Builder (wpi_course_graph.py)
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from wpi_course_graph import build_undirected_course_graph

SAMPLE_DAG = {
    "CS 1101": {
        "course_code": "CS 1101",
        "course_name": "Introduction To Program Design",
        "academic_year": "2026 - 2027 Academic Year",
        "terms": ["A", "C"],
        "prerequisites": [],
        "aliases": []
    },
    "CS 2102": {
        "course_code": "CS 2102",
        "course_name": "Object-Oriented Design Concepts",
        "academic_year": "2026 - 2027 Academic Year",
        "terms": ["B", "D"],
        "prerequisites": ["CS 1101"],
        "aliases": ["CS 2103"]
    },
    "CS 2103": {
        "course_code": "CS 2103",
        "course_name": "Accelerated Object-Oriented Design Concepts",
        "academic_year": "2026 - 2027 Academic Year",
        "terms": ["A"],
        "prerequisites": ["CS 1101"],
        "aliases": []
    }
}


class TestCourseGraph(unittest.TestCase):

    def test_prerequisite_for_reverse_edges(self):
        graph = build_undirected_course_graph(SAMPLE_DAG)

        self.assertIn("CS 2102", graph["CS 1101"]["prerequisite_for"])
        self.assertIn("CS 2103", graph["CS 1101"]["prerequisite_for"])

        self.assertEqual(graph["CS 2102"]["prerequisites"], ["CS 1101"])

        self.assertIn("CS 2103", graph["CS 2102"]["aliases"])
        self.assertIn("CS 2102", graph["CS 2103"]["aliases"])

        self.assertEqual(graph["CS 1101"]["academic_year"], "2026 - 2027 Academic Year")
        self.assertEqual(graph["CS 1101"]["terms"], ["A", "C"])
        self.assertEqual(graph["CS 2102"]["terms"], ["B", "D"])


if __name__ == "__main__":
    unittest.main()
