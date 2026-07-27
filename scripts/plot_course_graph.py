#!/usr/bin/env python3
"""
WPI Course Graph Interactive Plotter

Generates an interactive, color-coded HTML visualization of the WPI course graph / DAG.
Color-codes nodes by department, displays prerequisite directional edges and alias links,
and enables interactive filtering, recursive tree unwinding, and node inspection.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Any


def export_custom_interactive_html(graph_data: Dict[str, Dict[str, Any]], output_filepath: str, target_dept: str = None):
    """
    Generate a standalone, rich interactive HTML visualization using Vis.js with
    recursive prerequisite tree unwinding, department legend, detail panel, and search.
    """
    if target_dept and target_dept.lower() != "all":
        target_dept_upper = target_dept.upper()
        relevant_codes = set()
        for code, node in graph_data.items():
            if node.get("department_code") == target_dept_upper:
                relevant_codes.add(code)
                relevant_codes.update(node.get("prerequisites", []))
                relevant_codes.update(node.get("prerequisite_for", []))
                relevant_codes.update(node.get("aliases", []))
        filtered_graph = {k: v for k, v in graph_data.items() if k in relevant_codes}
    else:
        filtered_graph = graph_data

    depts = sorted(list(set(node.get("department_code", "OTHER") for node in filtered_graph.values())))

    nodes_js = []
    for code, node in filtered_graph.items():
        dept = node.get("department_code", "OTHER")
        nodes_js.append({
            "id": code,
            "label": code,
            "title": f"{code} - {node.get('course_name', '')}",
            "department": dept,
            "name": node.get("course_name", ""),
            "prerequisites": node.get("prerequisites", []),
            "prerequisites_structured": node.get("prerequisites_structured", []),
            "prerequisite_for": node.get("prerequisite_for", []),
            "aliases": node.get("aliases", []),
            "description": node.get("raw_prerequisite_text", ""),
            "min_credits": node.get("min_credits", "3.0")
        })

    edges_js = []
    added_edges = set()
    for code, node in filtered_graph.items():
        for prereq in node.get("prerequisites", []):
            if prereq in filtered_graph:
                edge_key = (prereq, code, "prereq")
                if edge_key not in added_edges:
                    edges_js.append({
                        "id": f"{prereq}->{code}",
                        "from": prereq,
                        "to": code,
                        "arrows": {"to": {"enabled": True, "scaleFactor": 0.4}},
                        "color": {"color": "#cbd5e1", "highlight": "#AC2B37"},
                        "width": 1.2
                    })
                    added_edges.add(edge_key)

        for alias in node.get("aliases", []):
            if alias in filtered_graph:
                edge_key = tuple(sorted([code, alias])) + ("alias",)
                if edge_key not in added_edges:
                    edges_js.append({
                        "id": f"{code}<->{alias}",
                        "from": code,
                        "to": alias,
                        "dashes": True,
                        "color": {"color": "#94a3b8", "highlight": "#AC2B37"},
                        "width": 1
                    })
                    added_edges.add(edge_key)

    dept_options_html = "".join([f'<option value="{d}">{d}</option>' for d in depts])

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css_path = os.path.join(base_dir, "assets", "css", "styles.css")
    js_path = os.path.join(base_dir, "assets", "js", "app.js")

    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Course Visualizer</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700&display=swap" rel="stylesheet">
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
{css_content}
  </style>
</head>
<body>
  <!-- Header Bar -->
  <header id="header">
    <div class="logo-container">
      <span class="logo-badge">WPI</span>
      <h1>WPI Course Catalog Visualizer</h1>
    </div>
    <div class="controls-container">
      <div class="search-box">
        <input type="text" id="search-input" placeholder="Search course (e.g. CS 1101)..." onkeyup="handleSearchInput(event)" autocomplete="off">
        <div id="search-dropdown" class="search-dropdown"></div>
      </div>
      <select id="dept-select" class="select-control" onchange="filterDepartment(this.value)">
        <option value="ALL">All Departments</option>
        {dept_options_html}
      </select>
      <button id="physics-toggle-btn" class="btn" onclick="togglePhysics()">Physics: OFF</button>
      <button class="btn" onclick="resetView()">Reset View</button>
      <button class="btn" onclick="openHelpModal()">Help</button>
    </div>
  </header>

  <!-- Main Application Workspace -->
  <div id="main-container">
    <div class="stats-bar">
      <div class="stat-pill">Courses: <span id="stat-courses" class="num">{len(filtered_graph)}</span></div>
      <div class="stat-pill">Departments: <span id="stat-depts" class="num">{len(depts)}</span></div>
      <div class="stat-pill">Prerequisite Links: <span id="stat-links" class="num">{len(edges_js)}</span></div>
    </div>
    <div id="mynetwork"></div>
    <aside id="sidebar">
      <div class="sidebar-section">
        <div class="section-title-row">
          <div class="section-title" id="dept-courses-title">Department Courses</div>
          <button id="dept-show-all-btn" class="btn-xs" style="display: none;">Show All</button>
        </div>
        <div id="dept-courses-list" class="dept-courses-list">
          <p class="placeholder-msg">Select a department or click a course to view all courses in that department.</p>
        </div>
      </div>

      <div class="sidebar-section details-section">
        <div class="section-title">Course Details</div>
        <div id="details-panel">
          <p class="placeholder-msg">Click any course node in the graph to view prerequisites, unlocked courses, and details.</p>
        </div>
      </div>
    </aside>
  </div>

  <!-- Footer Info Bar -->
  <footer id="footer">
    <span>Interactive WPI Prerequisite Network Visualizer &bull; Generated from <a href="https://github.com/WPI-Planner/wpi_planner" target="_blank" rel="noopener">WPI Course Catalog Data</a></span>
  </footer>

  <!-- Help Modal Overlay Container -->
  <div id="help-modal-overlay" class="modal-overlay" onclick="handleModalOverlayClick(event)">
    <div class="modal-card">
      <div class="modal-header">
        <div class="modal-title">Help & Controls Guide</div>
        <button class="modal-close-btn" onclick="closeHelpModal()">&times;</button>
      </div>
      <div class="modal-body">
        <div class="modal-section">
          <div class="modal-section-title">Graph Navigation Controls</div>
          <ul class="help-list">
            <li><strong>Single Left-Click:</strong> Click any course node to highlight its prerequisite chain (Indigo) and unlocked courses (Blue) directly in the main view without hiding background courses. Single-click again to unselect.</li>
            <li><strong>Double Left-Click:</strong> Double-click any course node to enter the <strong>Isolated Focused View</strong> (hiding unrelated background nodes and auto-zooming). Click empty space to return to the full view with your selection preserved.</li>
            <li><strong>Pan View:</strong> Hold <strong>Right-Click & Drag</strong> anywhere on the canvas to move around smoothly.</li>
            <li><strong>Zoom:</strong> Scroll your mouse wheel to zoom in or out.</li>
            <li><strong>Department Filter & Show All:</strong> Select a department from the header or click <strong>Show All</strong> in the sidebar to cluster and zoom into department courses.</li>
            <li><strong>Unwind Prerequisite:</strong> In the details sidebar, click <strong>Show All (Unwind)</strong> to expand the full recursive prerequisite hierarchy tier by tier.</li>
            <li><strong>Physics Toggle:</strong> Click <strong>Physics: OFF / ON</strong> to enable smooth live graph physics with anti-collision spacing and gentle attraction.</li>
          </ul>
        </div>
        <div class="modal-section">
          <div class="modal-section-title">Color Legend Guide</div>
          <ul class="help-list">
            <li><span class="color-sample red-sample"></span> <strong>Red:</strong> Currently selected focus course.</li>
            <li><span class="color-sample indigo-sample"></span> <strong>Indigo:</strong> Prerequisites required or recommended for the selected course.</li>
            <li><span class="color-sample sky-sample"></span> <strong>Blue:</strong> Courses unlocked after completing the selected course.</li>
            <li><span class="color-sample white-sample"></span> <strong>Cream / Slate Nodes:</strong> Background courses in the full graph overview.</li>
          </ul>
        </div>
      </div>
    </div>
  </div>

  <div id="badge-tooltip" class="badge-tooltip"></div>

  <script type="text/javascript">
    window.rawEmbeddedNodes = {json.dumps(nodes_js, indent=2)};
    window.rawEmbeddedEdges = {json.dumps(edges_js, indent=2)};
  </script>
  <script type="text/javascript">
{js_content}
  </script>
</body>
</html>
"""

    out_dir = os.path.dirname(output_filepath)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(html_template)


