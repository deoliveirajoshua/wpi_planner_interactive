#!/usr/bin/env python3
"""
WPI Course Prerequisite & Alias LLM Parser (Local Inference - Gemma CPU / Ollama / HuggingFace)

Translates raw course descriptions into structured prerequisite DAGs and alias relationships
using local CPU inference (Ollama or Hugging Face Transformers) with structured few-shot prompting
and persistent caching.
"""

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Set, Tuple

# Known WPI academic departments for validation and normalization
KNOWN_DEPTS = {
    "AB", "ACC", "AE", "AM", "AR", "AREN", "AS", "BB", "BCB", "BME", "BUS",
    "CE", "CH", "CHE", "CN", "CS", "DS", "ECE", "ECON", "EDU", "EN", "ENV",
    "ER", "ES", "ET", "FIN", "FP", "FY", "GE", "GN", "GOV", "HI", "HU", "ID",
    "IGS", "IMGD", "ISE", "MA", "ME", "MFE", "MIS", "ML", "MME", "MTE", "MU",
    "NE", "OIE", "OJL", "OR", "PH", "PSY", "PY", "RE", "RBE", "SD", "SEL",
    "SP", "SS", "STS", "SYS", "TH", "WR"
}

# ============================================================================
# FEW-SHOT PROMPT SPECIFICATION FOR LOCAL GEMMA CPU INFERENCE
# ============================================================================

SYSTEM_INSTRUCTION = """You are an academic course catalog parser specialized in Worcester Polytechnic Institute (WPI) curriculum data.
Your task is to analyze a given course code and its raw course description, then extract all prerequisite requirements and alias/mutual-credit exclusions into a strictly structured JSON format.

RULES AND CONVENTIONS:
1. Prerequisites:
   - Identify explicit prerequisites and recommended background courses (e.g. "Recommended background:", "Prerequisites:", "Prior knowledge in...").
   - Group them with logical relationships: "AND" (all required) or "OR" (alternatives/options).
   - Expand shorthand notations:
     * "CS 2102/3" -> "CS 2102", "CS 2103"
     * "MA 1021/1022" -> "MA 1021", "MA 1022"
     * "CS 1101, 2102, and 2301" -> "CS 1101", "CS 2102", "CS 2301"
     * "PY/RE 1731" -> "PY 1731", "RE 1731"
   - Phrases like "None", "No prerequisites", or "No background required" mean prerequisites is an empty list [].

2. Aliases and Mutual Credit Restrictions:
   - Identify cross-listed courses and credit restrictions (e.g., "Students cannot receive credit for both...", "Credit not allowed for both...", "Also offered as...", "Cross-listed as...", "Replaces...").
   - These are ALIASES / MUTUAL EXCLUSIONS, NOT prerequisites.

3. Strict Invariants:
   - A course CANNOT be a prerequisite for itself.
   - An alias CANNOT be listed as a prerequisite.
   - Do NOT include degrees, high school courses, or generic concepts as course codes. Course codes MUST be in standard "DEPT NUM" format (e.g., "CS 2102", "PH 1110", "AR 174X").

4. Output Schema:
   Return ONLY valid JSON matching this exact structure:
   {
     "prerequisites": ["DEPT NUM", ...],
     "prerequisites_structured": [
       {
         "type": "AND" or "OR",
         "courses": ["DEPT NUM", ...],
         "text": "original text snippet of this clause",
         "connector": "AND" or "OR"
       }
     ],
     "raw_prerequisite_text": "extracted snippet containing prerequisite/background statements",
     "aliases": ["DEPT NUM", ...],
     "raw_alias_text": "extracted snippet containing alias/credit restriction statements",
     "clean_description": "course description with prerequisite and credit restriction statements removed"
   }
"""

