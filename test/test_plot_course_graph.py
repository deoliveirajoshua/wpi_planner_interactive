#!/usr/bin/env python3
"""
Unit tests for WPI Course Graph Plotter (plot_course_graph.py)
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from plot_course_graph import generate_department_colors, export_custom_interactive_html

SAMPLE_GRAPH = {
    "CS 1101": {
        "course_code": "CS 1101",
        "course_name": "Introduction To Program Design",
        "department_code": "CS",
        "prerequisites": [],
        "prerequisite_for": ["CS 2102"],
        "aliases": []
    },
    "CS 2102": {
        "course_code": "CS 2102",
        "course_name": "Object-Oriented Design Concepts",
        "department_code": "CS",
        "prerequisites": ["CS 1101"],
        "prerequisite_for": [],
        "aliases": []
    },
    "MA 1021": {
        "course_code": "MA 1021",
        "course_name": "Calculus I",
        "department_code": "MA",
        "prerequisites": [],
        "prerequisite_for": [],
        "aliases": []
    }
}


class TestPlotter(unittest.TestCase):

    def test_department_colors(self):
        depts = ["CS", "MA", "ECE", "AE"]
        colors = generate_department_colors(depts)
        self.assertEqual(len(colors), 4)
        for d in depts:
            self.assertTrue(colors[d].startswith("#"))

    def test_html_export(self):
        out_file = os.path.join("assets", "test_graph.html")
        try:
            export_custom_interactive_html(SAMPLE_GRAPH, out_file)
            self.assertTrue(os.path.exists(out_file))
            with open(out_file, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("CS 1101", content)
                self.assertIn("CS 2102", content)
                self.assertIn("MA 1021", content)
                self.assertIn("vis.Network", content)
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)


if __name__ == "__main__":
    unittest.main()
