/**
 * WPI Course Graph & Planner Application Logic
 * Powered by Flagger Academic Engine & Vis.js
 * Path Walking & Recursive Prerequisite Tree Unwinding
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
let showAllPrereqsActive = false;
let isPhysicsEnabled = false;

// ============================================================================
// CENTRAL PHYSICS CONFIGURATION
// Edit these parameters to tune graph physics behavior across the application.
// ============================================================================
const PHYSICS_CONFIG = {
  department: {
    gravitationalConstant: -25, // Gentle repulsion force between department nodes
    centralGravity: 0.04,       // Steady inward attraction to department center
    springLength: 75,           // Resting distance between connected courses
    springConstant: 0.06,       // Smooth spring stiffness
    damping: 0.55,              // High friction to absorb motion and eliminate jitter
    avoidOverlap: 0.8           // Prevent node overlaps smoothly
  },
  full: {
    gravitationalConstant: -35, // Repulsion force for full campus graph
    centralGravity: 0.005,      // Inward attraction to canvas center
    springLength: 110,          // Resting distance for full graph
    springConstant: 0.05,       // Stiffness of full graph spring connections
    damping: 0.5,               // High friction to prevent vibration
    avoidOverlap: 0.5           // Prevent node overlaps
  }
};

const COLOR_DEFAULT_NODE = '#fcfaf6';     // Soft warm cream porcelain
const COLOR_DEFAULT_BORDER = '#94a3b8';   // Clean slate taupe border
const COLOR_DEFAULT_TEXT = '#2b3648';     // Deep espresso slate text
const COLOR_DEFAULT_STROKE = '#f5f0e6';   // Matching champagne halo
const COLOR_DEFAULT_EDGE = '#d4ceb8';     // Soft warm parchment edges

const COLOR_HOVER_NODE = '#fff5f5';       // Soft crimson silk hover background
const COLOR_WPI_CRIMSON = '#AC2B37';
const COLOR_PREREQ_ANCESTOR = '#4338ca';   // Deep Royal Indigo for Direct Prerequisites
const COLOR_UNLOCK_DESCENDANT = '#0284c7';  // Ocean Sky Blue for Direct Unlocked Courses

// Initialize Application
async function initApp() {
  try {
    if (typeof window.rawEmbeddedNodes !== 'undefined' && Array.isArray(window.rawEmbeddedNodes)) {
      rawGraphData = {};
      window.rawEmbeddedNodes.forEach(n => {
        rawGraphData[n.id] = {
          course_code: n.id,
          course_name: n.name,
          department_code: n.department,
          department: n.department,
          prerequisites: n.prerequisites || [],
          prerequisites_structured: n.prerequisites_structured || [],
          prerequisite_for: n.prerequisite_for || [],
          aliases: n.aliases || [],
          raw_prerequisite_text: n.description || '',
          min_credits: n.min_credits || '3.0'
        };
      });
    } else {
      const response = await fetch('data/wpi_course_graph.json');
      if (!response.ok) {
        throw new Error(`Failed to load graph data: ${response.status}`);
      }
      rawGraphData = await response.json();
    }

    renderStats(rawGraphData);
    setupNetwork(rawGraphData);
    populateDepartmentSelect(rawGraphData);
    renderDepartmentCourses('ALL', null);

    // Hide search dropdown on click outside
    document.addEventListener('click', function (e) {
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
        hover: { background: COLOR_HOVER_NODE, border: COLOR_WPI_CRIMSON }
      },
      font: {
        color: COLOR_DEFAULT_TEXT,
        size: 13,
        face: 'Inter',
        weight: '600',
        strokeWidth: 3,
        strokeColor: COLOR_DEFAULT_STROKE
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
            color: { color: COLOR_DEFAULT_EDGE, highlight: COLOR_WPI_CRIMSON },
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
  const data = { nodes: nodesDataSet, edges: edgesDataSet };

  const options = {
    nodes: {
      shape: 'dot',
      size: 14,
      borderWidth: 1.5
    },
    edges: {
      smooth: { type: 'continuous', roundness: 0.3 }
    },
    physics: {
      enabled: true,
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: PHYSICS_CONFIG.full.gravitationalConstant,
        centralGravity: PHYSICS_CONFIG.full.centralGravity,
        springLength: PHYSICS_CONFIG.full.springLength,
        springConstant: PHYSICS_CONFIG.full.springConstant,
        damping: PHYSICS_CONFIG.full.damping
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
      dragView: false,
      zoomView: true
    }
  };

  network = new vis.Network(container, data, options);

  network.once('stabilizationIterationsDone', function () {
    network.setOptions({ physics: { enabled: isPhysicsEnabled } });
  });

  // Right-Click Drag Canvas Panning Handler
  let isRightDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let initialViewPos = { x: 0, y: 0 };

  container.addEventListener('contextmenu', function (e) {
    e.preventDefault();
  });

  container.addEventListener('mousedown', function (e) {
    if (e.button === 2) {
      isRightDragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      initialViewPos = network.getViewPosition();
    }
  });

  document.addEventListener('mousemove', function (e) {
    if (isRightDragging && network) {
      const dx = e.clientX - dragStartX;
      const dy = e.clientY - dragStartY;
      const scale = network.getScale();
      network.moveTo({
        position: {
          x: initialViewPos.x - (dx / scale),
          y: initialViewPos.y - (dy / scale)
        }
      });
    }
  });

  document.addEventListener('mouseup', function (e) {
    if (e.button === 2) {
      isRightDragging = false;
    }
  });

  // Disable physics immediately after initial stabilization & record base positions
  network.once('stabilizationIterationsDone', function () {
    network.setOptions({ physics: { enabled: false } });
    nodesDataSet.forEach(node => {
      const pos = network.getPosition(node.id);
      originalNodePositions[node.id] = { x: pos.x, y: pos.y };
    });
  });

  // Left-Click: Select Course
  network.on('click', function (params) {
    if (params.nodes.length > 0) {
      const code = params.nodes[0];
      selectCourse(code);
    } else {
      clearHighlightPath();
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

// RADIAL FOCUS LAYOUT ENGINE WITH RECURSIVE TREE UNWINDING
function highlightCoursePath(targetCode) {
  const targetNode = rawGraphData[targetCode];
  if (!targetNode) return new Set();

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

          nodeUpdates.push({
            id: pId,
            label: pId,
            x: posX,
            y: posY,
            color: { background: COLOR_PREREQ_ANCESTOR, border: '#312e81' },
            font: { color: COLOR_PREREQ_ANCESTOR, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' },
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

        nodeUpdates.push({
          id: prereqId,
          label: prereqId,
          x: posX,
          y: posY,
          color: { background: COLOR_PREREQ_ANCESTOR, border: '#312e81' },
          font: { color: COLOR_PREREQ_ANCESTOR, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' },
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

      nodeUpdates.push({
        id: unlockId,
        label: unlockId,
        x: posX,
        y: posY,
        color: { background: COLOR_UNLOCK_DESCENDANT, border: '#0369a1' },
        font: { color: COLOR_UNLOCK_DESCENDANT, size: 14, face: 'Inter', weight: '700', strokeWidth: 3, strokeColor: '#ffffff' },
        size: unlockNodeSize,
        hidden: false
      });
    });

    // Selected Target Node
    nodeUpdates.push({
      id: targetCode,
      label: targetCode,
      x: centerPos.x,
      y: centerPos.y,
      color: { background: COLOR_WPI_CRIMSON, border: '#8B222C' },
      font: { color: COLOR_WPI_CRIMSON, size: 16, face: 'Inter', weight: '700', strokeWidth: 4, strokeColor: '#ffffff' },
      size: 24,
      hidden: false
    });
  }

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

  // STRICT EDGE FILTERING: Highlight Prereq->Target, Target->Unlock, and Prereq->Prereq chains only
  const prereqSet = new Set(directPrereqs);
  const edgeUpdates = [];

  edgesDataSet.forEach(edge => {
    const isFromTarget = (edge.from === targetCode);
    const isToTarget = (edge.to === targetCode);
    const isFromPrereq = prereqSet.has(edge.from);
    const isToPrereq = prereqSet.has(edge.to);

    const isHighlightEdge = (isToTarget && isFromPrereq) || isFromTarget || (isFromPrereq && isToPrereq);

    if (isHighlightEdge) {
      edgeUpdates.push({
        id: edge.id,
        color: { color: isFromTarget ? COLOR_UNLOCK_DESCENDANT : COLOR_PREREQ_ANCESTOR, highlight: COLOR_WPI_CRIMSON },
        width: 3.2,
        hidden: false
      });
    } else {
      edgeUpdates.push({
        id: edge.id,
        color: { color: 'rgba(226, 221, 211, 0.08)' },
        width: 0.5,
        hidden: true
      });
    }
  });

  nodesDataSet.update(nodeUpdates);
  edgesDataSet.update(edgeUpdates);

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
  currentSelectedCourse = null;
  hideBadgeTooltip();

  const panel = document.getElementById('details-panel');
  if (panel) {
    panel.innerHTML = '<p class="placeholder-msg">Click any course node in the graph to view prerequisites, unlocked courses, and details.</p>';
  }

  const currentDept = document.getElementById('dept-select') ? document.getElementById('dept-select').value : 'ALL';
  renderDepartmentCourses(currentDept, null);

  const nodeUpdates = [];
  nodesDataSet.forEach(node => {
    nodeUpdates.push({
      id: node.id,
      label: node.id,
      color: {
        background: COLOR_DEFAULT_NODE,
        border: COLOR_DEFAULT_BORDER,
        highlight: { background: COLOR_WPI_CRIMSON, border: COLOR_WPI_CRIMSON },
        hover: { background: COLOR_HOVER_NODE, border: COLOR_WPI_CRIMSON }
      },
      font: { color: COLOR_DEFAULT_TEXT, size: 13, face: 'Inter', weight: '600', strokeWidth: 3, strokeColor: COLOR_DEFAULT_STROKE },
      size: 14,
      hidden: false
    });
  });

  const edgeUpdates = [];
  edgesDataSet.forEach(edge => {
    edgeUpdates.push({
      id: edge.id,
      color: { color: COLOR_DEFAULT_EDGE, highlight: COLOR_WPI_CRIMSON },
      width: 1.2,
      hidden: false
    });
  });

  nodesDataSet.update(nodeUpdates);
  edgesDataSet.update(edgeUpdates);
}

// Toggle Recursive Tree Unwinder for Prerequisites
function toggleShowAllPrereqs(code) {
  showAllPrereqsActive = !showAllPrereqsActive;
  selectCourse(code);
}

// Select Course & Display Details with Auto-Framing
function selectCourse(code) {
  hideBadgeTooltip();

  // Freeze physics when inspecting a single course node
  network.setOptions({ physics: { enabled: false } });
  network.stopSimulation();

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

  const dept = node.department_code || node.department;
  if (dept) {
    renderDepartmentCourses(dept, code);
  }
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

  let prereqHTML = '';

  if (showAllPrereqsActive) {
    const treeObj = getAllUpstreamPrereqs(node.course_code);
    if (Object.keys(treeObj.resultByTier).length > 0) {
      const tierHTMLs = Object.entries(treeObj.resultByTier).sort((a, b) => Number(a[0]) - Number(b[0])).map(([depthStr, pCodes]) => {
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
    const reqCourses = [];
    const orGroups = [];

    node.prerequisites_structured.forEach(group => {
      const type = group.type || 'AND';
      const courses = group.courses || [];
      if (type === 'OR' && courses.length > 1) {
        orGroups.push(courses);
      } else {
        courses.forEach(c => {
          if (!reqCourses.includes(c)) reqCourses.push(c);
        });
      }
    });

    const blocksHTML = [];

    if (reqCourses.length > 0) {
      const reqBadges = reqCourses.map(p => `
        <span class="badge badge-prereq" 
              onclick="selectCourse('${p}')"
              onmouseenter="showBadgeTooltip(event, '${p}')"
              onmousemove="moveBadgeTooltip(event)"
              onmouseleave="hideBadgeTooltip()">${p}</span>
      `).join(' ');

      blocksHTML.push(`
        <div class="prereq-group-box and-group">
          ${(orGroups.length > 0 || reqCourses.length > 1) ? '<div class="prereq-group-title req-title">Required:</div>' : ''}
          <div class="badge-list">${reqBadges}</div>
        </div>
      `);
    }

    orGroups.forEach(courses => {
      const badges = courses.map(p => `
        <span class="badge badge-prereq" 
              onclick="selectCourse('${p}')"
              onmouseenter="showBadgeTooltip(event, '${p}')"
              onmousemove="moveBadgeTooltip(event)"
              onmouseleave="hideBadgeTooltip()">${p}</span>
      `).join(' <span class="or-divider-badge">OR</span> ');

      blocksHTML.push(`
        <div class="prereq-group-box or-group">
          <div class="prereq-group-title">Any One Of:</div>
          <div class="badge-list">${badges}</div>
        </div>
      `);
    });

    prereqHTML = blocksHTML.join('');
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
        <div class="course-code-tag">${node.course_code}</div>
      </div>
      <div class="course-title-text">${node.course_name || 'Course Title'}</div>
      <div class="meta-row">
        <span><strong>Department:</strong> ${node.department_code || 'N/A'}</span>
        <span><strong>Credits:</strong> ${node.min_credits || '3.0'}</span>
      </div>
    </div>

    <div class="detail-block">
      <div class="detail-block-header">
        <div class="detail-block-label">Prerequisites Recommended</div>
        ${hasPrereqs ? `
          <button class="btn-xs ${showAllPrereqsActive ? 'active' : ''}" onclick="toggleShowAllPrereqs('${node.course_code}')">
            ${showAllPrereqsActive ? 'Collapse Tree' : 'Show All (Unwind)'}
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

function extractCourseSortWeight(code) {
  const parts = (code || '').trim().split(/\s+/);
  const numToken = parts[1] || parts[0] || '';
  const match = numToken.match(/\d+/);
  if (!match) return 999999;

  const digits = match[0];
  const num = parseInt(digits, 10);

  if (numToken.length >= 4) {
    if (digits.length === 3) {
      return num * 10 + 5;
    }
    return num;
  }

  if (numToken.length === 3) {
    return 10000 + num;
  }

  return 20000 + num;
}

// Render Scrollable Department Courses Directory
function renderDepartmentCourses(deptCode, activeCourseCode) {
  const titleEl = document.getElementById('dept-courses-title');
  const container = document.getElementById('dept-courses-list');
  const showAllBtn = document.getElementById('dept-show-all-btn');

  if (!container) return;

  if (!deptCode || deptCode === 'ALL') {
    if (titleEl) titleEl.textContent = 'Department Courses';
    if (showAllBtn) showAllBtn.style.display = 'none';
    container.innerHTML = '<p class="placeholder-msg">Select a department or click a course to view all courses in that department.</p>';
    return;
  }

  if (showAllBtn) {
    showAllBtn.style.display = 'inline-flex';
    showAllBtn.onclick = () => filterDepartment(deptCode);
  }

  const deptCourses = Object.values(rawGraphData).filter(c => {
    const dept = c.department_code || c.department || '';
    return dept === deptCode;
  });

  deptCourses.sort((a, b) => {
    const codeA = a.course_code || a.id || '';
    const codeB = b.course_code || b.id || '';
    const weightA = extractCourseSortWeight(codeA);
    const weightB = extractCourseSortWeight(codeB);
    if (weightA !== weightB) return weightA - weightB;
    return codeA.localeCompare(codeB);
  });

  if (titleEl) {
    titleEl.textContent = `${deptCode} Dept (${deptCourses.length})`;
  }

  if (deptCourses.length === 0) {
    container.innerHTML = '<p class="placeholder-msg">No courses found in this department.</p>';
    return;
  }

  container.innerHTML = deptCourses.map(c => {
    const code = c.course_code || c.id;
    const name = c.course_name || c.name || '';
    const isActive = (code === activeCourseCode);

    return `
      <div class="dept-course-item ${isActive ? 'active' : ''}" data-code="${code}" onclick="selectCourse('${code}')">
        <span class="dept-course-code">${code}</span>
        <span class="dept-course-title" title="${name}">${name}</span>
      </div>
    `;
  }).join('');

  if (activeCourseCode) {
    const activeEl = container.querySelector(`.dept-course-item[data-code="${activeCourseCode}"]`);
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' });
    }
  }
}

// FILTER DEPARTMENT WITH DYNAMIC AUTO-FIT, TIGHT CLUSTERING & AUTO-CENTERING
function filterDepartment(dept) {
  hideBadgeTooltip();
  document.getElementById('dept-select').value = dept;
  renderDepartmentCourses(dept, null);
  const updates = [];
  const visibleNodeIds = [];

  if (dept === 'ALL') {
    restoreOriginalPositions();
    nodesDataSet.forEach(n => {
      updates.push({ id: n.id, hidden: false });
      visibleNodeIds.push(n.id);
    });
  } else {
    const deptNodeIds = [];
    nodesDataSet.forEach(n => {
      const isVisible = (n.department === dept);
      updates.push({ id: n.id, hidden: !isVisible });
      if (isVisible) {
        visibleNodeIds.push(n.id);
        deptNodeIds.push(n.id);
      }
    });

    let sumX = 0, sumY = 0, count = 0;
    deptNodeIds.forEach(id => {
      const pos = originalNodePositions[id] || network.getPosition(id);
      if (pos) {
        sumX += pos.x;
        sumY += pos.y;
        count++;
      }
    });

    if (count > 0) {
      const avgX = sumX / count;
      const avgY = sumY / count;

      const connectedNodeIds = new Set();
      edgesDataSet.forEach(e => {
        if (!e.hidden) {
          connectedNodeIds.add(e.from);
          connectedNodeIds.add(e.to);
        }
      });

      deptNodeIds.forEach(id => {
        const pos = originalNodePositions[id] || network.getPosition(id);
        if (pos) {
          const isConnected = connectedNodeIds.has(id);
          const factor = isConnected ? 0.28 : 0.12;
          updates.push({
            id: id,
            hidden: false,
            x: avgX + (pos.x - avgX) * factor,
            y: avgY + (pos.y - avgY) * factor
          });
        }
      });
    }
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

      if (dept !== 'ALL') {
        setTimeout(() => {
          const currentScale = network.getScale();
          if (currentScale < 0.8) {
            const pos = network.getViewPosition();
            network.moveTo({
              position: pos,
              scale: 0.85,
              animation: { duration: 300, easingFunction: 'easeInOutQuad' }
            });
          }
        }, 420);
      }
    }, 50);
  }

  // Manage physics state for department courses with tighter springs
  if (isPhysicsEnabled) {
    const cfg = (dept && dept !== 'ALL') ? PHYSICS_CONFIG.department : PHYSICS_CONFIG.full;
    network.setOptions({
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: cfg.gravitationalConstant,
          centralGravity: cfg.centralGravity,
          springLength: cfg.springLength,
          springConstant: cfg.springConstant,
          damping: cfg.damping,
          avoidOverlap: cfg.avoidOverlap || 0.8
        },
        stabilization: { enabled: false }
      }
    });
    network.startSimulation();
  } else {
    network.setOptions({ physics: { enabled: false } });
    network.stopSimulation();
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
  hideBadgeTooltip();
  document.getElementById('search-input').value = '';
  document.getElementById('dept-select').value = 'ALL';
  const dropdown = document.getElementById('search-dropdown');
  if (dropdown) dropdown.style.display = 'none';
  filterDepartment('ALL');
  clearHighlightPath();
  network.fit({ animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
}

// Help Modal Controls
function openHelpModal() {
  const overlay = document.getElementById('help-modal-overlay');
  if (overlay) overlay.classList.add('active');
}

function closeHelpModal() {
  const overlay = document.getElementById('help-modal-overlay');
  if (overlay) overlay.classList.remove('active');
}

function handleModalOverlayClick(e) {
  if (e.target && e.target.id === 'help-modal-overlay') {
    closeHelpModal();
  }
}

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    closeHelpModal();
  }
});

// Toggle Live Graph Physics
function togglePhysics() {
  isPhysicsEnabled = !isPhysicsEnabled;
  const btn = document.getElementById('physics-toggle-btn');

  if (isPhysicsEnabled) {
    if (btn) {
      btn.textContent = 'Physics: ON';
      btn.classList.add('active');
    }
    const currentDept = document.getElementById('dept-select') ? document.getElementById('dept-select').value : 'ALL';
    const cfg = (currentDept && currentDept !== 'ALL') ? PHYSICS_CONFIG.department : PHYSICS_CONFIG.full;

    network.setOptions({
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: cfg.gravitationalConstant,
          centralGravity: cfg.centralGravity,
          springLength: cfg.springLength,
          springConstant: cfg.springConstant,
          damping: cfg.damping,
          avoidOverlap: cfg.avoidOverlap || 0.8
        },
        stabilization: { enabled: false }
      }
    });
    network.startSimulation();
  } else {
    if (btn) {
      btn.textContent = 'Physics: OFF';
      btn.classList.remove('active');
    }
    network.setOptions({
      physics: { enabled: false }
    });
    network.stopSimulation();
  }
}

// Initialize on DOM Load
document.addEventListener('DOMContentLoaded', initApp);