FEW_SHOT_EXAMPLES = [
    {
        "course_code": "CS 2102",
        "course_name": "Object-Oriented Design Concepts",
        "course_description": "Cat. I This course introduces students to the object-oriented design and programming paradigm. Recommended background: CS 1101 or CS 1102 or equivalent. Students cannot receive credit for both CS 2102 and CS 2103.",
        "expected_output": {
            "prerequisites": ["CS 1101", "CS 1102"],
            "prerequisites_structured": [
                {
                    "type": "OR",
                    "courses": ["CS 1101", "CS 1102"],
                    "text": "CS 1101 or CS 1102 or equivalent",
                    "connector": "AND"
                }
            ],
            "raw_prerequisite_text": "Recommended background: CS 1101 or CS 1102 or equivalent.",
            "aliases": ["CS 2103"],
            "raw_alias_text": "Students cannot receive credit for both CS 2102 and CS 2103.",
            "clean_description": "Cat. I This course introduces students to the object-oriented design and programming paradigm."
        }
    },
    {
        "course_code": "RBE 2020",
        "course_name": "Embedded Systems for Robotics",
        "course_description": "1/3 Unit. Microcontrollers and electronic circuits for robotic systems management and design. Credit is not permitted for both RBE 2020 and ECE 2049, regardless of major. Recommended Background: RBE 1001; fundamentals of electronics, such as found in ECE 2010; and programming experience, such as covered in CS 2119, CS 2102/3, CS 2301/3, or ECE 2039.",
        "expected_output": {
            "prerequisites": ["CS 2102", "CS 2103", "CS 2119", "CS 2301", "CS 2303", "ECE 2010", "ECE 2039", "RBE 1001"],
            "prerequisites_structured": [
                {
                    "type": "AND",
                    "courses": ["RBE 1001"],
                    "text": "RBE 1001",
                    "connector": "AND"
                },
                {
                    "type": "AND",
                    "courses": ["ECE 2010"],
                    "text": "fundamentals of electronics, such as found in ECE 2010",
                    "connector": "AND"
                },
                {
                    "type": "OR",
                    "courses": ["CS 2119", "CS 2102", "CS 2103", "CS 2301", "CS 2303", "ECE 2039"],
                    "text": "programming experience, such as covered in CS 2119, CS 2102/3, CS 2301/3, or ECE 2039",
                    "connector": "AND"
                }
            ],
            "raw_prerequisite_text": "Recommended Background: RBE 1001; fundamentals of electronics, such as found in ECE 2010; and programming experience, such as covered in CS 2119, CS 2102/3, CS 2301/3, or ECE 2039.",
            "aliases": ["ECE 2049"],
            "raw_alias_text": "Credit is not permitted for both RBE 2020 and ECE 2049, regardless of major.",
            "clean_description": "1/3 Unit. Microcontrollers and electronic circuits for robotic systems management and design."
        }
    },
    {
        "course_code": "ECON 1110",
        "course_name": "Introductory Microeconomics",
        "course_description": "Cat. I The course focuses upon the implications of reliance upon markets for the allocation of resources in a society. There are no prerequisites for the course.",
        "expected_output": {
            "prerequisites": [],
            "prerequisites_structured": [],
            "raw_prerequisite_text": "There are no prerequisites for the course.",
            "aliases": [],
            "raw_alias_text": "",
            "clean_description": "Cat. I The course focuses upon the implications of reliance upon markets for the allocation of resources in a society."
        }
    },
    {
        "course_code": "AE 3703",
        "course_name": "Introduction to Control",
        "course_description": "Cat. I Analysis and design of control systems. Recommended background: ordinary differential equations (MA 2051), dynamics (ES 2503). Also offered as ME 3703. Note: Students who previously took AE 3703 will not get credit.",
        "expected_output": {
            "prerequisites": ["ES 2503", "MA 2051"],
            "prerequisites_structured": [
                {
                    "type": "AND",
                    "courses": ["MA 2051"],
                    "text": "ordinary differential equations (MA 2051)",
                    "connector": "AND"
                },
                {
                    "type": "AND",
                    "courses": ["ES 2503"],
                    "text": "dynamics (ES 2503)",
                    "connector": "AND"
                }
            ],
            "raw_prerequisite_text": "Recommended background: ordinary differential equations (MA 2051), dynamics (ES 2503).",
            "aliases": ["ME 3703"],
            "raw_alias_text": "Also offered as ME 3703. Note: Students who previously took AE 3703 will not get credit.",
            "clean_description": "Cat. I Analysis and design of control systems."
        }
    }
]


