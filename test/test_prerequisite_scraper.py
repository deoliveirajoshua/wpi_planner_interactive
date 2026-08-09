#!/usr/bin/env python3
"""
Unit tests for WPI Course Prerequisite & Alias Scraper and LLM Parser
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from prerequisite_scraper import (
    extract_course_codes_from_text,
    parse_prerequisites,
    parse_aliases,
    clean_category_and_units_metadata,
    clean_course_description,
    build_course_graph,
    sanitize_and_validate_course_graph,
)
from llm_prerequisite_parser import (
    build_gemma_prompt,
    parse_json_from_llm_text,
    normalize_course_code,
    LLMPrerequisiteExtractor,
    RegexFallbackProvider,
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
    },
    {
        "course_code": "BME 4607",
        "department_code": "BME",
        "department_name": "Biomedical Engineering",
        "course_number": "4607",
        "course_name": "Biotransport Laboratory: Application",
        "course_description": "Recommended Background: BME 3607, CH 1010. ~Note: Students who previously took BME 3605 will not get credit for BME 4607."
    },
    {
        "course_code": "CHE 2013",
        "department_code": "CHE",
        "department_name": "Chemical Engineering",
        "course_number": "2013",
        "course_name": "Applied Chemical Engineering Thermodynamics",
        "course_description": "Recommended background: CHE 2011 and CHE 2012.Students may not receive credit towards CHE distribution requirements for both CHE 2013 and CM 2102."
    },
    {
        "course_code": "ECE 3829",
        "department_code": "ECE",
        "department_name": "Electrical & Computer Engineering",
        "course_number": "3829",
        "course_name": "Advanced Digital System Design With FPGAs",
        "course_description": "Recommended background: ECE 2029 and ECE 2049 Students who have received credit for ECE 3810 may not receive credit for ECE 3829."
    },
    {
        "course_code": "SS 1505",
        "department_code": "SS",
        "department_name": "Social Science",
        "course_number": "1505",
        "course_name": "Games For Understanding Complexity",
        "course_description": "Recommended background: None Students who completed SS150X cannot receive credit for SS1505."
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

    def test_extract_shorthand_slashed_numbers(self):
        text = "Recommended background: CS 2102/3, CS 2301/3, or ECE 2039."
        codes = extract_course_codes_from_text(text)
        self.assertIn("CS 2102", codes)
        self.assertIn("CS 2103", codes)
        self.assertIn("CS 2301", codes)
        self.assertIn("CS 2303", codes)
        self.assertIn("ECE 2039", codes)

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

    def test_final_sanitization_no_self_prerequisites(self):
        graph = build_course_graph(SAMPLE_COURSES)
        # Verify tricky courses that previously had self-prerequisites are cleanly purged
        for tricky_code in ["BME 4607", "CHE 2013", "ECE 3829", "SS 1505"]:
            self.assertIn(tricky_code, graph)
            self.assertNotIn(tricky_code, graph[tricky_code]["prerequisites"])
            for grp in graph[tricky_code]["prerequisites_structured"]:
                self.assertNotIn(tricky_code, grp.get("courses", []))

    def test_final_sanitization_aliases_not_in_prerequisites(self):
        graph = build_course_graph(SAMPLE_COURSES)
        for code, node in graph.items():
            overlap = set(node["aliases"]).intersection(set(node["prerequisites"]))
            self.assertEqual(len(overlap), 0, f"Course {code} has aliases in prerequisites: {overlap}")
            self.assertNotIn(code, node["aliases"])
            self.assertNotIn(code, node["prerequisites"])

    def test_sanitize_and_validate_course_graph_direct(self):
        # Construct synthetic flawed graph
        flawed_graph = {
            "CS 2102": {
                "course_code": "CS 2102",
                "prerequisites": ["CS 2102", "CS 1101", "CS 2103"],
                "prerequisites_structured": [
                    {"type": "OR", "courses": ["CS 2102", "CS 1101"]},
                    {"type": "AND", "courses": ["CS 2103"]}
                ],
                "aliases": ["CS 2102", "CS 2103"],
                "department_code": "CS"
            }
        }
        report = sanitize_and_validate_course_graph(flawed_graph)
        self.assertEqual(report["status"], "PASSED")
        node = flawed_graph["CS 2102"]
        self.assertNotIn("CS 2102", node["prerequisites"])
        self.assertNotIn("CS 2102", node["aliases"])
        self.assertNotIn("CS 2103", node["prerequisites"])
        self.assertIn("CS 1101", node["prerequisites"])
        self.assertIn("CS 2103", node["aliases"])
        # Symmetrical alias placeholder created
        self.assertIn("CS 2103", flawed_graph)
        self.assertIn("CS 2102", flawed_graph["CS 2103"]["aliases"])

    def test_cs4344_complex_prerequisite_structure(self):
        desc = (
            "Recommended background: Programming skills equivalent to (CS 1004 or CS 1101 or CS 1102) "
            "and (CS 2102 or CS2103 or CS 2119); and machine learning equivalent to (DS 3010, CS 4445, or CS4342). "
            "Units: 1/3 Category: II"
        )
        codes, struct, raw = parse_prerequisites(desc)
        self.assertEqual(len(struct), 3)
        self.assertTrue(all(g["type"] == "OR" for g in struct))
        self.assertEqual(set(struct[0]["courses"]), {"CS 1004", "CS 1101", "CS 1102"})
        self.assertEqual(set(struct[1]["courses"]), {"CS 2102", "CS 2103", "CS 2119"})
        self.assertEqual(set(struct[2]["courses"]), {"DS 3010", "CS 4445", "CS 4342"})

    def test_cross_listed_twin_courses_alias_linking(self):
        courses = [
            {
                "course_code": "CS 4344",
                "department_code": "CS",
                "course_number": "4344",
                "course_name": "Natural Language Processing: From Foundations to Large Language Models",
                "course_description": "Sample description."
            },
            {
                "course_code": "DS 4344",
                "department_code": "DS",
                "course_number": "4344",
                "course_name": "Natural Language Processing: From Foundations to Large Language Models",
                "course_description": "Sample description."
            }
        ]
        graph = build_course_graph(courses)
        self.assertIn("DS 4344", graph["CS 4344"]["aliases"])
        self.assertIn("CS 4344", graph["DS 4344"]["aliases"])

    def test_cs4343_all_and_background_prerequisites(self):
        desc = (
            "Recommended background: Machine Learning (CS 4342), and knowledge of Linear Algebra "
            "(such as MA 2071) and Algorithms (such as CS 2223) Units: 1/3 Category: II"
        )
        codes, struct, raw = parse_prerequisites(desc)
        self.assertEqual(set(codes), {"CS 4342", "MA 2071", "CS 2223"})
        self.assertEqual(len(struct), 3)
        # All groups must be AND (no OR group created due to 1/3 Units fraction)
        self.assertTrue(all(g["type"] == "AND" for g in struct))

    def test_clean_category_and_units_metadata_leading(self):
        self.assertEqual(
            clean_category_and_units_metadata("Cat. IAn intensive course to introduce Arabic."),
            "An intensive course to introduce Arabic."
        )
        self.assertEqual(
            clean_category_and_units_metadata("Cat. I This course continues students exposure."),
            "This course continues students exposure."
        )
        self.assertEqual(
            clean_category_and_units_metadata("Cat. 1 This course provides students with an understanding."),
            "This course provides students with an understanding."
        )
        self.assertEqual(
            clean_category_and_units_metadata("AE 2210: Introduction to Thermal Engineering (1/3 units; Cat. I) Thermal engineering encompasses."),
            "Thermal engineering encompasses."
        )
        self.assertEqual(
            clean_category_and_units_metadata("AB 1600 Moroccan Colloquial Arabic (1/3 Unit; Cat. III) This course presents the rudiments."),
            "This course presents the rudiments."
        )
        self.assertEqual(
            clean_category_and_units_metadata("Units 1/3. Computational methods to make informed decisions."),
            "Computational methods to make informed decisions."
        )
        self.assertEqual(
            clean_category_and_units_metadata("1/3 Unit. Microcontrollers and electronic circuits for robotics."),
            "Microcontrollers and electronic circuits for robotics."
        )

    def test_clean_category_and_units_metadata_trailing(self):
        self.assertEqual(
            clean_category_and_units_metadata("Foundational topics in deep learning. Units: 1/3 Category: II"),
            "Foundational topics in deep learning."
        )
        self.assertEqual(
            clean_category_and_units_metadata("Statistical inference and modeling. Cat II"),
            "Statistical inference and modeling."
        )
        self.assertEqual(
            clean_category_and_units_metadata("Consumer behavior principles. Units: 1/3. Category: Category II"),
            "Consumer behavior principles."
        )
        self.assertEqual(
            clean_category_and_units_metadata("Fluid dynamics fundamentals. (1/3 Unit; Cat. I)"),
            "Fluid dynamics fundamentals."
        )

    def test_clean_course_description_with_category_and_units(self):
        desc = (
            "Cat. I This course introduces the object-oriented design paradigm. "
            "Recommended background: CS 1101 or CS 1102. "
            "Students cannot receive credit for both CS 2102 and CS 2103. Units: 1/3 Category: I"
        )
        p_codes, p_struct, p_raw = parse_prerequisites(desc)
        a_codes, a_raw = parse_aliases(desc, "CS 2102")
        cleaned = clean_course_description(desc, p_raw, a_raw)
        self.assertEqual(
            cleaned,
            "This course introduces the object-oriented design paradigm."
        )


class TestLLMPrerequisiteParser(unittest.TestCase):

    def test_normalize_course_code(self):
        self.assertEqual(normalize_course_code("cs 2102"), "CS 2102")
        self.assertEqual(normalize_course_code("ECE 2010"), "ECE 2010")
        self.assertEqual(normalize_course_code("ar 174x"), "AR 174X")
        self.assertIsNone(normalize_course_code("NONE"))
        self.assertIsNone(normalize_course_code("INVALID 99999"))

    def test_build_gemma_prompt(self):
        prompt = build_gemma_prompt("CS 2102", "Object-Oriented Design Concepts", "Sample desc.")
        self.assertIn("RULES AND CONVENTIONS:", prompt)
        self.assertIn("=== FEW-SHOT EXAMPLES ===", prompt)
        self.assertIn("=== TASK INPUT ===", prompt)
        self.assertIn("CS 2102", prompt)

    def test_parse_json_from_llm_text(self):
        # Raw json
        res1 = parse_json_from_llm_text('{"prerequisites": ["CS 1101"]}')
        self.assertEqual(res1.get("prerequisites"), ["CS 1101"])

        # Markdown fenced json
        markdown_text = """Here is the extracted json:
```json
{
  "prerequisites": ["MA 1021", "MA 1022"],
  "aliases": ["MA 1023"]
}
```
Hope this helps!"""
        res2 = parse_json_from_llm_text(markdown_text)
        self.assertEqual(res2.get("prerequisites"), ["MA 1021", "MA 1022"])
        self.assertEqual(res2.get("aliases"), ["MA 1023"])

    def test_llm_extractor_caching(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            cache_file = tf.name

        try:
            extractor = LLMPrerequisiteExtractor(
                provider_name="fallback",
                cache_path=cache_file,
                use_cache=True
            )
            res1 = extractor.extract_course(
                "CS 2102",
                "Object-Oriented Design Concepts",
                "Recommended background: CS 1101. Credit not allowed for CS 2102 and CS 2103."
            )
            extractor.save_cache()
            self.assertIn("CS 1101", res1["prerequisites"])

            # Reload extractor from cache
            extractor2 = LLMPrerequisiteExtractor(
                provider_name="fallback",
                cache_path=cache_file,
                use_cache=True
            )
            self.assertEqual(len(extractor2.cache), 1)
            self.assertIn("clean_description", res1)
            self.assertIn("raw_description", res1)
        finally:
            if os.path.exists(cache_file):
                os.remove(cache_file)

    def test_llm_extractor_retains_original_and_clean_description(self):
        desc = "Cat. I This is a test description. Recommended background: CS 1101. Units: 1/3 Category: II"
        extractor = LLMPrerequisiteExtractor(provider_name="fallback", use_cache=False)
        result = extractor.extract_course("CS 2102", "Object-Oriented Design", desc)
        self.assertEqual(result["raw_description"], desc)
        self.assertNotIn("Cat. I", result["clean_description"])
        self.assertNotIn("Units: 1/3 Category: II", result["clean_description"])


if __name__ == "__main__":
    unittest.main()
