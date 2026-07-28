#!/usr/bin/env python3
"""
Unit tests for WPI Planner Course Scraper
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from scraper import (
    clean_text,
    parse_schedb_xml,
    parse_workday_json,
    scrape_courses,
    export_courses,
)

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<schedb generated="1:30 PM Jul 26, 2026">
  <dept abbrev="CS" name="Computer Science">
    <course number="1101" name="Introduction To Program Design" course_desc="&lt;p&gt;Cat. I This course provides an introduction to computer programming.&lt;/p&gt;" min-credits="3.0" max-credits="3.0">
      <section number="A01" part-of-term="A Term"/>
      <section number="C01" part-of-term="C Term"/>
    </course>
    <course number="2102" name="Object-Oriented Design Concepts" course_desc="Cat. I Object-oriented concepts and techniques." min-credits="3.0" max-credits="3.0">
      <section number="B01" part-of-term="B Term"/>
    </course>
  </dept>
  <dept abbrev="ECE" name="Electrical &amp; Computer Engineering">
    <course number="2010" name="Introduction to Electrical and Computer Engineering" course_desc="Introductory course for ECE." min-credits="3.0" max-credits="3.0"/>
  </dept>
</schedb>
"""

SAMPLE_JSON = b"""{
  "Report_Entry": [
    {
      "Course_Title": "CS 1101 - Introduction To Program Design",
      "Course_Description": "<p>Cat. I Introductory programming.</p>",
      "Subject": "Computer Science",
      "Academic_Level": "Undergraduate",
      "Credits": "3",
      "Offering_Period": "2026 Fall A Term"
    },
    {
      "Course_Title": "MA 1021 - Calculus I",
      "Course_Description": "First calculus course.",
      "Subject": "Mathematical Sciences",
      "Academic_Level": "Undergraduate",
      "Credits": "3",
      "Offering_Period": "2027 Spring C Term"
    }
  ]
}
"""


class TestScraper(unittest.TestCase):

    def test_clean_text(self):
        html_input = "<p>Cat. I&nbsp;An intensive course to introduce Arabic.&amp;nbsp; closed to native speakers.</p>"
        cleaned = clean_text(html_input)
        self.assertNotIn("<p>", cleaned)
        self.assertNotIn("</p>", cleaned)
        self.assertIn("Cat. I An intensive course", cleaned)

    def test_parse_schedb_xml(self):
        courses = parse_schedb_xml(SAMPLE_XML, clean_html=True)
        self.assertEqual(len(courses), 3)

        cs1101 = courses[0]
        self.assertEqual(cs1101["course_code"], "CS 1101")
        self.assertEqual(cs1101["department_code"], "CS")
        self.assertEqual(cs1101["department_name"], "Computer Science")
        self.assertEqual(cs1101["course_number"], "1101")
        self.assertEqual(cs1101["course_name"], "Introduction To Program Design")
        self.assertEqual(
            cs1101["course_description"],
            "Cat. I This course provides an introduction to computer programming."
        )
        self.assertEqual(cs1101["academic_year"], "2026 - 2027 Academic Year")
        self.assertEqual(cs1101["terms"], ["A", "C"])

    def test_parse_workday_json(self):
        courses = parse_workday_json(SAMPLE_JSON, clean_html=True)
        self.assertEqual(len(courses), 2)
        cs1101 = courses[0]
        self.assertEqual(cs1101["course_code"], "CS 1101")
        self.assertEqual(cs1101["course_name"], "Introduction To Program Design")
        self.assertEqual(cs1101["course_description"], "Cat. I Introductory programming.")
        self.assertEqual(cs1101["academic_year"], "2026 - 2027 Academic Year")
        self.assertEqual(cs1101["terms"], ["A"])

    def test_export_json_and_csv(self):
        courses = parse_schedb_xml(SAMPLE_XML, clean_html=True)

        json_file = os.path.join("data", "test_output.json")
        csv_file = os.path.join("data", "test_output.csv")

        try:
            export_courses(courses, json_file, fmt="json")
            self.assertTrue(os.path.exists(json_file))
            with open(json_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                self.assertEqual(len(loaded), 3)

            export_courses(courses, csv_file, fmt="csv")
            self.assertTrue(os.path.exists(csv_file))
        finally:
            if os.path.exists(json_file):
                os.remove(json_file)
            if os.path.exists(csv_file):
                os.remove(csv_file)

    def test_live_scrape_planner(self):
        courses = scrape_courses(source="planner", clean_html=True, verbose=False)
        self.assertGreater(len(courses), 1000)
        codes = [c["course_code"] for c in courses]
        self.assertIn("CS 1101", codes)
        self.assertIn("MA 1021", codes)


if __name__ == "__main__":
    unittest.main()