def build_gemma_prompt(course_code: str, course_name: str, course_description: str) -> str:
    """
    Format prompt with task instructions, JSON schema, and few-shot examples for Gemma.
    """
    prompt = f"{SYSTEM_INSTRUCTION}\n\n=== FEW-SHOT EXAMPLES ===\n"
    for i, ex in enumerate(FEW_SHOT_EXAMPLES, 1):
        prompt += f"\n--- Example {i} ---\n"
        prompt += f"Input Course Code: {ex['course_code']}\n"
        prompt += f"Input Course Name: {ex['course_name']}\n"
        prompt += f"Input Description: {ex['course_description']}\n"
        prompt += f"Output JSON:\n{json.dumps(ex['expected_output'], indent=2)}\n"

    prompt += "\n=== TASK INPUT ===\n"
    prompt += f"Input Course Code: {course_code}\n"
    prompt += f"Input Course Name: {course_name}\n"
    prompt += f"Input Description: {course_description}\n"
    prompt += "Output JSON:\n"
    return prompt


# ============================================================================
# LOCAL INFERENCE PROVIDERS (OLLAMA / HUGGINGFACE / FALLBACK)
# ============================================================================

class BaseLLMProvider:
    """Base interface for prerequisite extraction providers."""
    def extract(self, course_code: str, course_name: str, description: str) -> Dict[str, Any]:
        raise NotImplementedError


class OllamaLocalProvider(BaseLLMProvider):
    """
    Local CPU/GPU inference via Ollama REST API (default model: gemma:2b).
    Zero heavy Python dependencies required.
    """
    def __init__(self, model: str = "gemma:2b", host: str = "http://localhost:11434", timeout: int = 45):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def extract(self, course_code: str, course_name: str, description: str) -> Dict[str, Any]:
        prompt = build_gemma_prompt(course_code, course_name, description)
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
                "num_predict": 512,
                "top_p": 0.95
            }
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Ollama HTTP {resp.status}")
            res_body = json.loads(resp.read().decode("utf-8"))
            raw_response = res_body.get("response", "")
            return parse_json_from_llm_text(raw_response)


class HuggingFaceLocalProvider(BaseLLMProvider):
    """
    Local CPU inference via Hugging Face Transformers pipeline (e.g. google/gemma-2b-it).
    """
    def __init__(self, model_id: str = "google/gemma-2b-it", max_new_tokens: int = 512):
        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        self._pipeline = None

    def _init_pipeline(self):
        if self._pipeline is None:
            try:
                import torch
                from transformers import pipeline
                print(f"[HF Local] Loading {self.model_id} on CPU...")
                self._pipeline = pipeline(
                    "text-generation",
                    model=self.model_id,
                    model_kwargs={"torch_dtype": torch.float32},
                    device="cpu"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to initialize HuggingFace pipeline for {self.model_id}: {e}")

    def extract(self, course_code: str, course_name: str, description: str) -> Dict[str, Any]:
        self._init_pipeline()
        prompt = build_gemma_prompt(course_code, course_name, description)
        outputs = self._pipeline(
            prompt,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            temperature=0.0,
            return_full_text=False
        )
        generated_text = outputs[0]["generated_text"] if outputs else ""
        return parse_json_from_llm_text(generated_text)


class RegexFallbackProvider(BaseLLMProvider):
    """
    Enhanced deterministic rule-based extractor for offline execution and test environments.
    """
    def extract(self, course_code: str, course_name: str, description: str) -> Dict[str, Any]:
        from prerequisite_scraper import (
            extract_course_codes_from_text,
            parse_prerequisites,
            parse_aliases,
            clean_course_description
        )
        prereq_codes, prereq_struct, prereq_raw = parse_prerequisites(description)
        alias_codes, alias_raw = parse_aliases(description, course_code)
        clean_desc = clean_course_description(description, prereq_raw, alias_raw)

        return {
            "prerequisites": prereq_codes,
            "prerequisites_structured": prereq_struct,
            "raw_prerequisite_text": prereq_raw,
            "aliases": alias_codes,
            "raw_alias_text": alias_raw,
            "clean_description": clean_desc
        }


# ============================================================================
# RESPONSE PARSER & NORMALIZATION UTILITIES
# ============================================================================

def parse_json_from_llm_text(text: str) -> Dict[str, Any]:
    """
    Extract valid JSON from LLM output, handling markdown blocks or surrounding text.
    """
    if not text:
        return {}

    text = text.strip()

    # If wrapped in markdown code fence ```json ... ```
    fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    # Search for outermost matching braces { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = text[first_brace:last_brace + 1]
        try:
            return json.loads(json_str)
        except Exception:
            pass

    try:
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"Could not parse valid JSON from LLM output: {e}\nRaw output: {text[:200]}")