def main():
    default_input = os.path.join("data", "wpi_course_graph.json")
    default_output = os.path.join("assets", "wpi_course_graph.html")

    parser = argparse.ArgumentParser(
        description="Plot WPI course graph / DAG into an interactive HTML visualization"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=default_input,
        help=f"Input graph JSON file (default: {default_input})"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=default_output,
        help=f"Output HTML visualization file (default: {default_output})"
    )
    parser.add_argument(
        "-d", "--dept",
        type=str,
        default="ALL",
        help="Filter by specific department abbreviation (e.g. CS, ECE, MA, or ALL)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print status messages"
    )

    args = parser.parse_args()

    input_file = args.input
    if not os.path.exists(input_file):
        fallback1 = os.path.join("data", "wpi_course_dag.json")
        fallback2 = os.path.join("data", "wpi_courses.json")
        if os.path.exists(fallback1):
            input_file = fallback1
        elif os.path.exists(fallback2):
            input_file = fallback2

    if args.verbose:
        print(f"Loading graph data from {input_file}...")

    with open(input_file, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    if args.verbose:
        print(f"Generating interactive HTML visualization ({len(graph_data)} nodes)...")

    export_custom_interactive_html(graph_data, args.output, target_dept=args.dept)

    if args.verbose or True:
        print(f"Successfully generated interactive course graph visualization: {args.output}")


if __name__ == "__main__":
    main()
