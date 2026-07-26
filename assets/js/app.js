/**
 * WPI Course Graph & Planner Application Logic
 * Powered by Flagger Academic Engine & Vis.js
 * Right-Click Anchoring, Path Walking & Recursive Prerequisite Tree Unwinding
 */

let rawGraphData = {};
let network = null;
let nodesDataSet = null;
let edgesDataSet = null;
let originalNodePositions = {};

let searchDebounceTimer = null;
let searchSelectedIndex = -1;
let currentSearchMatches = [];

let currentSelectedCourse = null;
let anchoredCourseCodes = new Set();
let showAllPrereqsActive = false;

const COLOR_DEFAULT_NODE = '#ffffff';
const COLOR_DEFAULT_BORDER = '#64748b';
const COLOR_DEFAULT_TEXT = '#0f172a';

const COLOR_WPI_CRIMSON = '#AC2B37';
const COLOR_ANCHOR_GOLD = '#d97706';
const COLOR_PREREQ_ANCESTOR = '#4338ca';   // Deep Royal Indigo for Direct Prerequisites
const COLOR_UNLOCK_DESCENDANT = '#0284c7';  // Ocean Sky Blue for Direct Unlocked Courses

// Initialize Application
async function initApp() {
  try {
    const response = await fetch('data/wpi_course_graph.json');
    if (!response.ok) {
      throw new Error(`Failed to load graph data: ${response.status}`);
    }
    rawGraphData = await response.json();
    renderStats(rawGraphData);
    setupNetwork(rawGraphData);
    populateDepartmentSelect(rawGraphData);
    renderLegend(rawGraphData);

    // Hide search dropdown on click outside
    document.addEventListener('click', function(e) {
      const searchBox = document.querySelector('.search-box');
      if (searchBox && !searchBox.contains(e.target)) {
        const dropdown = document.getElementById('search-dropdown');
        if (dropdown) dropdown.style.display = 'none';
      }
    });
  } catch (err) {
    console.error('Initialization error:', err);
    document.getElementById('details-panel').innerHTML = `
      <p style="color: #AC2B37; padding: 16px; font-size: 0.85rem;">
        Error loading course graph dataset. Make sure <code>data/wpi_course_graph.json</code> exists.
      </p>
    `;
  }
}

// Render Stats Header
function renderStats(graphData) {
  const totalCourses = Object.keys(graphData).length;
  const depts = new Set(Object.values(graphData).map(n => n.department_code || 'OTHER'));
  const prereqLinks = Object.values(graphData).reduce((acc, n) => acc + (n.prerequisites ? n.prerequisites.length : 0), 0);

  document.getElementById('stat-courses').textContent = totalCourses;
  document.getElementById('stat-depts').textContent = depts.size;
  document.getElementById('stat-links').textContent = prereqLinks;
}