def normalize_course_code(code: str) -> Optional[str]:
    """
    Normalize course code to standard 'DEPT NUM' format (e.g. 'CS 2102', 'MA 1021', 'AR 174X').
    Returns None if the token is not a valid course code.
    """
    if not code or not isinstance(code, str):
        return None

    cleaned = re.sub(r'[^A-Za-z0-9\s/]', '', code).strip()
    m = re.match(r'^([A-Za-z]{2,4})\s*(\d{3,4}[A-Za-z]?)$', cleaned)
    if m:
        dept = m.group(1).upper()
        num = m.group(2).upper()
        if dept in KNOWN_DEPTS:
            return f"{dept} {num}"
    return None


# ============================================================================
# LLM PREREQUISITE EXTRACTOR WITH PERSISTENT CACHING & BATCHING
# ============================================================================

class LLMPrerequisiteExtractor:
    """
    High-level orchestrator for course prerequisite extraction with:
    - Multi-provider fallback (Ollama -> HuggingFace -> Enhanced Regex)
    - Persistent content-hash caching to eliminate redundant local inference
    - Clean schema normalization
    """
    def __init__(
        self,
        provider_name: str = "auto",
        ollama_model: str = "gemma:2b",
        ollama_host: str = "http://localhost:11434",
        hf_model: str = "google/gemma-2b-it",
        cache_path: str = os.path.join("data", ".cache_llm_prereqs.json"),
        use_cache: bool = True,
        force_refresh: bool = False
    ):
        self.provider_name = provider_name
        self.ollama_model = ollama_model
        self.ollama_host = ollama_host
        self.hf_model = hf_model
        self.cache_path = cache_path
        self.use_cache = use_cache
        self.force_refresh = force_refresh
        self.cache: Dict[str, Any] = {}

        if self.use_cache and not self.force_refresh:
            self._load_cache()

        self.provider = self._select_provider()

    def _select_provider(self) -> BaseLLMProvider:
        if self.provider_name == "ollama":
            return OllamaLocalProvider(model=self.ollama_model, host=self.ollama_host)
        elif self.provider_name == "huggingface":
            return HuggingFaceLocalProvider(model_id=self.hf_model)
        elif self.provider_name == "fallback":
            return RegexFallbackProvider()
        elif self.provider_name == "auto":
            # Test if Ollama is running locally
            try:
                test_req = urllib.request.Request(f"{self.ollama_host.rstrip('/')}/api/tags")
                with urllib.request.urlopen(test_req, timeout=1.5) as r:
                    if r.status == 200:
                        print(f"[LLM Parser] Local Ollama detected at {self.ollama_host}. Using model: {self.ollama_model}")
                        return OllamaLocalProvider(model=self.ollama_model, host=self.ollama_host)
            except Exception:
                pass

            # Fall back to enhanced regex provider
            return RegexFallbackProvider()
        else:
            return RegexFallbackProvider()

    def _get_cache_key(self, course_code: str, description: str) -> str:
        content = f"{course_code}::{description.strip()}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _load_cache(self):
        if os.path.exists(self.cache_path) and os.path.getsize(self.cache_path) > 0:
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load LLM cache ({e}). Starting fresh.", file=sys.stderr)
                self.cache = {}

    def save_cache(self):
        if not self.use_cache:
            return
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, indent=2, ensure_ascii=False)

    def extract_course(self, course_code: str, course_name: str, description: str) -> Dict[str, Any]:
        """
        Extract prerequisites and aliases for a single course, utilizing cache when available.
        """
        cache_key = self._get_cache_key(course_code, description)
        if self.use_cache and not self.force_refresh and cache_key in self.cache:
            return self.cache[cache_key]

        try:
            result = self.provider.extract(course_code, course_name, description)
            if not isinstance(result, dict):
                raise ValueError("Provider output must be a dictionary")
        except Exception as err:
            # Fall back smoothly to regex
            fallback = RegexFallbackProvider().extract(course_code, course_name, description)
            result = fallback

        # Standardize structure
        normalized_prereqs = []
        for p in result.get("prerequisites", []):
            norm = normalize_course_code(p)
            if norm and norm not in normalized_prereqs:
                normalized_prereqs.append(norm)

        normalized_aliases = []
        for a in result.get("aliases", []):
            norm = normalize_course_code(a)
            if norm and norm not in normalized_aliases:
                normalized_aliases.append(norm)

        structured = []
        for grp in result.get("prerequisites_structured", []):
            grp_courses = []
            for c in grp.get("courses", []):
                norm = normalize_course_code(c)
                if norm and norm not in grp_courses:
                    grp_courses.append(norm)
            if grp_courses:
                structured.append({
                    "type": "OR" if grp.get("type", "").upper() == "OR" else "AND",
                    "courses": grp_courses,
                    "text": grp.get("text", "").strip(),
                    "connector": "OR" if grp.get("connector", "").upper() == "OR" else "AND"
                })

        entry = {
            "prerequisites": sorted(normalized_prereqs),
            "prerequisites_structured": structured,
            "raw_prerequisite_text": result.get("raw_prerequisite_text", "").strip(),
            "aliases": sorted(normalized_aliases),
            "raw_alias_text": result.get("raw_alias_text", "").strip(),
            "clean_description": result.get("clean_description", "").strip() or description.strip()
        }

        if self.use_cache:
            self.cache[cache_key] = entry

        return entry


