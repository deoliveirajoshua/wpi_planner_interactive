#!/usr/bin/env python3
"""
WPI Course Graph Interactive Plotter

Generates an interactive, color-coded HTML visualization of the WPI course graph / DAG.
Color-codes nodes by department, displays prerequisite directional edges and alias links,
and enables interactive filtering, right-click anchoring, recursive tree unwinding, and node inspection.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Any


def export_custom_interactive_html(graph_data: Dict[str, Dict[str, Any]], output_filepath: str, target_dept: str = None):
    """
    Generate a standalone, rich interactive HTML visualization using Vis.js with right-click anchoring,
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
    legend_items_html = "".join([
        f'<div class="legend-item" onclick="filterDepartment(\'{d}\')">'
        f'<span class="legend-dot"></span>'
        f'<span>{d}</span></div>'
        for d in depts
    ])

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WPI Course Dependency Graph & Planner</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700&display=swap" rel="stylesheet">
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    :root {{
      --bg-main: #f4f1ea;
      --bg-card: #fcfbfa;
      --bg-sidebar: #ffffff;
      --border-color: #e2ddd3;
      --border-hover: #cbd5e1;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #64748b;
      --wpi-crimson: #AC2B37;
      --wpi-crimson-hover: #8B222C;
      --wpi-crimson-light: rgba(172, 43, 55, 0.08);
      --anchor-gold: #d97706;
      --anchor-gold-bg: #fffbeb;
      --anchor-gold-border: #fde68a;
      --badge-indigo-bg: #e0e7ff;
      --badge-indigo-text: #4338ca;
      --badge-indigo-border: #c7d2fe;
      --badge-sky-bg: #e0f2fe;
      --badge-sky-text: #0284c7;
      --badge-sky-border: #bae6fd;
      --badge-amber-bg: #fef3c7;
      --badge-amber-text: #92400e;
      --badge-amber-border: #fde68a;
      --sidebar-width: 380px;
      --header-height: 60px;
      --footer-height: 40px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background-color: var(--bg-main); color: var(--text-primary); height: 100vh; overflow: hidden; display: flex; flex-direction: column; }}
    #header {{ height: var(--header-height); background: var(--bg-card); border-bottom: 1px solid var(--border-color); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; z-index: 100; flex-shrink: 0; }}
    .brand {{ display: flex; align-items: center; gap: 12px; }}
    .brand-icon {{ width: 34px; height: 34px; background: var(--wpi-crimson); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1.1rem; color: #ffffff; box-shadow: 0 2px 4px rgba(172, 43, 55, 0.2); }}
    .brand-title h1 {{ font-family: 'Outfit', sans-serif; font-size: 1.15rem; font-weight: 700; color: var(--text-primary); letter-spacing: -0.01em; }}
    .brand-title p {{ font-size: 0.72rem; color: var(--wpi-crimson); font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }}
    .toolbar {{ display: flex; align-items: center; gap: 12px; }}
    .search-box {{ position: relative; width: 260px; }}
    .search-box input {{ width: 100%; padding: 7px 12px; background: var(--bg-main); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; font-weight: 500; outline: none; }}
    .search-box input:focus {{ border-color: var(--wpi-crimson); background: #ffffff; box-shadow: 0 0 0 3px var(--wpi-crimson-light); }}
    .search-dropdown {{ position: absolute; top: calc(100% + 4px); left: 0; right: 0; background: #ffffff; border: 1px solid var(--border-color); border-radius: 6px; box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12); z-index: 200; max-height: 280px; overflow-y: auto; display: none; }}
    .search-item {{ padding: 8px 12px; font-size: 0.825rem; cursor: pointer; border-bottom: 1px solid var(--border-color); color: var(--text-primary); transition: background 0.1s ease; }}
    .search-item:last-child {{ border-bottom: none; }}
    .search-item:hover, .search-item.active {{ background: var(--wpi-crimson-light); color: var(--wpi-crimson); font-weight: 600; }}
    .select-control {{ padding: 7px 12px; background: var(--bg-main); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; font-weight: 500; outline: none; cursor: pointer; }}
    .btn {{ padding: 7px 14px; border-radius: 6px; font-size: 0.85rem; font-weight: 600; cursor: pointer; border: 1px solid var(--border-color); background: var(--bg-main); color: var(--text-primary); transition: all 0.15s ease; }}
    .btn:hover {{ background: #e5e1d8; border-color: var(--border-hover); }}
    .btn-xs {{ padding: 3px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 700; cursor: pointer; border: 1px solid var(--wpi-crimson); background: #ffffff; color: var(--wpi-crimson); transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 4px; }}
    .btn-xs:hover, .btn-xs.active {{ background: var(--wpi-crimson); color: #ffffff; }}
    .btn-anchor {{ border-color: var(--anchor-gold); color: var(--anchor-gold); }}
    .btn-anchor:hover, .btn-anchor.active {{ background: var(--anchor-gold); color: #ffffff; }}
    #main-container {{ display: flex; flex: 1; height: calc(100vh - var(--header-height) - var(--footer-height)); min-height: 0; position: relative; overflow: hidden; }}
    #mynetwork {{ flex: 1; height: 100%; background: #f4f1ea; }}
    .stats-bar {{ position: absolute; top: 16px; left: 16px; display: flex; align-items: center; gap: 10px; z-index: 10; }}
    .stat-pill {{ background: #ffffff; border: 1px solid var(--border-color); border-radius: 20px; padding: 5px 14px; font-size: 0.78rem; color: var(--text-secondary); font-weight: 600; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04); }}
    .stat-pill .num {{ font-weight: 700; color: var(--wpi-crimson); }}
    .anchored-bar {{ display: flex; align-items: center; gap: 6px; background: #ffffff; border: 1px solid var(--anchor-gold-border); border-radius: 20px; padding: 4px 12px; font-size: 0.75rem; color: var(--anchor-gold); font-weight: 700; box-shadow: 0 2px 6px rgba(217, 119, 6, 0.15); }}
    .anchor-pill {{ background: var(--anchor-gold-bg); border: 1px solid var(--anchor-gold-border); color: var(--anchor-gold); padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; transition: all 0.15s ease; }}
    .anchor-pill:hover {{ background: var(--anchor-gold); color: #ffffff; }}
    #sidebar {{ width: var(--sidebar-width); height: 100%; min-height: 0; background: var(--bg-sidebar); border-left: 1px solid var(--border-color); display: flex; flex-direction: column; overflow: hidden; }}
    .sidebar-section {{ padding: 18px; border-bottom: 1px solid var(--border-color); flex-shrink: 0; }}
    .sidebar-section.details-section {{ flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; border-bottom: none; padding-bottom: 0; }}
    .section-title {{ font-family: 'Outfit', sans-serif; font-size: 0.85rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10px; flex-shrink: 0; }}
    .legend-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; max-height: 130px; overflow-y: auto; padding-right: 4px; }}
    .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 0.78rem; font-weight: 500; padding: 4px 6px; border-radius: 4px; cursor: pointer; color: var(--text-secondary); transition: all 0.15s ease; }}
    .legend-item:hover {{ background: var(--wpi-crimson-light); color: var(--wpi-crimson); }}
    .legend-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #64748b; }}
    #details-panel {{ flex: 1; min-height: 0; overflow-y: auto; padding: 0 0 18px 0; }}
    .placeholder-msg {{ color: var(--text-muted); font-size: 0.85rem; text-align: center; margin-top: 40px; line-height: 1.5; }}
    .course-card-header {{ margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid var(--border-color); }}
    .course-header-top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }}
    .course-code-tag {{ display: inline-block; background: var(--wpi-crimson); color: #ffffff; padding: 4px 10px; border-radius: 4px; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1rem; }}
    .course-code-tag.anchored {{ background: var(--anchor-gold); }}
    .course-title-text {{ font-size: 1.15rem; font-weight: 700; line-height: 1.3; color: var(--text-primary); }}
    .meta-row {{ display: flex; gap: 16px; margin-top: 8px; font-size: 0.825rem; color: var(--text-secondary); }}
    .detail-block {{ margin-top: 16px; }}
    .detail-block-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }}
    .detail-block-label {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; }}
    .badge-list {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
    .badge {{ padding: 4px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 600; cursor: pointer; transition: all 0.15s ease; border: 1px solid transparent; display: inline-flex; align-items: center; gap: 4px; position: relative; }}
    .badge-prereq {{ background: var(--badge-indigo-bg); color: var(--badge-indigo-text); border-color: var(--badge-indigo-border); }}
    .badge-unlock {{ background: var(--badge-sky-bg); color: var(--badge-sky-text); border-color: var(--badge-sky-border); }}
    .badge-alias {{ background: var(--badge-amber-bg); color: var(--badge-amber-text); border-color: var(--badge-amber-border); }}
    .badge:hover {{ transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0, 0, 0, 0.12); }}
    .depth-tier-block {{ margin-top: 8px; padding: 6px 8px; background: var(--bg-main); border-radius: 6px; border: 1px solid var(--border-color); }}
    .depth-tier-title {{ font-size: 0.7rem; font-weight: 700; color: var(--wpi-crimson); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }}
    .prereq-group-box {{ background: #ffffff; border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 10px; margin-bottom: 4px; }}
    .prereq-group-box.or-group {{ border-left: 3px solid var(--badge-indigo-text); background: #f8fafc; }}
    .prereq-group-title {{ font-size: 0.68rem; font-weight: 700; color: var(--badge-indigo-text); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }}
    .prereq-group-title.req-title {{ color: var(--text-secondary); }}
    .or-divider-badge {{ font-size: 0.68rem; font-weight: 700; color: var(--badge-indigo-text); background: #ffffff; border: 1px solid var(--badge-indigo-border); border-radius: 10px; padding: 2px 6px; align-self: center; }}
    .or-connector {{ text-align: center; font-size: 0.68rem; font-weight: 700; color: var(--wpi-crimson); letter-spacing: 0.08em; margin: 4px 0; position: relative; }}
    .and-connector {{ text-align: center; font-size: 0.68rem; font-weight: 700; color: var(--badge-indigo-text); letter-spacing: 0.08em; margin: 4px 0; position: relative; }}
    .badge-tooltip {{ position: fixed; background: #ffffff; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px; box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15); z-index: 1000; width: 290px; pointer-events: none; display: none; font-size: 0.8rem; line-height: 1.4; }}
    .badge-tooltip-code {{ font-family: 'Outfit', sans-serif; font-weight: 700; color: var(--wpi-crimson); font-size: 0.95rem; margin-bottom: 2px; }}
    .badge-tooltip-title {{ font-weight: 600; color: var(--text-primary); font-size: 0.85rem; margin-bottom: 6px; line-height: 1.25; }}
    .badge-tooltip-meta {{ font-size: 0.75rem; color: var(--text-muted); margin-bottom: 6px; }}
    .badge-tooltip-desc {{ font-size: 0.75rem; color: var(--text-secondary); background: var(--bg-main); padding: 8px; border-radius: 6px; border: 1px solid var(--border-color); margin-top: 6px; line-height: 1.35; }}
    .badge-tooltip-prereqs {{ font-size: 0.75rem; color: var(--text-secondary); margin-top: 6px; font-weight: 500; }}
    .description-text {{ font-size: 0.825rem; line-height: 1.5; color: var(--text-secondary); background: var(--bg-main); padding: 12px; border-radius: 6px; border: 1px solid var(--border-color); }}
    #footer {{ height: var(--footer-height); background: var(--bg-card); border-top: 1px solid var(--border-color); display: flex; align-items: center; justify-content: center; padding: 0 16px; font-size: 0.75rem; color: var(--text-secondary); text-align: center; flex-shrink: 0; line-height: 1.3; z-index: 100; }}
    #footer a {{ color: var(--wpi-crimson); text-decoration: none; font-weight: 600; }}
    #footer a:hover {{ text-decoration: underline; }}
    #footer em {{ font-style: italic; }}
  </style>
</head>
<body>
  <header id="header">
    <div class="brand">
      <div class="brand-icon">W</div>
      <div class="brand-title">
        <h1>WPI Course Dependency Graph</h1>
        <p>Worcester Polytechnic Institute</p>
      </div>
    </div>
    <div class="toolbar">
      <div class="search-box">
        <input type="text" id="search-input" placeholder="Search course (e.g. CS 1101)..." onkeydown="handleSearchInput(event)">
        <div id="search-dropdown" class="search-dropdown"></div>
      </div>
      <select id="dept-select" class="select-control" onchange="filterDepartment(this.value)">
        <option value="ALL">All Departments</option>
        {dept_options_html}
      </select>
      <button class="btn" onclick="resetView()">Reset View</button>
    </div>
  </header>
  <div id="main-container">
    <div class="stats-bar">
      <div class="stat-pill">Courses: <span id="stat-courses" class="num">{len(filtered_graph)}</span></div>
      <div id="anchored-container" class="anchored-bar" style="display: none;"></div>
    </div>
    <div id="mynetwork"></div>
    <aside id="sidebar">
      <div class="sidebar-section">
        <div class="section-title">Department Selector</div>
        <div id="legend-grid" class="legend-grid">{legend_items_html}</div>
      </div>
      <div class="sidebar-section details-section">
        <div class="section-title">Course Details</div>
        <div id="details-panel">
          <p class="placeholder-msg">Click any course node in the graph to view prerequisites, unlocked courses, and details.<br><br><strong>Tip:</strong> Right-click a course to <strong>Anchor</strong> it and walk down dependency paths!</p>
        </div>
      </div>
    </aside>
  </div>
  <div id="badge-tooltip" class="badge-tooltip"></div>
  <footer id="footer">
    Site owned and maintained by Joshua DeOliveira. Data is collected from <a href="https://planner.wpi.edu/" target="_blank" rel="noopener">https://planner.wpi.edu/</a>. Work was supported in part by a grant entitled <em>"Supporting Student Success: Using Data to Identify Barriers and Design Data Informed Strategies"</em>.
  </footer>
  <script type="text/javascript">
    const rawNodes = {json.dumps(nodes_js)};
    const rawEdges = {json.dumps(edges_js)};
    const rawGraphData = {{}};
    let searchDebounceTimer = null;
    let searchSelectedIndex = -1;
    let currentSearchMatches = [];
    let originalNodePositions = {{}};
    let currentSelectedCourse = null;
    let anchoredCourseCodes = new Set();
    let showAllPrereqsActive = false;

    rawNodes.forEach(n => {{ rawGraphData[n.id] = n; }});

    const COLOR_WPI_CRIMSON = '#AC2B37';
    const COLOR_ANCHOR_GOLD = '#d97706';
    const COLOR_PREREQ_ANCESTOR = '#4338ca';
    const COLOR_UNLOCK_DESCENDANT = '#0284c7';

    const nodesDataSet = new vis.DataSet(rawNodes.map(n => ({{
      id: n.id,
      label: n.id,
      title: n.title,
      color: {{ background: '#ffffff', border: '#64748b', highlight: {{ background: '#AC2B37', border: '#AC2B37' }} }},
      font: {{ color: '#0f172a', size: 13, face: 'Inter', weight: '600', strokeWidth: 3, strokeColor: '#ffffff' }},
      department: n.department
    }})));

    const edgesDataSet = new vis.DataSet(rawEdges);
    const container = document.getElementById('mynetwork');

    container.addEventListener('contextmenu', function (e) {{
      e.preventDefault();
    }});

    document.addEventListener('click', function(e) {{
      const searchBox = document.querySelector('.search-box');
      if (searchBox && !searchBox.contains(e.target)) {{
        const dropdown = document.getElementById('search-dropdown');
        if (dropdown) dropdown.style.display = 'none';
      }}
    }});

    const data = {{ nodes: nodesDataSet, edges: edgesDataSet }};

    const options = {{
      nodes: {{ shape: 'dot', size: 14, borderWidth: 1.5 }},
      edges: {{ smooth: {{ type: 'continuous', roundness: 0.2 }} }},
      physics: {{
        enabled: true,
        solver: 'barnesHut',
        barnesHut: {{ gravitationalConstant: -3000, centralGravity: 0.3, springLength: 100, springConstant: 0.04 }},
        stabilization: {{ enabled: true, iterations: 150, updateInterval: 25, fit: true }}
      }},
      interaction: {{
        hover: true,
        tooltipDelay: 100,
        navigationButtons: false,
        dragView: true,
        zoomView: true
      }}
    }};

    const network = new vis.Network(container, data, options);

    network.once('stabilizationIterationsDone', function () {{
      network.setOptions({{ physics: {{ enabled: false }} }});
      nodesDataSet.forEach(node => {{
        const pos = network.getPosition(node.id);
        originalNodePositions[node.id] = {{ x: pos.x, y: pos.y }};
      }});
    }});

    network.on('click', function(params) {{
      if (params.nodes.length > 0) {{
        selectCourse(params.nodes[0]);
      }} else {{
        if (anchoredCourseCodes.size === 0) {{
          clearHighlightPath();
        }}
      }}
    }});

    network.on('oncontext', function(params) {{
      params.event.preventDefault();
      const nodeId = network.getNodeAt(params.pointer.DOM);
      if (nodeId) {{
        toggleAnchorCourse(nodeId);
      }}
    }});

    function getAllUpstreamPrereqs(targetCode) {{
      const visited = new Set();
      const depthMap = {{}};

      function traverse(code, currentDepth) {{
        const node = rawGraphData[code];
        if (!node || !node.prerequisites) return;

        node.prerequisites.forEach(prereqId => {{
          if (!visited.has(prereqId)) {{
            visited.add(prereqId);
            depthMap[prereqId] = currentDepth;
            traverse(prereqId, currentDepth + 1);
          }} else {{
            if (currentDepth < depthMap[prereqId]) {{
              depthMap[prereqId] = currentDepth;
            }}
          }}
        }});
      }}

      traverse(targetCode, 1);

      const resultByTier = {{}};
      Object.entries(depthMap).forEach(([pCode, depth]) => {{
        if (!resultByTier[depth]) resultByTier[depth] = [];
        resultByTier[depth].push(pCode);
      }});

      return {{
        allPrereqIds: Array.from(visited),
        depthMap: depthMap,
        resultByTier: resultByTier
      }};
    }}

    function highlightCoursePath(targetCode) {{
      const targetNode = rawGraphData[targetCode];
      if (!targetNode && anchoredCourseCodes.size === 0) return new Set();

      restoreOriginalPositions();

      let activeNodeIds = new Set();
      let directPrereqs = [];
      let recursivePrereqObj = null;

      if (targetNode) {{
        activeNodeIds.add(targetCode);

        if (showAllPrereqsActive) {{
          recursivePrereqObj = getAllUpstreamPrereqs(targetCode);
          directPrereqs = recursivePrereqObj.allPrereqIds;
        }} else {{
          directPrereqs = Array.from(new Set(targetNode.prerequisites || []));
        }}

        const directUnlocks = Array.from(new Set(targetNode.prerequisite_for || []));
        directPrereqs.forEach(p => activeNodeIds.add(p));
        directUnlocks.forEach(u => activeNodeIds.add(u));
      }}

      anchoredCourseCodes.forEach(anchorCode => {{
        activeNodeIds.add(anchorCode);
        const anchorNode = rawGraphData[anchorCode];
        if (anchorNode) {{
          (anchorNode.prerequisites || []).forEach(p => activeNodeIds.add(p));
          (anchorNode.prerequisite_for || []).forEach(u => activeNodeIds.add(u));
        }}
      }});

      const centerPos = targetCode ? (originalNodePositions[targetCode] || network.getPosition(targetCode) || {{ x: 0, y: 0 }}) : {{ x: 0, y: 0 }};
      const nodeUpdates = [];

      if (targetNode) {{
        const directUnlocks = Array.from(new Set(targetNode.prerequisite_for || []));

        if (showAllPrereqsActive && recursivePrereqObj) {{
          Object.entries(recursivePrereqObj.resultByTier).forEach(([depthStr, pCodes]) => {{
            const depth = Number(depthStr);
            const radius = 180 + (depth - 1) * 110;
            const total = pCodes.length;
            pCodes.forEach((pId, idx) => {{
              const angle = (total === 1) ? Math.PI : (Math.PI * 0.55) + ((Math.PI * 0.9) * idx / (total - 1 || 1));
              const posX = centerPos.x + radius * Math.cos(angle);
              const posY = centerPos.y + radius * Math.sin(angle);

              const isAnchored = anchoredCourseCodes.has(pId);
              nodeUpdates.push({{
                id: pId,
                label: pId,
                x: posX,
                y: posY,
                color: isAnchored ? {{ background: COLOR_ANCHOR_GOLD, border: '#b45309' }} : {{ background: COLOR_PREREQ_ANCESTOR, border: '#312e81' }},
                font: {{ color: isAnchored ? COLOR_ANCHOR_GOLD : COLOR_PREREQ_ANCESTOR, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' }},
                size: Math.max(10, 16 - depth * 2),
                hidden: false
              }});
            }});
          }});
        }} else {{
          const prereqRadius = Math.max(180, 15 * directPrereqs.length);
          const prereqNodeSize = Math.max(12, Math.min(18, 250 / (directPrereqs.length || 1)));

          directPrereqs.forEach((prereqId, idx) => {{
            const total = directPrereqs.length;
            const angle = (total === 1) ? Math.PI : (Math.PI * 0.6) + ((Math.PI * 0.8) * idx / (total - 1 || 1));
            const posX = centerPos.x + prereqRadius * Math.cos(angle);
            const posY = centerPos.y + prereqRadius * Math.sin(angle);

            const isAnchored = anchoredCourseCodes.has(prereqId);
            nodeUpdates.push({{
              id: prereqId,
              label: prereqId,
              x: posX,
              y: posY,
              color: isAnchored ? {{ background: COLOR_ANCHOR_GOLD, border: '#b45309' }} : {{ background: COLOR_PREREQ_ANCESTOR, border: '#312e81' }},
              font: {{ color: isAnchored ? COLOR_ANCHOR_GOLD : COLOR_PREREQ_ANCESTOR, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' }},
              size: prereqNodeSize,
              hidden: false
            }});
          }});
        }}

        const unlockRadius = Math.max(220, Math.min(420, 8 * directUnlocks.length));
        const unlockNodeSize = Math.max(10, Math.min(18, 300 / (directUnlocks.length || 1)));

        directUnlocks.forEach((unlockId, idx) => {{
          const total = directUnlocks.length;
          const angle = (total === 1) ? 0 : (-Math.PI * 0.42) + ((Math.PI * 0.84) * idx / (total - 1 || 1));
          const posX = centerPos.x + unlockRadius * Math.cos(angle);
          const posY = centerPos.y + unlockRadius * Math.sin(angle);

          const isAnchored = anchoredCourseCodes.has(unlockId);
          nodeUpdates.push({{
            id: unlockId,
            label: unlockId,
            x: posX,
            y: posY,
            color: isAnchored ? {{ background: COLOR_ANCHOR_GOLD, border: '#b45309' }} : {{ background: COLOR_UNLOCK_DESCENDANT, border: '#0369a1' }},
            font: {{ color: isAnchored ? COLOR_ANCHOR_GOLD : COLOR_UNLOCK_DESCENDANT, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' }},
            size: unlockNodeSize,
            hidden: false
          }});
        }});

        const isTargetAnchored = anchoredCourseCodes.has(targetCode);
        nodeUpdates.push({{
          id: targetCode,
          label: targetCode,
          x: centerPos.x,
          y: centerPos.y,
          color: isTargetAnchored ? {{ background: COLOR_ANCHOR_GOLD, border: '#b45309' }} : {{ background: COLOR_WPI_CRIMSON, border: '#8B222C' }},
          font: {{ color: isTargetAnchored ? COLOR_ANCHOR_GOLD : COLOR_WPI_CRIMSON, size: 16, face: 'Inter', weight: '700', strokeWidth: 4, strokeColor: '#ffffff' }},
          size: 24,
          hidden: false
        }});
      }}

      anchoredCourseCodes.forEach(aCode => {{
        if (aCode !== targetCode) {{
          const orig = originalNodePositions[aCode] || network.getPosition(aCode);
          nodeUpdates.push({{
            id: aCode,
            label: aCode,
            x: orig ? orig.x : undefined,
            y: orig ? orig.y : undefined,
            color: {{ background: COLOR_ANCHOR_GOLD, border: '#b45309' }},
            font: {{ color: COLOR_ANCHOR_GOLD, size: 15, face: 'Inter', weight: '700', strokeWidth: 4, strokeColor: '#ffffff' }},
            size: 20,
            hidden: false
          }});
        }}
      }});

      nodesDataSet.forEach(node => {{
        if (!activeNodeIds.has(node.id)) {{
          const orig = originalNodePositions[node.id];
          nodeUpdates.push({{
            id: node.id,
            label: node.id,
            x: orig ? orig.x : undefined,
            y: orig ? orig.y : undefined,
            color: {{ background: '#e5e1d8', border: 'rgba(203, 213, 225, 0.3)' }},
            font: {{ color: 'rgba(148, 163, 184, 0.05)', size: 7, face: 'Inter', weight: '400', strokeWidth: 0 }},
            size: 4,
            hidden: false
          }});
        }}
      }});

      const edgeUpdates = [];
      const activeEdgeIds = [];

      edgesDataSet.forEach(edge => {{
        const isFromActive = activeNodeIds.has(edge.from);
        const isToActive = activeNodeIds.has(edge.to);

        if (isFromActive && isToActive) {{
          const isAnchorEdge = (anchoredCourseCodes.has(edge.from) || anchoredCourseCodes.has(edge.to));
          edgeUpdates.push({{
            id: edge.id,
            color: {{ color: isAnchorEdge ? COLOR_ANCHOR_GOLD : COLOR_PREREQ_ANCESTOR, highlight: COLOR_WPI_CRIMSON }},
            width: 3.2
          }});
          activeEdgeIds.push(edge.id);
        }} else {{
          edgeUpdates.push({{
            id: edge.id,
            color: {{ color: 'rgba(226, 221, 211, 0.08)' }},
            width: 0.5
          }});
        }}
      }});

      nodesDataSet.update(nodeUpdates);
      edgesDataSet.update(edgeUpdates);

      const activeNodes = nodeUpdates.filter(u => activeNodeIds.has(u.id));
      nodesDataSet.remove(Array.from(activeNodeIds));
      nodesDataSet.add(activeNodes);

      if (activeEdgeIds.length > 0) {{
        const fullActiveEdgeObjs = edgesDataSet.get(activeEdgeIds);
        edgesDataSet.remove(activeEdgeIds);
        edgesDataSet.add(fullActiveEdgeObjs);
      }}

      return activeNodeIds;
    }}

    function restoreOriginalPositions() {{
      const updates = [];
      nodesDataSet.forEach(node => {{
        const orig = originalNodePositions[node.id];
        if (orig) {{
          updates.push({{ id: node.id, x: orig.x, y: orig.y }});
        }}
      }});
      if (updates.length > 0) {{
        nodesDataSet.update(updates);
      }}
    }}

    function clearHighlightPath() {{
      restoreOriginalPositions();

      const nodeUpdates = [];
      nodesDataSet.forEach(node => {{
        const isAnchored = anchoredCourseCodes.has(node.id);
        nodeUpdates.push({{
          id: node.id,
          label: node.id,
          color: isAnchored ? {{ background: COLOR_ANCHOR_GOLD, border: '#b45309' }} : {{
            background: '#ffffff',
            border: '#64748b',
            highlight: {{ background: '#AC2B37', border: '#AC2B37' }}
          }},
          font: {{ color: isAnchored ? COLOR_ANCHOR_GOLD : '#0f172a', size: isAnchored ? 15 : 13, face: 'Inter', weight: '600', strokeWidth: 3, strokeColor: '#ffffff' }},
          size: isAnchored ? 20 : 14,
          hidden: false
        }});
      }});

      const edgeUpdates = [];
      edgesDataSet.forEach(edge => {{
        edgeUpdates.push({{
          id: edge.id,
          color: {{ color: '#cbd5e1', highlight: '#AC2B37' }},
          width: 1.2
        }});
      }});

      nodesDataSet.update(nodeUpdates);
      edgesDataSet.update(edgeUpdates);
    }}

    function toggleAnchorCourse(code) {{
      if (anchoredCourseCodes.has(code)) {{
        anchoredCourseCodes.delete(code);
      }} else {{
        anchoredCourseCodes.add(code);
      }}
      updateAnchoredUI();
      if (currentSelectedCourse) {{
        selectCourse(currentSelectedCourse);
      }} else {{
        selectCourse(code);
      }}
    }}

    function clearAllAnchors() {{
      anchoredCourseCodes.clear();
      updateAnchoredUI();
      if (currentSelectedCourse) {{
        selectCourse(currentSelectedCourse);
      }} else {{
        clearHighlightPath();
      }}
    }}

    function updateAnchoredUI() {{
      const container = document.getElementById('anchored-container');
      if (!container) return;

      if (anchoredCourseCodes.size === 0) {{
        container.style.display = 'none';
        container.innerHTML = '';
        return;
      }}

      const pillsHTML = Array.from(anchoredCourseCodes).map(code => `
        <span class="anchor-pill" onclick="toggleAnchorCourse('${{code}}')">
          ⚓ ${{code}} &times;
        </span>
      `).join('');

      container.innerHTML = `
        <span>Anchored Paths:</span>
        ${{pillsHTML}}
        <button class="btn-xs" style="margin-left: 4px;" onclick="clearAllAnchors()">Clear All</button>
      `;
      container.style.display = 'flex';
    }}

    function toggleShowAllPrereqs(code) {{
      showAllPrereqsActive = !showAllPrereqsActive;
      selectCourse(code);
    }}

    function selectCourse(code) {{
      const node = rawGraphData[code];
      if (!node) return;

      if (currentSelectedCourse !== code) {{
        showAllPrereqsActive = false;
      }}

      currentSelectedCourse = code;

      const searchInput = document.getElementById('search-input');
      if (searchInput) searchInput.value = code;

      const dropdown = document.getElementById('search-dropdown');
      if (dropdown) dropdown.style.display = 'none';

      const activeNodeIds = highlightCoursePath(code);

      if (activeNodeIds && activeNodeIds.size > 0) {{
        network.fit({{
          nodes: Array.from(activeNodeIds),
          animation: {{ duration: 350, easingFunction: 'easeInOutQuad' }}
        }});
      }} else {{
        network.focus(code, {{ scale: 1.1, animation: {{ duration: 350, easingFunction: 'easeInOutQuad' }} }});
      }}

      renderCourseDetails(node);
    }}

    function showBadgeTooltip(e, code) {{
      const node = rawGraphData[code];
      if (!node) return;

      const tooltip = document.getElementById('badge-tooltip');
      if (!tooltip) return;

      const prereqText = (node.prerequisites && node.prerequisites.length > 0)
        ? node.prerequisites.join(', ')
        : 'None';

      tooltip.innerHTML = `
        <div class="badge-tooltip-code">${{node.id}}</div>
        <div class="badge-tooltip-title">${{node.name || 'Course Title'}}</div>
        <div class="badge-tooltip-meta"><strong>Dept:</strong> ${{node.department || 'N/A'}} | <strong>Credits:</strong> ${{node.min_credits || '3.0'}}</div>
        ${{node.description ? `<div class="badge-tooltip-desc">${{node.description}}</div>` : ''}}
        <div class="badge-tooltip-prereqs"><strong>Prerequisites:</strong> ${{prereqText}}</div>
      `;

      tooltip.style.display = 'block';
      moveBadgeTooltip(e);
    }}

    function moveBadgeTooltip(e) {{
      const tooltip = document.getElementById('badge-tooltip');
      if (!tooltip || tooltip.style.display === 'none') return;
      const padding = 15;
      let left = e.clientX + padding;
      let top = e.clientY + padding;

      if (left + 300 > window.innerWidth) {{
        left = e.clientX - 310;
      }}
      if (top + 180 > window.innerHeight) {{
        top = e.clientY - 190;
      }}

      tooltip.style.left = left + 'px';
      tooltip.style.top = top + 'px';
    }}

    function hideBadgeTooltip() {{
      const tooltip = document.getElementById('badge-tooltip');
      if (tooltip) tooltip.style.display = 'none';
    }}

    function renderCourseDetails(node) {{
      const panel = document.getElementById('details-panel');
      const isAnchored = anchoredCourseCodes.has(node.id);

      let prereqHTML = '';

      if (showAllPrereqsActive) {{
        const treeObj = getAllUpstreamPrereqs(node.id);
        if (Object.keys(treeObj.resultByTier).length > 0) {{
          const tierHTMLs = Object.entries(treeObj.resultByTier).sort((a,b) => Number(a[0]) - Number(b[0])).map(([depthStr, pCodes]) => {{
            const depth = Number(depthStr);
            const tierLabel = (depth === 1) ? 'Tier 1 (Direct Prerequisites)' : `Tier ${{depth}} (Upstream Prerequisites)`;
            const badges = pCodes.map(p => `
              <span class="badge badge-prereq" 
                    onclick="selectCourse('${{p}}')"
                    onmouseenter="showBadgeTooltip(event, '${{p}}')"
                    onmousemove="moveBadgeTooltip(event)"
                    onmouseleave="hideBadgeTooltip()">${{p}}</span>
            `).join(' ');

            return `
              <div class="depth-tier-block">
                <div class="depth-tier-title">${{tierLabel}}</div>
                <div class="badge-list">${{badges}}</div>
              </div>
            `;
          }});
          prereqHTML = tierHTMLs.join('');
        }} else {{
          prereqHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">No upstream prerequisites.</span>';
        }}
      }} else if (node.prerequisites_structured && node.prerequisites_structured.length > 0) {{
        const topConnector = (node.prerequisites_structured[0] && node.prerequisites_structured[0].connector === 'OR') ? 'OR' : 'AND';

        const groupHTMLs = node.prerequisites_structured.map((group, idx) => {{
          const type = group.type || 'AND';
          const isOrGroup = (type === 'OR' && group.courses.length > 1);

          const badges = group.courses.map(p => `
            <span class="badge badge-prereq" 
                  onclick="selectCourse('${{p}}')"
                  onmouseenter="showBadgeTooltip(event, '${{p}}')"
                  onmousemove="moveBadgeTooltip(event)"
                  onmouseleave="hideBadgeTooltip()">${{p}}</span>
          `).join(isOrGroup ? ' <span class="or-divider-badge">OR</span> ' : ' ');

          return `
            <div class="prereq-group-box ${{isOrGroup ? 'or-group' : 'and-group'}}">
              ${{isOrGroup ? '<div class="prereq-group-title">Any One Of:</div>' : (node.prerequisites_structured.length > 1 ? '<div class="prereq-group-title req-title">Required:</div>' : '')}}
              <div class="badge-list">${{badges}}</div>
            </div>
          `;
        }});

        const connectorHTML = (topConnector === 'OR')
          ? '<div class="or-connector">— OR —</div>'
          : '<div class="and-connector">— AND —</div>';

        prereqHTML = groupHTMLs.join(connectorHTML);
      }} else if ((node.prerequisites || []).length > 0) {{
        prereqHTML = `
          <div class="badge-list">
            ${{node.prerequisites.map(p => `
              <span class="badge badge-prereq" 
                    onclick="selectCourse('${{p}}')"
                    onmouseenter="showBadgeTooltip(event, '${{p}}')"
                    onmousemove="moveBadgeTooltip(event)"
                    onmouseleave="hideBadgeTooltip()">${{p}}</span>
            `).join('')}}
          </div>
        `;
      }} else {{
        prereqHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">None</span>';
      }}

      const unlockBadges = (node.prerequisite_for || []).length > 0
        ? node.prerequisite_for.map(u => `
            <span class="badge badge-unlock" 
                  onclick="selectCourse('${{u}}')"
                  onmouseenter="showBadgeTooltip(event, '${{u}}')"
                  onmousemove="moveBadgeTooltip(event)"
                  onmouseleave="hideBadgeTooltip()">${{u}}</span>
          `).join('')
        : '<span style="color: var(--text-muted); font-size: 0.8rem;">None</span>';

      const aliasBadges = (node.aliases || []).length > 0
        ? node.aliases.map(a => `
            <span class="badge badge-alias" 
                  onclick="selectCourse('${{a}}')"
                  onmouseenter="showBadgeTooltip(event, '${{a}}')"
                  onmousemove="moveBadgeTooltip(event)"
                  onmouseleave="hideBadgeTooltip()">${{a}}</span>
          `).join('')
        : '<span style="color: var(--text-muted); font-size: 0.8rem;">None</span>';

      const hasPrereqs = (node.prerequisites || []).length > 0;

      panel.innerHTML = `
        <div class="course-card-header">
          <div class="course-header-top">
            <div class="course-code-tag ${{isAnchored ? 'anchored' : ''}}">${{node.id}} ${{isAnchored ? '⚓' : ''}}</div>
            <button class="btn-xs btn-anchor ${{isAnchored ? 'active' : ''}}" onclick="toggleAnchorCourse('${{node.id}}')">
              ${{isAnchored ? '⚓ Unanchor' : '⚓ Anchor Path'}}
            </button>
          </div>
          <div class="course-title-text">${{node.name || 'Course Title'}}</div>
          <div class="meta-row">
            <span><strong>Department:</strong> ${{node.department || 'N/A'}}</span>
            <span><strong>Credits:</strong> ${{node.min_credits || '3.0'}}</span>
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-block-header">
            <div class="detail-block-label">Prerequisites Required</div>
            ${{hasPrereqs ? `
              <button class="btn-xs ${{showAllPrereqsActive ? 'active' : ''}}" onclick="toggleShowAllPrereqs('${{node.id}}')">
                ${{showAllPrereqsActive ? 'Collapse Tree' : 'Show All (Tree)'}}
              </button>
            ` : ''}}
          </div>
          ${{prereqHTML}}
        </div>

        <div class="detail-block">
          <div class="detail-block-label">Unlocks Courses</div>
          <div class="badge-list">${{unlockBadges}}</div>
        </div>

        <div class="detail-block">
          <div class="detail-block-label">Aliases / Cross-Listed</div>
          <div class="badge-list">${{aliasBadges}}</div>
        </div>

        ${{node.description ? `<div class="detail-block"><div class="detail-block-label">Prerequisite Statement</div><div class="description-text">${{node.description}}</div></div>` : ''}}
      `;
    }}

    function filterDepartment(dept) {{
      document.getElementById('dept-select').value = dept;
      const updates = [];
      const visibleNodeIds = [];

      if (dept === 'ALL') {{
        nodesDataSet.forEach(n => {{
          updates.push({{ id: n.id, hidden: false }});
          visibleNodeIds.push(n.id);
        }});
      }} else {{
        nodesDataSet.forEach(n => {{
          const isVisible = (n.department === dept);
          updates.push({{ id: n.id, hidden: !isVisible }});
          if (isVisible) visibleNodeIds.push(n.id);
        }});
      }}

      nodesDataSet.update(updates);

      if (visibleNodeIds.length > 0) {{
        setTimeout(() => {{
          network.fit({{
            nodes: visibleNodeIds,
            animation: {{
              duration: 400,
              easingFunction: 'easeInOutQuad'
            }}
          }});
        }}, 50);
      }}
    }}

    function handleSearchInput(event) {{
      const dropdown = document.getElementById('search-dropdown');
      const items = dropdown.querySelectorAll('.search-item');

      if (event.key === 'ArrowDown') {{
        event.preventDefault();
        if (currentSearchMatches.length === 0) return;
        searchSelectedIndex = (searchSelectedIndex + 1) % currentSearchMatches.length;
        updateSearchHighlight(items);
        return;
      }}

      if (event.key === 'ArrowUp') {{
        event.preventDefault();
        if (currentSearchMatches.length === 0) return;
        searchSelectedIndex = (searchSelectedIndex - 1 + currentSearchMatches.length) % currentSearchMatches.length;
        updateSearchHighlight(items);
        return;
      }}

      if (event.key === 'Enter') {{
        event.preventDefault();
        if (searchSelectedIndex >= 0 && searchSelectedIndex < currentSearchMatches.length) {{
          selectCourse(currentSearchMatches[searchSelectedIndex].id);
        }} else if (currentSearchMatches.length > 0) {{
          selectCourse(currentSearchMatches[0].id);
        }}
        dropdown.style.display = 'none';
        searchSelectedIndex = -1;
        return;
      }}

      if (event.key === 'Escape') {{
        dropdown.style.display = 'none';
        searchSelectedIndex = -1;
        return;
      }}

      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {{
        const query = event.target.value.toUpperCase().trim();

        if (!query || query.length < 2) {{
          dropdown.style.display = 'none';
          currentSearchMatches = [];
          searchSelectedIndex = -1;
          return;
        }}

        currentSearchMatches = rawNodes.filter(n => n.id.includes(query) || (n.name && n.name.toUpperCase().includes(query))).slice(0, 8);
        searchSelectedIndex = -1;

        if (currentSearchMatches.length > 0) {{
          dropdown.innerHTML = currentSearchMatches.map((m, idx) => `
            <div class="search-item" data-index="${{idx}}" onclick="selectCourse('${{m.id}}')">
              <strong>${{m.id}}</strong>: ${{m.name || ''}}
            </div>
          `).join('');
          dropdown.style.display = 'block';
        }} else {{
          dropdown.style.display = 'none';
        }}
      }}, 100);
    }}

    function updateSearchHighlight(items) {{
      items.forEach((item, idx) => {{
        if (idx === searchSelectedIndex) {{
          item.classList.add('active');
          item.scrollIntoView({{ block: 'nearest' }});
        }} else {{
          item.classList.remove('active');
        }}
      }});
    }}

    function resetView() {{
      document.getElementById('search-input').value = '';
      document.getElementById('dept-select').value = 'ALL';
      const dropdown = document.getElementById('search-dropdown');
      if (dropdown) dropdown.style.display = 'none';
      filterDepartment('ALL');
      clearAllAnchors();
      clearHighlightPath();
      network.fit({{ animation: {{ duration: 300, easingFunction: 'easeInOutQuad' }} }});
    }}
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