// Setup Vis.js Network
function setupNetwork(graphData) {
  const nodes = [];
  const edges = [];
  const addedEdges = new Set();

  Object.entries(graphData).forEach(([code, node]) => {
    const dept = node.department_code || 'OTHER';

    nodes.push({
      id: code,
      label: code,
      title: `${code} - ${node.course_name || ''}`,
      color: {
        background: COLOR_DEFAULT_NODE,
        border: COLOR_DEFAULT_BORDER,
        highlight: { background: COLOR_WPI_CRIMSON, border: COLOR_WPI_CRIMSON },
        hover: { background: '#f8fafc', border: COLOR_WPI_CRIMSON }
      },
      font: {
        color: COLOR_DEFAULT_TEXT,
        size: 13,
        face: 'Inter',
        weight: '600',
        strokeWidth: 3,
        strokeColor: '#ffffff'
      },
      department: dept
    });

    // Prerequisite Edges (Prereq -> Course)
    (node.prerequisites || []).forEach(prereq => {
      if (graphData[prereq]) {
        const edgeKey = `${prereq}->${code}`;
        if (!addedEdges.has(edgeKey)) {
          edges.push({
            id: edgeKey,
            from: prereq,
            to: code,
            arrows: { to: { enabled: true, scaleFactor: 0.4 } },
            color: { color: '#cbd5e1', highlight: COLOR_WPI_CRIMSON },
            width: 1.2
          });
          addedEdges.add(edgeKey);
        }
      }
    });

    // Alias Edges
    (node.aliases || []).forEach(alias => {
      if (graphData[alias]) {
        const edgeKey = [code, alias].sort().join('<->');
        if (!addedEdges.has(edgeKey)) {
          edges.push({
            id: edgeKey,
            from: code,
            to: alias,
            dashes: true,
            color: { color: '#94a3b8', highlight: COLOR_WPI_CRIMSON },
            width: 1
          });
          addedEdges.add(edgeKey);
        }
      }
    });
  });

  nodesDataSet = new vis.DataSet(nodes);
  edgesDataSet = new vis.DataSet(edges);

  const container = document.getElementById('mynetwork');

  // Prevent default context menu & bind Right-Click Anchoring
  container.addEventListener('contextmenu', function (e) {
    e.preventDefault();
  });

  const data = { nodes: nodesDataSet, edges: edgesDataSet };

  const options = {
    nodes: {
      shape: 'dot',
      size: 14,
      borderWidth: 1.5
    },
    edges: {
      smooth: { type: 'continuous', roundness: 0.2 }
    },
    physics: {
      enabled: true,
      solver: 'barnesHut',
      barnesHut: {
        gravitationalConstant: -3000,
        centralGravity: 0.3,
        springLength: 100,
        springConstant: 0.04
      },
      stabilization: {
        enabled: true,
        iterations: 150,
        updateInterval: 25,
        fit: true
      }
    },
    interaction: {
      hover: true,
      tooltipDelay: 100,
      navigationButtons: false,
      dragView: true,
      zoomView: true
    }
  };

  network = new vis.Network(container, data, options);

  // Disable physics immediately after initial stabilization & record base positions
  network.once('stabilizationIterationsDone', function () {
    network.setOptions({ physics: { enabled: false } });
    nodesDataSet.forEach(node => {
      const pos = network.getPosition(node.id);
      originalNodePositions[node.id] = { x: pos.x, y: pos.y };
    });
  });

  // Left-Click: Select Course
  network.on('click', function(params) {
    if (params.nodes.length > 0) {
      const code = params.nodes[0];
      selectCourse(code);
    } else {
      if (anchoredCourseCodes.size === 0) {
        clearHighlightPath();
      }
    }
  });

  // Right-Click: Toggle Anchor Course
  network.on('oncontext', function(params) {
    params.event.preventDefault();
    const nodeId = network.getNodeAt(params.pointer.DOM);
    if (nodeId) {
      toggleAnchorCourse(nodeId);
    }
  });
}

// RECURSIVE UPSTREAM PREREQUISITES TRAVERSAL ENGINE
function getAllUpstreamPrereqs(targetCode) {
  const visited = new Set();
  const depthMap = {};

  function traverse(code, currentDepth) {
    const node = rawGraphData[code];
    if (!node || !node.prerequisites) return;

    node.prerequisites.forEach(prereqId => {
      if (!visited.has(prereqId)) {
        visited.add(prereqId);
        depthMap[prereqId] = currentDepth;
        traverse(prereqId, currentDepth + 1);
      } else {
        if (currentDepth < depthMap[prereqId]) {
          depthMap[prereqId] = currentDepth;
        }
      }
    });
  }

  traverse(targetCode, 1);

  const resultByTier = {};
  Object.entries(depthMap).forEach(([pCode, depth]) => {
    if (!resultByTier[depth]) resultByTier[depth] = [];
    resultByTier[depth].push(pCode);
  });

  return {
    allPrereqIds: Array.from(visited),
    depthMap: depthMap,
    resultByTier: resultByTier
  };
}