def main():
    import argparse
    from prerequisite_scraper import build_course_graph

    default_input = os.path.join("data", "wpi_courses.json")
    default_output = os.path.join("data", "wpi_course_dag.json")
    default_cache = os.path.join("data", ".cache_llm_prereqs.json")

    parser = argparse.ArgumentParser(
        description="WPI Course Prerequisite LLM Parser (Local Gemma CPU / Ollama / HF)"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=default_input,
        help=f"Input courses JSON file (default: {default_input})"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=default_output,
        help=f"Output DAG JSON file (default: {default_output})"
    )
    parser.add_argument(
        "-c", "--course",
        type=str,
        default=None,
        help="Test parser on a single course code (e.g. 'CS 2102' or 'RBE 2020')"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=["auto", "ollama", "huggingface", "fallback"],
        help="LLM inference provider (default: auto)"
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default="gemma:2b",
        help="Ollama model name (default: gemma:2b)"
    )
    parser.add_argument(
        "--ollama-host",
        type=str,
        default="http://localhost:11434",
        help="Ollama host endpoint (default: http://localhost:11434)"
    )
    parser.add_argument(
        "--hf-model",
        type=str,
        default="google/gemma-2b-it",
        help="HuggingFace model ID for CPU inference (default: google/gemma-2b-it)"
    )
    parser.add_argument(
        "--cache-file",
        type=str,
        default=default_cache,
        help=f"Cache file path (default: {default_cache})"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable LLM extraction cache"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force re-extraction ignoring cache"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=True,
        help="Print verbose status and metrics (default: True)"
    )

    args = parser.parse_args()

    extractor = LLMPrerequisiteExtractor(
        provider_name=args.provider,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
        hf_model=args.hf_model,
        cache_path=args.cache_file,
        use_cache=not args.no_cache,
        force_refresh=args.force_refresh
    )

    if not os.path.exists(args.input):
        print(f"Error: Input file {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        courses = json.load(f)

    if args.course:
        target = args.course.upper().strip()
        matched = [c for c in courses if c.get("course_code", "").upper() == target]
        if not matched:
            print(f"Course {target} not found in {args.input}", file=sys.stderr)
            sys.exit(1)

        c = matched[0]
        print(f"\n=======================================================")
        print(f"Parsing Course: {c['course_code']} - {c.get('course_name', '')}")
        print(f"Provider: {extractor.provider.__class__.__name__}")
        print(f"=======================================================")
        print(f"Raw Description:\n{c.get('course_description', '')}\n")
        res = extractor.extract_course(c["course_code"], c.get("course_name", ""), c.get("course_description", ""))
        print("Extracted Structured Result:")
        print(json.dumps(res, indent=2))
        return

    print(f"Loaded {len(courses)} courses from {args.input}")
    print(f"Running LLM Extraction Pipeline with provider: {extractor.provider.__class__.__name__}...")

    dag = build_course_graph(courses, extractor=extractor, verbose=args.verbose)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(dag, f, indent=2, ensure_ascii=False)

    print(f"\nSuccessfully generated course DAG with {len(dag)} nodes.")
    print(f"Saved DAG to {args.output}")


if __name__ == "__main__":
    main()

