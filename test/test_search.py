#!/usr/bin/env python3
"""
Unit tests for Course Search, Space-Insensitive Matching, and Fuzzy Typo Tolerance.
"""

import json
import os
import re
import sys
import unittest

def levenshtein_distance(a, b):
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    if abs(len(a) - len(b)) > 2: return 999
    dp = [[0]*(len(a)+1) for _ in range(len(b)+1)]
    for j in range(len(a)+1): dp[0][j] = j
    for i in range(len(b)+1): dp[i][0] = i
    for i in range(1, len(b)+1):
        for j in range(1, len(a)+1):
            cost = 0 if b[i-1] == a[j-1] else 1
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost)
    return dp[len(b)][len(a)]

def normalize_search_str(s):
    return re.sub(r'[^A-Z0-9]', '', (s or '').upper())

def fuzzy_word_match(query_word, target_word):
    qw = (query_word or '').upper()
    tw = (target_word or '').upper()
    if not qw or not tw: return 0.0
    if qw == tw: return 1.0
    if tw.startswith(qw) or qw in tw: return 0.9
    if len(qw) >= 3 and len(tw) >= 3:
        if levenshtein_distance(qw, tw) <= 1: return 0.85
        if len(tw) >= len(qw) and levenshtein_distance(qw, tw[:len(qw)]) <= 1: return 0.8
        if len(qw) >= 6 and len(tw) >= 6 and levenshtein_distance(qw, tw) <= 2: return 0.75
    return 0.0

def search_course_catalog(query, graph_data):
    if not query or not graph_data: return []
    q_raw = query.upper().strip()
    q_norm = normalize_search_str(q_raw)
    if len(q_norm) < 2 and len(q_raw) < 2: return []
    
    q_words = [w for w in re.split(r'[^A-Z0-9]+', q_raw) if len(w) >= 2]
    scored = []
    
    for code, node in graph_data.items():
        c_code = (node.get('course_code') or code).upper().strip()
        c_name = (node.get('course_name') or '').upper().strip()
        c_norm = normalize_search_str(c_code)
        
        score = 0
        if c_code == q_raw or (len(q_norm) >= 2 and c_norm == q_norm):
            score = 1000
        elif c_code.startswith(q_raw) or (len(q_norm) >= 2 and c_norm.startswith(q_norm)):
            score = 800 + max(0, 10 - len(c_norm))
        elif q_raw in c_code or (len(q_norm) >= 2 and q_norm in c_norm):
            score = 700
        elif len(q_norm) >= 3 and levenshtein_distance(c_norm, q_norm) == 1:
            score = 650
        elif len(q_norm) >= 3 and len(c_norm) >= len(q_norm) and levenshtein_distance(c_norm[:len(q_norm)], q_norm) == 1:
            score = 600
        elif q_raw in c_name:
            score = 500
        elif q_words and c_name:
            name_words = [w for w in re.split(r'[^A-Z0-9]+', c_name) if len(w) >= 2]
            word_scores = [max([fuzzy_word_match(qw, nw) for nw in name_words], default=0.0) for qw in q_words]
            if word_scores and min(word_scores) >= 0.75:
                avg = sum(word_scores) / len(word_scores)
                score = 350 + int(avg * 100)
            elif word_scores and max(word_scores) >= 0.8:
                score = 150 + int(max(word_scores) * 100)
        
        if score > 0:
            scored.append({'score': score, 'course_code': c_code, 'course_name': c_name})
            
    scored.sort(key=lambda x: (-x['score'], len(x['course_code']), x['course_code']))
    return scored[:8]


SAMPLE_COURSES = {
    "MA 1020": {"course_code": "MA 1020", "course_name": "Calculus I With Preliminary Topics"},
    "MA 1021": {"course_code": "MA 1021", "course_name": "Calculus I"},
    "MA 1022": {"course_code": "MA 1022", "course_name": "Calculus II"},
    "CS 2102": {"course_code": "CS 2102", "course_name": "Object-Oriented Design Concepts"},
    "CS 2103": {"course_code": "CS 2103", "course_name": "Accelerated Object-Oriented Design Concepts"},
    "ECE 2010": {"course_code": "ECE 2010", "course_name": "Introduction To Electrical And Computer Engineering"},
    "DS 3010": {"course_code": "DS 3010", "course_name": "Data Science III: Computational Methods"}
}

class TestCourseSearch(unittest.TestCase):

    def test_spaceless_course_code_exact(self):
        results = search_course_catalog("MA1020", SAMPLE_COURSES)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["course_code"], "MA 1020")
        self.assertEqual(results[0]["score"], 1000)

    def test_spaceless_course_code_prefix(self):
        results = search_course_catalog("MA102", SAMPLE_COURSES)
        matched_codes = [r["course_code"] for r in results]
        self.assertIn("MA 1020", matched_codes)
        self.assertIn("MA 1021", matched_codes)
        self.assertIn("MA 1022", matched_codes)

    def test_1_char_typo_on_course_code(self):
        # Letter 'O' instead of '0'
        results = search_course_catalog("MA102O", SAMPLE_COURSES)
        matched_codes = [r["course_code"] for r in results]
        self.assertIn("MA 1020", matched_codes)

        # Missing 'S' in 'CS 2102' -> 'C2102'
        results = search_course_catalog("C2102", SAMPLE_COURSES)
        self.assertEqual(results[0]["course_code"], "CS 2102")

        # Extra 'S' in 'CS 2102' -> 'CSS 2102'
        results = search_course_catalog("CSS 2102", SAMPLE_COURSES)
        self.assertEqual(results[0]["course_code"], "CS 2102")

    def test_title_fuzzy_typo(self):
        # Typo 'calclus' for 'Calculus'
        results = search_course_catalog("calclus", SAMPLE_COURSES)
        matched_codes = [r["course_code"] for r in results]
        self.assertIn("MA 1020", matched_codes)
        self.assertIn("MA 1021", matched_codes)

        # Typo 'desgn' for 'Design'
        results = search_course_catalog("desgn", SAMPLE_COURSES)
        matched_codes = [r["course_code"] for r in results]
        self.assertIn("CS 2102", matched_codes)


if __name__ == "__main__":
    unittest.main()