// RADIAL FOCUS LAYOUT ENGINE WITH ANCHORING & RECURSIVE TREE UNWINDING
function highlightCoursePath(targetCode) {
  const targetNode = rawGraphData[targetCode];
  if (!targetNode && anchoredCourseCodes.size === 0) return new Set();

  restoreOriginalPositions();

  let activeNodeIds = new Set();
  let directPrereqs = [];
  let recursivePrereqObj = null;

  if (targetNode) {
    activeNodeIds.add(targetCode);

    if (showAllPrereqsActive) {
      recursivePrereqObj = getAllUpstreamPrereqs(targetCode);
      directPrereqs = recursivePrereqObj.allPrereqIds;
    } else {
      directPrereqs = Array.from(new Set(targetNode.prerequisites || []));
    }

    const directUnlocks = Array.from(new Set(targetNode.prerequisite_for || []));
    directPrereqs.forEach(p => activeNodeIds.add(p));
    directUnlocks.forEach(u => activeNodeIds.add(u));
  }

  // Add all anchored courses and their dependencies to active set
  anchoredCourseCodes.forEach(anchorCode => {
    activeNodeIds.add(anchorCode);
    const anchorNode = rawGraphData[anchorCode];
    if (anchorNode) {
      (anchorNode.prerequisites || []).forEach(p => activeNodeIds.add(p));
      (anchorNode.prerequisite_for || []).forEach(u => activeNodeIds.add(u));
    }
  });

  const centerPos = targetCode ? (originalNodePositions[targetCode] || network.getPosition(targetCode) || { x: 0, y: 0 }) : { x: 0, y: 0 };
  const nodeUpdates = [];

  if (targetNode) {
    const directUnlocks = Array.from(new Set(targetNode.prerequisite_for || []));

    // Position Prerequisites
    if (showAllPrereqsActive && recursivePrereqObj) {
      const maxTier = Math.max(...Object.keys(recursivePrereqObj.resultByTier).map(Number), 1);
      Object.entries(recursivePrereqObj.resultByTier).forEach(([depthStr, pCodes]) => {
        const depth = Number(depthStr);
        const radius = 180 + (depth - 1) * 110;
        const total = pCodes.length;
        pCodes.forEach((pId, idx) => {
          const angle = (total === 1) ? Math.PI : (Math.PI * 0.55) + ((Math.PI * 0.9) * idx / (total - 1 || 1));
          const posX = centerPos.x + radius * Math.cos(angle);
          const posY = centerPos.y + radius * Math.sin(angle);

          const isAnchored = anchoredCourseCodes.has(pId);
          nodeUpdates.push({
            id: pId,
            label: pId,
            x: posX,
            y: posY,
            color: isAnchored ? { background: COLOR_ANCHOR_GOLD, border: '#b45309' } : { background: COLOR_PREREQ_ANCESTOR, border: '#312e81' },
            font: { color: isAnchored ? COLOR_ANCHOR_GOLD : COLOR_PREREQ_ANCESTOR, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' },
            size: Math.max(10, 16 - depth * 2),
            hidden: false
          });
        });
      });
    } else {
      const prereqRadius = Math.max(180, 15 * directPrereqs.length);
      const prereqNodeSize = Math.max(12, Math.min(18, 250 / (directPrereqs.length || 1)));

      directPrereqs.forEach((prereqId, idx) => {
        const total = directPrereqs.length;
        const angle = (total === 1) ? Math.PI : (Math.PI * 0.6) + ((Math.PI * 0.8) * idx / (total - 1 || 1));
        const posX = centerPos.x + prereqRadius * Math.cos(angle);
        const posY = centerPos.y + prereqRadius * Math.sin(angle);

        const isAnchored = anchoredCourseCodes.has(prereqId);
        nodeUpdates.push({
          id: prereqId,
          label: prereqId,
          x: posX,
          y: posY,
          color: isAnchored ? { background: COLOR_ANCHOR_GOLD, border: '#b45309' } : { background: COLOR_PREREQ_ANCESTOR, border: '#312e81' },
          font: { color: isAnchored ? COLOR_ANCHOR_GOLD : COLOR_PREREQ_ANCESTOR, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' },
          size: prereqNodeSize,
          hidden: false
        });
      });
    }

    // Position Unlocked Courses
    const unlockRadius = Math.max(220, Math.min(420, 8 * directUnlocks.length));
    const unlockNodeSize = Math.max(10, Math.min(18, 300 / (directUnlocks.length || 1)));

    directUnlocks.forEach((unlockId, idx) => {
      const total = directUnlocks.length;
      const angle = (total === 1) ? 0 : (-Math.PI * 0.42) + ((Math.PI * 0.84) * idx / (total - 1 || 1));
      const posX = centerPos.x + unlockRadius * Math.cos(angle);
      const posY = centerPos.y + unlockRadius * Math.sin(angle);

      const isAnchored = anchoredCourseCodes.has(unlockId);
      nodeUpdates.push({
        id: unlockId,
        label: unlockId,
        x: posX,
        y: posY,
        color: isAnchored ? { background: COLOR_ANCHOR_GOLD, border: '#b45309' } : { background: COLOR_UNLOCK_DESCENDANT, border: '#0369a1' },
        font: { color: isAnchored ? COLOR_ANCHOR_GOLD : COLOR_UNLOCK_DESCENDANT, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' },
        size: unlockNodeSize,
        hidden: false
      });
    });

    // Selected Target Node
    const isTargetAnchored = anchoredCourseCodes.has(targetCode);
    nodeUpdates.push({
      id: targetCode,
      label: targetCode,
      x: centerPos.x,
      y: centerPos.y,
      color: isTargetAnchored ? { background: COLOR_ANCHOR_GOLD, border: '#b45309' } : { background: COLOR_WPI_CRIMSON, border: '#8B222C' },
      font: { color: isTargetAnchored ? COLOR_ANCHOR_GOLD : COLOR_WPI_CRIMSON, size: 16, face: 'Inter', weight: '700', strokeWidth: 4, strokeColor: '#ffffff' },
      size: 24,
      hidden: false
    });
  }

  // Ensure all other anchored nodes maintain high visibility
  anchoredCourseCodes.forEach(aCode => {
    if (aCode !== targetCode) {
      const orig = originalNodePositions[aCode] || network.getPosition(aCode);
      nodeUpdates.push({
        id: aCode,
        label: aCode,
        x: orig ? orig.x : undefined,
        y: orig ? orig.y : undefined,
        color: { background: COLOR_ANCHOR_GOLD, border: '#b45309' },
        font: { color: COLOR_ANCHOR_GOLD, size: 15, face: 'Inter', weight: '700', strokeWidth: 4, strokeColor: '#ffffff' },
        size: 20,
        hidden: false
      });
    }
  });

  // Inactive background nodes
  nodesDataSet.forEach(node => {
    if (!activeNodeIds.has(node.id)) {
      const orig = originalNodePositions[node.id];
      nodeUpdates.push({
        id: node.id,
        label: node.id,
        x: orig ? orig.x : undefined,
        y: orig ? orig.y : undefined,
        color: { background: '#e5e1d8', border: 'rgba(203, 213, 225, 0.3)' },
        font: { color: 'rgba(148, 163, 184, 0.05)', size: 7, face: 'Inter', weight: '400', strokeWidth: 0 },
        size: 4,
        hidden: false
      });
    }
  });

  // STRICT EDGE Z-LAYERING: Fade out background edges, elevate active & anchored edges
  const edgeUpdates = [];
  const activeEdgeIds = [];

  edgesDataSet.forEach(edge => {
    const isFromActive = activeNodeIds.has(edge.from);
    const isToActive = activeNodeIds.has(edge.to);
    const isBothActive = isFromActive && isToActive;

    if (isBothActive) {
      const isAnchorEdge = (anchoredCourseCodes.has(edge.from) || anchoredCourseCodes.has(edge.to));
      edgeUpdates.push({
        id: edge.id,
        color: { color: isAnchorEdge ? COLOR_ANCHOR_GOLD : COLOR_PREREQ_ANCESTOR, highlight: COLOR_WPI_CRIMSON },
        width: 3.2
      });
      activeEdgeIds.push(edge.id);
    } else {
      edgeUpdates.push({
        id: edge.id,
        color: { color: 'rgba(226, 221, 211, 0.08)' },
        width: 0.5
      });
    }
  });

  nodesDataSet.update(nodeUpdates);
  edgesDataSet.update(edgeUpdates);

  // Canvas Re-insertion Hack: Re-add active nodes & active edges so they render on top
  const activeNodes = nodeUpdates.filter(u => activeNodeIds.has(u.id));
  nodesDataSet.remove(Array.from(activeNodeIds));
  nodesDataSet.add(activeNodes);

  if (activeEdgeIds.length > 0) {
    const fullActiveEdgeObjs = edgesDataSet.get(activeEdgeIds);
    edgesDataSet.remove(activeEdgeIds);
    edgesDataSet.add(fullActiveEdgeObjs);
  }

  return activeNodeIds;
}

// Restore Original Node Base Coordinates
function restoreOriginalPositions() {
  const updates = [];
  nodesDataSet.forEach(node => {
    const orig = originalNodePositions[node.id];
    if (orig) {
      updates.push({ id: node.id, x: orig.x, y: orig.y });
    }
  });
  if (updates.length > 0) {
    nodesDataSet.update(updates);
  }
}

// BATCHED OPTIMIZED CLEAR
function clearHighlightPath() {
  restoreOriginalPositions();

  const nodeUpdates = [];
  nodesDataSet.forEach(node => {
    const isAnchored = anchoredCourseCodes.has(node.id);
    nodeUpdates.push({
      id: node.id,
      label: node.id,
      color: isAnchored ? { background: COLOR_ANCHOR_GOLD, border: '#b45309' } : {
        background: COLOR_DEFAULT_NODE,
        border: COLOR_DEFAULT_BORDER,
        highlight: { background: COLOR_WPI_CRIMSON, border: COLOR_WPI_CRIMSON },
        hover: { background: '#f8fafc', border: COLOR_WPI_CRIMSON }
      },
      font: { color: isAnchored ? COLOR_ANCHOR_GOLD : COLOR_DEFAULT_TEXT, size: isAnchored ? 15 : 13, face: 'Inter', weight: '600', strokeWidth: 3, strokeColor: '#ffffff' },
      size: isAnchored ? 20 : 14,
      hidden: false
    });
  });

  const edgeUpdates = [];
  edgesDataSet.forEach(edge => {
    edgeUpdates.push({
      id: edge.id,
      color: { color: '#cbd5e1', highlight: COLOR_WPI_CRIMSON },
      width: 1.2
    });
  });

  nodesDataSet.update(nodeUpdates);
  edgesDataSet.update(edgeUpdates);
}

// Toggle Course Anchor
function toggleAnchorCourse(code) {
  if (anchoredCourseCodes.has(code)) {
    anchoredCourseCodes.delete(code);
  } else {
    anchoredCourseCodes.add(code);
  }
  updateAnchoredUI();
  if (currentSelectedCourse) {
    selectCourse(currentSelectedCourse);
  } else {
    selectCourse(code);
  }
}

// Clear All Anchored Courses
function clearAllAnchors() {
  anchoredCourseCodes.clear();
  updateAnchoredUI();
  if (currentSelectedCourse) {
    selectCourse(currentSelectedCourse);
  } else {
    clearHighlightPath();
  }
}

// Update Anchored Courses Floating Control Bar UI
function updateAnchoredUI() {
  const container = document.getElementById('anchored-container');
  if (!container) return;

  if (anchoredCourseCodes.size === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  const pillsHTML = Array.from(anchoredCourseCodes).map(code => `
    <span class="anchor-pill" onclick="toggleAnchorCourse('${code}')">
      ⚓ ${code} &times;
    </span>
  `).join('');

  container.innerHTML = `
    <span>Anchored Paths:</span>
    ${pillsHTML}
    <button class="btn-xs" style="margin-left: 4px;" onclick="clearAllAnchors()">Clear All</button>
  `;
  container.style.display = 'flex';
}

// Toggle Recursive Tree Unwinder for Prerequisites
function toggleShowAllPrereqs(code) {
  showAllPrereqsActive = !showAllPrereqsActive;
  selectCourse(code);
}

// Select Course & Display Details with Auto-Framing
function selectCourse(code) {
  const node = rawGraphData[code];
  if (!node) return;

  if (currentSelectedCourse !== code) {
    showAllPrereqsActive = false; // Reset unwinder on new course selection
  }

  currentSelectedCourse = code;

  const searchInput = document.getElementById('search-input');
  if (searchInput) searchInput.value = code;

  const dropdown = document.getElementById('search-dropdown');
  if (dropdown) dropdown.style.display = 'none';

  const activeNodeIds = highlightCoursePath(code);

  if (activeNodeIds && activeNodeIds.size > 0) {
    network.fit({
      nodes: Array.from(activeNodeIds),
      animation: { duration: 350, easingFunction: 'easeInOutQuad' }
    });
  } else {
    network.focus(code, { scale: 1.1, animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
  }

  renderCourseDetails(node);
}

// HOVERABLE SIDEBAR BADGE POPOVER TOOLTIP ENGINE
function showBadgeTooltip(e, code) {
  const node = rawGraphData[code];
  if (!node) return;

  const tooltip = document.getElementById('badge-tooltip');
  if (!tooltip) return;

  const prereqText = (node.prerequisites && node.prerequisites.length > 0)
    ? node.prerequisites.join(', ')
    : 'None';

  tooltip.innerHTML = `
    <div class="badge-tooltip-code">${node.course_code || code}</div>
    <div class="badge-tooltip-title">${node.course_name || 'Course Title'}</div>
    <div class="badge-tooltip-meta"><strong>Dept:</strong> ${node.department_code || 'N/A'} | <strong>Credits:</strong> ${node.min_credits || '3.0'}</div>
    ${node.raw_prerequisite_text ? `<div class="badge-tooltip-desc">${node.raw_prerequisite_text}</div>` : ''}
    <div class="badge-tooltip-prereqs"><strong>Prerequisites:</strong> ${prereqText}</div>
  `;

  tooltip.style.display = 'block';
  moveBadgeTooltip(e);
}

function moveBadgeTooltip(e) {
  const tooltip = document.getElementById('badge-tooltip');
  if (!tooltip || tooltip.style.display === 'none') return;
  const padding = 15;
  let left = e.clientX + padding;
  let top = e.clientY + padding;

  if (left + 300 > window.innerWidth) {
    left = e.clientX - 310;
  }
  if (top + 180 > window.innerHeight) {
    top = e.clientY - 190;
  }

  tooltip.style.left = left + 'px';
  tooltip.style.top = top + 'px';
}

function hideBadgeTooltip() {
  const tooltip = document.getElementById('badge-tooltip');
  if (tooltip) tooltip.style.display = 'none';
}

// Render Details Sidebar Panel with Visual OR/AND Group Rendering & Tree Unwinder
function renderCourseDetails(node) {
  const panel = document.getElementById('details-panel');
  const isAnchored = anchoredCourseCodes.has(node.course_code);

  let prereqHTML = '';

  if (showAllPrereqsActive) {
    const treeObj = getAllUpstreamPrereqs(node.course_code);
    if (Object.keys(treeObj.resultByTier).length > 0) {
      const tierHTMLs = Object.entries(treeObj.resultByTier).sort((a,b) => Number(a[0]) - Number(b[0])).map(([depthStr, pCodes]) => {
        const depth = Number(depthStr);
        const tierLabel = (depth === 1) ? 'Tier 1 (Direct Prerequisites)' : `Tier ${depth} (Upstream Prerequisites)`;
        const badges = pCodes.map(p => `
          <span class="badge badge-prereq" 
                onclick="selectCourse('${p}')"
                onmouseenter="showBadgeTooltip(event, '${p}')"
                onmousemove="moveBadgeTooltip(event)"
                onmouseleave="hideBadgeTooltip()">${p}</span>
        `).join(' ');

        return `
          <div class="depth-tier-block">
            <div class="depth-tier-title">${tierLabel}</div>
            <div class="badge-list">${badges}</div>
          </div>
        `;
      });
      prereqHTML = tierHTMLs.join('');
    } else {
      prereqHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">No upstream prerequisites.</span>';
    }
  } else if (node.prerequisites_structured && node.prerequisites_structured.length > 0) {
    const topConnector = (node.prerequisites_structured[0] && node.prerequisites_structured[0].connector === 'OR') ? 'OR' : 'AND';

    const groupHTMLs = node.prerequisites_structured.map((group, idx) => {
      const type = group.type || 'AND';
      const isOrGroup = (type === 'OR' && group.courses.length > 1);

      const badges = group.courses.map(p => `
        <span class="badge badge-prereq" 
              onclick="selectCourse('${p}')"
              onmouseenter="showBadgeTooltip(event, '${p}')"
              onmousemove="moveBadgeTooltip(event)"
              onmouseleave="hideBadgeTooltip()">${p}</span>
      `).join(isOrGroup ? ' <span class="or-divider-badge">OR</span> ' : ' ');

      return `
        <div class="prereq-group-box ${isOrGroup ? 'or-group' : 'and-group'}">
          ${isOrGroup ? '<div class="prereq-group-title">Any One Of:</div>' : (node.prerequisites_structured.length > 1 ? '<div class="prereq-group-title req-title">Required:</div>' : '')}
          <div class="badge-list">${badges}</div>
        </div>
      `;
    });

    const connectorHTML = (topConnector === 'OR')
      ? '<div class="or-connector">— OR —</div>'
      : '<div class="and-connector">— AND —</div>';

    prereqHTML = groupHTMLs.join(connectorHTML);
  } else if ((node.prerequisites || []).length > 0) {
    prereqHTML = `
      <div class="badge-list">
        ${node.prerequisites.map(p => `
          <span class="badge badge-prereq" 
                onclick="selectCourse('${p}')"
                onmouseenter="showBadgeTooltip(event, '${p}')"
                onmousemove="moveBadgeTooltip(event)"
                onmouseleave="hideBadgeTooltip()">${p}</span>
        `).join('')}
      </div>
    `;
  } else {
    prereqHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">None</span>';
  }

  const unlockBadges = (node.prerequisite_for || []).length > 0
    ? node.prerequisite_for.map(u => `
        <span class="badge badge-unlock" 
              onclick="selectCourse('${u}')"
              onmouseenter="showBadgeTooltip(event, '${u}')"
              onmousemove="moveBadgeTooltip(event)"
              onmouseleave="hideBadgeTooltip()">${u}</span>
      `).join('')
    : '<span style="color: var(--text-muted); font-size: 0.8rem;">None</span>';

  const aliasBadges = (node.aliases || []).length > 0
    ? node.aliases.map(a => `
        <span class="badge badge-alias" 
              onclick="selectCourse('${a}')"
              onmouseenter="showBadgeTooltip(event, '${a}')"
              onmousemove="moveBadgeTooltip(event)"
              onmouseleave="hideBadgeTooltip()">${a}</span>
      `).join('')
    : '<span style="color: var(--text-muted); font-size: 0.8rem;">None</span>';

  const hasPrereqs = (node.prerequisites || []).length > 0;

  panel.innerHTML = `
    <div class="course-card-header">
      <div class="course-header-top">
        <div class="course-code-tag ${isAnchored ? 'anchored' : ''}">${node.course_code} ${isAnchored ? '⚓' : ''}</div>
        <button class="btn-xs btn-anchor ${isAnchored ? 'active' : ''}" onclick="toggleAnchorCourse('${node.course_code}')">
          ${isAnchored ? '⚓ Unanchor' : '⚓ Anchor Path'}
        </button>
      </div>
      <div class="course-title-text">${node.course_name || 'Course Title'}</div>
      <div class="meta-row">
        <span><strong>Department:</strong> ${node.department_code || 'N/A'}</span>
        <span><strong>Credits:</strong> ${node.min_credits || '3.0'}</span>
      </div>
    </div>

    <div class="detail-block">
      <div class="detail-block-header">
        <div class="detail-block-label">Prerequisites Required</div>
        ${hasPrereqs ? `
          <button class="btn-xs ${showAllPrereqsActive ? 'active' : ''}" onclick="toggleShowAllPrereqs('${node.course_code}')">
            ${showAllPrereqsActive ? 'Collapse Tree' : 'Show All (Tree)'}
          </button>
        ` : ''}
      </div>
      ${prereqHTML}
    </div>

    <div class="detail-block">
      <div class="detail-block-label">Unlocks Courses</div>
      <div class="badge-list">${unlockBadges}</div>
    </div>

    <div class="detail-block">
      <div class="detail-block-label">Aliases / Cross-Listed</div>
      <div class="badge-list">${aliasBadges}</div>
    </div>

    ${node.raw_prerequisite_text ? `
      <div class="detail-block">
        <div class="detail-block-label">Prerequisite Statement</div>
        <div class="description-text">${node.raw_prerequisite_text}</div>
      </div>
    ` : ''}

    ${node.raw_alias_text ? `
      <div class="detail-block">
        <div class="detail-block-label">Notes & Restrictions</div>
        <div class="description-text">${node.raw_alias_text}</div>
      </div>
    ` : ''}
  `;
}

// Department Selector
function populateDepartmentSelect(graphData) {
  const select = document.getElementById('dept-select');
  const depts = Array.from(new Set(Object.values(graphData).map(n => n.department_code || 'OTHER'))).sort();

  depts.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d;
    select.appendChild(opt);
  });
}

// Render Department Legend
function renderLegend(graphData) {
  const grid = document.getElementById('legend-grid');
  const depts = Array.from(new Set(Object.values(graphData).map(n => n.department_code || 'OTHER'))).sort();

  grid.innerHTML = depts.map(d => `
    <div class="legend-item" onclick="filterDepartment('${d}')">
      <span class="legend-dot"></span>
      <span>${d}</span>
    </div>
  `).join('');
}

// FILTER DEPARTMENT WITH DYNAMIC AUTO-FIT & AUTO-CENTERING
function filterDepartment(dept) {
  document.getElementById('dept-select').value = dept;
  const updates = [];
  const visibleNodeIds = [];

  if (dept === 'ALL') {
    nodesDataSet.forEach(n => {
      updates.push({ id: n.id, hidden: false });
      visibleNodeIds.push(n.id);
    });
  } else {
    nodesDataSet.forEach(n => {
      const isVisible = (n.department === dept);
      updates.push({ id: n.id, hidden: !isVisible });
      if (isVisible) visibleNodeIds.push(n.id);
    });
  }

  nodesDataSet.update(updates);

  if (visibleNodeIds.length > 0) {
    setTimeout(() => {
      network.fit({
        nodes: visibleNodeIds,
        animation: {
          duration: 400,
          easingFunction: 'easeInOutQuad'
        }
      });
    }, 50);
  }
}

// IMMEDIATE KEYPRESS NAVIGATION & SEARCH HANDLER
function handleSearchInput(event) {
  const dropdown = document.getElementById('search-dropdown');
  const items = dropdown.querySelectorAll('.search-item');

  // Handle ArrowDown on immediate keypress
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    if (currentSearchMatches.length === 0) return;
    searchSelectedIndex = (searchSelectedIndex + 1) % currentSearchMatches.length;
    updateSearchHighlight(items);
    return;
  }

  // Handle ArrowUp on immediate keypress
  if (event.key === 'ArrowUp') {
    event.preventDefault();
    if (currentSearchMatches.length === 0) return;
    searchSelectedIndex = (searchSelectedIndex - 1 + currentSearchMatches.length) % currentSearchMatches.length;
    updateSearchHighlight(items);
    return;
  }

  // Handle Enter on immediate keypress
  if (event.key === 'Enter') {
    event.preventDefault();
    if (searchSelectedIndex >= 0 && searchSelectedIndex < currentSearchMatches.length) {
      selectCourse(currentSearchMatches[searchSelectedIndex].course_code);
    } else if (currentSearchMatches.length > 0) {
      selectCourse(currentSearchMatches[0].course_code);
    }
    dropdown.style.display = 'none';
    searchSelectedIndex = -1;
    return;
  }

  // Handle Escape on immediate keypress
  if (event.key === 'Escape') {
    dropdown.style.display = 'none';
    searchSelectedIndex = -1;
    return;
  }

  // Character input - evaluate input value on keypress
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    const query = event.target.value.toUpperCase().trim();

    if (!query || query.length < 2) {
      dropdown.style.display = 'none';
      currentSearchMatches = [];
      searchSelectedIndex = -1;
      return;
    }

    currentSearchMatches = Object.values(rawGraphData).filter(n =>
      n.course_code.includes(query) || (n.course_name && n.course_name.toUpperCase().includes(query))
    ).slice(0, 8);

    searchSelectedIndex = -1;

    if (currentSearchMatches.length > 0) {
      dropdown.innerHTML = currentSearchMatches.map((m, idx) => `
        <div class="search-item" data-index="${idx}" onclick="selectCourse('${m.course_code}')">
          <strong>${m.course_code}</strong>: ${m.course_name || ''}
        </div>
      `).join('');
      dropdown.style.display = 'block';
    } else {
      dropdown.style.display = 'none';
    }
  }, 100);
}

// Update Active Keyboard Highlight Item
function updateSearchHighlight(items) {
  items.forEach((item, idx) => {
    if (idx === searchSelectedIndex) {
      item.classList.add('active');
      item.scrollIntoView({ block: 'nearest' });
    } else {
      item.classList.remove('active');
    }
  });
}

// Reset View
function resetView() {
  document.getElementById('search-input').value = '';
  document.getElementById('dept-select').value = 'ALL';
  const dropdown = document.getElementById('search-dropdown');
  if (dropdown) dropdown.style.display = 'none';
  filterDepartment('ALL');
  clearAllAnchors();
  clearHighlightPath();
  network.fit({ animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
}

// Initialize on DOM Load
document.addEventListener('DOMContentLoaded', initApp);
