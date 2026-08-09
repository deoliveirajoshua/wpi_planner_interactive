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
            "course_description": node.get("course_description", ""),
            "raw_prerequisite_text": node.get("raw_prerequisite_text", ""),
            "raw_alias_text": node.get("raw_alias_text", ""),
            "description": node.get("raw_prerequisite_text", ""),
            "min_credits": node.get("min_credits", "3.0"),
            "academic_year": node.get("academic_year", "2026 - 2027 Academic Year"),
            "terms": node.get("terms", [])
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

    historical_dir = os.path.join(base_dir, "data", "historical")
    historical_graphs_js = {}

    years_suffixes = ["2021_2022", "2022_2023", "2023_2024", "2024_2025", "2025_2026", "2026_2027"]
    for ys in years_suffixes:
        hist_path = os.path.join(historical_dir, f"wpi_course_graph_{ys}.json")
        if not os.path.exists(hist_path) and ys == "2026_2027":
            hist_path = os.path.join(base_dir, "data", "wpi_course_graph.json")

        if os.path.exists(hist_path):
            with open(hist_path, "r", encoding="utf-8") as f:
                h_graph = json.load(f)

            h_nodes = []
            for c_code, h_node in h_graph.items():
                h_nodes.append({
                    "id": c_code,
                    "label": c_code,
                    "title": f"{c_code} - {h_node.get('course_name', '')}",
                    "department": h_node.get("department_code", "OTHER"),
                    "name": h_node.get("course_name", ""),
                    "prerequisites": h_node.get("prerequisites", []),
                    "prerequisites_structured": h_node.get("prerequisites_structured", []),
                    "prerequisite_for": h_node.get("prerequisite_for", []),
                    "aliases": h_node.get("aliases", []),
                    "course_description": h_node.get("course_description", ""),
                    "raw_prerequisite_text": h_node.get("raw_prerequisite_text", ""),
                    "raw_alias_text": h_node.get("raw_alias_text", ""),
                    "description": h_node.get("raw_prerequisite_text", ""),
                    "min_credits": h_node.get("min_credits", "3.0"),
                    "academic_year": h_node.get("academic_year", f"{ys.replace('_', ' - ')} Academic Year"),
                    "terms": h_node.get("terms", [])
                })
            historical_graphs_js[ys] = h_nodes

    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WPI Course Planner & Catalog Visualizer</title>
  <meta name="description" content="Interactive course planner and prerequisite network visualizer for Worcester Polytechnic Institute (WPI). Explore course offerings, unwind prerequisite chains, and inspect course details.">
  <meta name="keywords" content="WPI, Worcester Polytechnic Institute, WPI Course Planner, WPI Course Catalog, WPI Prerequisites, Course Visualizer, WPI Schedule, Degree Planning">
  <meta property="og:title" content="WPI Course Planner & Catalog Visualizer">
  <meta property="og:description" content="Interactive prerequisite network visualizer for Worcester Polytechnic Institute (WPI) courses.">
  <meta property="og:type" content="website">
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
    <div class="brand">
      <div class="brand-icon">W</div>
      <div class="brand-title">
        <h1>Course Planner & Catalog Visualizer</h1>
        <p>Worcester Polytechnic Institute</p>
      </div>
      <select id="academic-year-select" class="academic-year-select" onchange="changeAcademicYear(this.value)" aria-label="Select Academic Year" title="Select Academic Year Catalog">
        <option value="2026_2027" selected> 2026 - 2027 Academic Year </option>
        <option value="2025_2026"> 2025 - 2026 Academic Year </option>
        <option value="2024_2025"> 2024 - 2025 Academic Year </option>
        <option value="2023_2024"> 2023 - 2024 Academic Year </option>
        <option value="2022_2023"> 2022 - 2023 Academic Year </option>
        <option value="2021_2022"> 2021 - 2022 Academic Year </option>
      </select>
    </div>
    <div class="controls-container">
      <div class="search-box">
        <input type="text" id="search-input" placeholder="Search for a course (e.g. MA 1022)..." onkeyup="handleSearchInput(event)" autocomplete="off">
        <div id="search-dropdown" class="search-dropdown"></div>
      </div>
      <button id="mobile-menu-btn" class="mobile-menu-btn" onclick="toggleMobileMenu()" aria-label="Toggle Mobile Controls Menu">
        <span></span><span></span><span></span>
      </button>
      <div id="toolbar-right-group" class="toolbar-right-group">
        <button id="physics-toggle-btn" class="btn" onclick="togglePhysics()">Animation: OFF</button>
        <button class="btn" onclick="resetView()">Reset View</button>
        <button class="btn" onclick="openHelpModal()">Help</button>
      </div>
    </div>
  </header>

  <!-- Main Application Workspace -->
  <div id="main-container">
    <div class="stats-bar">
      <div class="stat-pill">Courses: <span id="stat-courses" class="num">{len(filtered_graph)}</span></div>
      <div class="stat-pill">Departments & Programs: <span id="stat-depts" class="num">{len(depts)}</span></div>
      <div class="stat-pill">Prerequisite Links: <span id="stat-links" class="num">{len(edges_js)}</span></div>
    </div>
    <div id="controls-legend-widget" class="controls-legend-widget">
      <div class="legend-header" onclick="toggleControlsLegend()">
        <div class="legend-title">
          Controls & Legend
        </div>
        <button id="legend-toggle-btn" class="legend-toggle-btn" aria-label="Toggle Legend" title="Collapse/Expand Legend">
          ▼
        </button>
      </div>
      <div id="legend-content" class="legend-content">
        <div class="legend-content-inner">
          <div class="legend-group">
            <div class="group-title">Graph Node Colors</div>
            <div class="legend-items-grid">
              <div class="legend-item"><span class="color-sample red-sample"></span> <span>Selected</span></div>
              <div class="legend-item"><span class="color-sample indigo-sample"></span> <span>Prerequisites</span></div>
              <div class="legend-item"><span class="color-sample sky-sample"></span> <span>Unlocks</span></div>
              <div class="legend-item"><span class="color-sample white-sample"></span> <span>All Others</span></div>
            </div>
          </div>
          <div class="legend-group">
            <div class="group-title">Canvas Controls</div>
            <ul class="controls-list">
              <li><span class="control-key">Left Click</span> Highlight chain</li>
              <li><span class="control-key">Double Click</span> Isolate view</li>
              <li><span class="control-key">Right Drag</span> Pan canvas</li>
              <li><span class="control-key">Scroll Wheel</span> Zoom in / out</li>
            </ul>
          </div>
          <div class="legend-group keyboard-shortcuts-group">
            <div class="group-title">Keyboard Shortcuts</div>
            <ul class="controls-list">
              <li><span class="control-key">Esc</span> Reset view</li>
              <li><span class="control-key">P</span> Toggle animation</li>
              <li><span class="control-key">Space</span> Highlight / Isolate</li>
              <li><span class="control-key">U</span> Unwind prereqs</li>
              <li><span class="control-key">?</span> Help modal</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
    <div id="mynetwork"></div>

    <!-- Mobile Drawer Overlay Backdrop -->
    <div id="mobile-drawer-overlay" class="mobile-drawer-overlay" onclick="closeMobileDrawer()"></div>

    <!-- Right/Bottom Sidebar Drawer -->
    <aside id="sidebar">
      <div class="mobile-drawer-handle-bar" onclick="toggleMobileDrawer()">
        <div class="drawer-drag-pill"></div>
        <div class="mobile-drawer-title">Course Details & List</div>
        <button class="mobile-drawer-close-btn" onclick="closeMobileDrawer(event)" aria-label="Close Drawer">&times;</button>
      </div>

      <div class="sidebar-section">
        <div class="section-title-row">
          <select id="dept-select" class="dept-select sidebar-dept-select" onchange="filterDepartment(this.value)" aria-label="Filter by Department" title="Filter Graph by Department">
            <option value="ALL">All Departments and Programs</option>
            {dept_options_html}
          </select>
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

    <!-- Mobile Floating Action Button (FAB) -->
    <button id="mobile-fab-details" class="mobile-fab-btn" onclick="toggleMobileDrawer()">
      <span id="mobile-fab-icon">📋</span> <span id="mobile-fab-label">Course Details & List</span>
    </button>
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
            <li><strong>Animation Toggle:</strong> Click <strong>Animation: OFF / ON</strong> to enable smooth live graph physics with anti-collision spacing and gentle attraction.</li>
          </ul>
        </div>
        <div class="modal-section">
          <div class="modal-section-title">Keyboard Shortcuts</div>
          <ul class="help-list">
            <li><strong>Escape:</strong> Reset graph view, filters, search, or course selection.</li>
            <li><strong>P:</strong> Toggle live graph animation / physics simulation ON or OFF.</li>
            <li><strong>Space:</strong> Toggle between <strong>Highlighted</strong> and <strong>Isolated</strong> course view.</li>
            <li><strong>U:</strong> Toggle recursive prerequisite unwinding (Show All Prereqs).</li>
            <li><strong>?:</strong> Open this Help & Controls guide.</li>
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
    window.rawHistoricalGraphs = {json.dumps(historical_graphs_js, indent=2)};
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
