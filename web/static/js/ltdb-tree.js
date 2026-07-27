(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.LTDBTree = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  function tokenize(input) {
    const tokens = [];
    let index = 0;
    while (index < input.length) {
      const char = input[index];
      if (/\s/.test(char)) {
        index += 1;
      } else if (char === "(" || char === ")") {
        tokens.push({ type: char, value: char });
        index += 1;
      } else if (char === '"') {
        let value = "";
        index += 1;
        while (index < input.length) {
          const next = input[index];
          if (next === "\\") {
            if (index + 1 < input.length) {
              value += input[index + 1];
              index += 2;
            } else {
              index += 1;
            }
          } else if (next === '"') {
            index += 1;
            break;
          } else {
            value += next;
            index += 1;
          }
        }
        tokens.push({ type: "string", value });
      } else {
        let value = "";
        while (
          index < input.length &&
          !/\s/.test(input[index]) &&
          input[index] !== "(" &&
          input[index] !== ")"
        ) {
          value += input[index];
          index += 1;
        }
        tokens.push({ type: "atom", value });
      }
    }
    return tokens;
  }

  function parseList(tokens, state) {
    const list = [];
    state.index += 1;
    while (state.index < tokens.length && tokens[state.index].type !== ")") {
      const token = tokens[state.index];
      if (token.type === "(") {
        list.push(parseList(tokens, state));
      } else {
        list.push(token.value);
        state.index += 1;
      }
    }
    if (state.index >= tokens.length) {
      throw new Error("Unclosed derivation list");
    }
    state.index += 1;
    return list;
  }

  function parseSexp(input) {
    const tokens = tokenize(input);
    if (!tokens.length) {
      throw new Error("Empty derivation");
    }
    const state = { index: 0 };
    const tree = parseList(tokens, state);
    if (state.index !== tokens.length) {
      throw new Error("Unexpected content after derivation");
    }
    return tree;
  }

  function isNumberAtom(value) {
    return /^-?\d+(?:\.\d+)?$/.test(String(value));
  }

  function visibleChildren(items, start) {
    return items.slice(start).filter(Array.isArray).map(toTree);
  }

  function fromDict(node) {
    if (!node || typeof node !== "object") {
      return { name: String(node || ""), leaf: true };
    }
    if (!node.daughters) {
      // preterminal: pydelphin flattens the surface token into `form`;
      // rebuild the lex-type > lex-entry > form chain so the lexical
      // entry and its type stay visible in the tree
      const form = node.form || node.entity || "";
      let tree = { name: form, form, leaf: true };
      if (node.entity && node.entity !== form) {
        tree = { name: node.entity, entity: node.entity, children: [tree] };
      }
      if (node.type) {
        tree = {
          name: node.type,
          entity: node.type,
          type: node.type,
          isLexType: true,
          children: [tree],
        };
      }
      return tree;
    }
    return {
      name: node.entity || "",
      entity: node.entity || "",
      type: node.type || null,
      // word-index span, when the source dict carries one (see toTree
      // below for where these come from on the raw-sexp parsing path)
      start: node.start,
      end: node.end,
      children: node.daughters.map(fromDict),
    };
  }

  function toTree(node) {
    if (!Array.isArray(node)) {
      return { name: String(node), leaf: true };
    }
    if (typeof node[0] === "string" && node[0] && !isNumberAtom(node[0])) {
      if (node.length === 1) {
        return { name: node[0], form: node[0], leaf: true };
      }
      if (node.length >= 3 && !Array.isArray(node[1])) {
        return { name: node[0], form: node[0], leaf: true };
      }
      const children = visibleChildren(node, 1);
      // the outermost root wraps a single UDF-header child with no
      // start/end of its own (it's just a bare category name); derive
      // its span as the envelope of its children's, so root-status
      // constructions can be span-highlighted too
      const starts = children.map((c) => c.start).filter((v) => v !== undefined);
      const ends = children.map((c) => c.end).filter((v) => v !== undefined);
      const start = starts.length ? Math.min(...starts) : undefined;
      const end = ends.length ? Math.max(...ends) : undefined;
      return { name: node[0], entity: node[0], children, start, end };
    }
    const name = String(node[1] || node[0] || "");
    const children = visibleChildren(node, 2);
    // UDF header shape: (id entity score start end daughter...) -- start/end
    // is the node's word-index span, the same 0-based half-open scheme
    // typind.kara/made and sent.wid already use elsewhere in the app.
    // visibleChildren's Array.isArray filter already drops these scalar
    // fields when collecting children regardless of the slice start
    // index, so pulling them out here doesn't disturb that.
    const start = Number.isFinite(Number(node[3])) ? Number(node[3]) : undefined;
    const end = Number.isFinite(Number(node[4])) ? Number(node[4]) : undefined;
    if (!children.length) {
      return { name, leaf: true, start, end };
    }
    return { name, entity: name, children, start, end };
  }

  function maxLeafDepth(node, depth) {
    const children = node.children || node._children || [];
    if (!children.length || node.leaf) {
      return depth;
    }
    return Math.max(...children.map((child) => maxLeafDepth(child, depth + 1)));
  }

  function visibleChildrenFor(node) {
    if (node.collapsed) {
      return [];
    }
    return node.children || [];
  }

  function visibleLeafDepths(node, depth, depths) {
    const children = visibleChildrenFor(node);
    if (node.leaf || !children.length) {
      if (node.leaf) {
        depths.push(depth);
      }
      return;
    }
    children.forEach((child) => visibleLeafDepths(child, depth + 1, depths));
  }

  function countRows(node) {
    const children = visibleChildrenFor(node);
    if (!children.length) {
      node._rows = 1;
      return 1;
    }
    node._rows = children.reduce((total, child) => total + countRows(child), 0);
    return node._rows;
  }

  function collectVisibleNodes(node, nodes, links) {
    nodes.push(node);
    visibleChildrenFor(node).forEach((child) => {
      links.push({ source: node, target: child });
      collectVisibleNodes(child, nodes, links);
    });
  }

  function labelForNode(node, options) {
    if (node.form != null) return node.form;
    if (options && options.showLabels && node.type) return node.type;
    return node.entity || node.name;
  }

  function boxWidthForLabel(label) {
    return Math.max(44, String(label).length * 7 + 18);
  }

  function rootShapePoints(width, height) {
    const left = -width / 2;
    const right = width / 2;
    const top = -height / 2;
    const bottom = height / 2;
    const trimX = Math.min(10, width / 5);
    const trimY = Math.min(5, height / 4);
    return [
      [left + trimX, top],
      [right - trimX, top],
      [right, top + trimY],
      [right, bottom - trimY],
      [right - trimX, bottom],
      [left + trimX, bottom],
      [left, bottom - trimY],
      [left, top + trimY],
    ]
      .map((point) => point.join(","))
      .join(" ");
  }

  function classifyNode(node) {
    if (node.leaf) {
      return "lemma";
    }
    if (node.isLexType) {
      return "lex-type";
    }
    if (
      node.children &&
      node.children.length &&
      node.children.every((child) => child.leaf)
    ) {
      return "lex-entry";
    }
    const name = String(node.entity || node.name || "");
    if (name.startsWith("root_") || name.endsWith("_root")) {
      return "root";
    }
    if (/_([diop]?lr)$/.test(name) || /_(?:d|i|o|p)lr$/.test(name)) {
      return "lex-rule";
    }
    if (name.endsWith("_le") || name.endsWith("_lexent")) {
      return "lex-type";
    }
    return "rule";
  }

  function isHighlightedNode(node, options) {
    if (!options) return false;
    // a specific occurrence, by word-index span (e.g. a deep link from a
    // type's sentence list or the standalone sentence page) -- takes
    // precedence over, and does not fall back to, highlightType below
    if (options.highlightSpan) {
      const { from, to } = options.highlightSpan;
      return node.start === from && node.end === to;
    }
    return Boolean(
      options.highlightType &&
        (node.name === options.highlightType || node.entity === options.highlightType)
    );
  }

  function layoutTree(root, options) {
    const levelHeight = options && options.levelHeight ? options.levelHeight : 64;
    const marginY = options && options.marginY ? options.marginY : 28;
    const nodeSep = options && options.nodeSep ? options.nodeSep : 12;

    let maxNodeWidth = 44;
    (function scanWidths(node) {
      maxNodeWidth = Math.max(maxNodeWidth, boxWidthForLabel(labelForNode(node, options)));
      (node.children || []).forEach(scanWidths);
    }(root));

    const marginX = Math.max(
      options && options.marginX ? options.marginX : 42,
      Math.ceil(maxNodeWidth / 2) + 8
    );

    const leafDepths = [];
    visibleLeafDepths(root, 0, leafDepths);
    const leafBaseline = Math.max(0, ...leafDepths) * levelHeight + marginY;

    // Sequential leaf placement; interior nodes centred over outermost children.
    // After each child is placed, sibling boxes are checked and the right subtree
    // is shifted if it would overlap, with leafX updated so subsequent siblings
    // start after the shifted position.
    let leafX = 0;

    function shiftSubtree(node, delta) {
      node._x += delta;
      visibleChildrenFor(node).forEach((child) => shiftSubtree(child, delta));
    }

    // Depth-matched contour comparison: at each row, record the rightmost right-edge
    // of the left subtree and the leftmost left-edge of the right subtree, then take
    // the maximum required shift across all rows where both subtrees have nodes.
    function contourRight(node, d, acc) {
      const cur = node._x + node._boxWidth / 2;
      acc[d] = acc[d] !== undefined ? Math.max(acc[d], cur) : cur;
      visibleChildrenFor(node).forEach((c) => contourRight(c, d + 1, acc));
      return acc;
    }

    function contourLeft(node, d, acc) {
      const cur = node._x - node._boxWidth / 2;
      acc[d] = acc[d] !== undefined ? Math.min(acc[d], cur) : cur;
      visibleChildrenFor(node).forEach((c) => contourLeft(c, d + 1, acc));
      return acc;
    }

    function requiredShift(leftNode, rightNode) {
      const rc = contourRight(leftNode, 0, {});
      const lc = contourLeft(rightNode, 0, {});
      let shift = 0;
      for (const d of Object.keys(rc)) {
        if (lc[d] !== undefined) {
          shift = Math.max(shift, rc[d] + nodeSep - lc[d]);
        }
      }
      return shift;
    }

    function position(node, depth) {
      node._boxWidth = boxWidthForLabel(labelForNode(node, options));
      node._boxHeight = 24;
      const children = visibleChildrenFor(node);
      if (!children.length) {
        node._x = leafX + node._boxWidth / 2;
        leafX += node._boxWidth + nodeSep;
        node._y = node.leaf ? leafBaseline : marginY + depth * levelHeight;
        return;
      }
      position(children[0], depth + 1);
      for (let i = 1; i < children.length; i++) {
        position(children[i], depth + 1);
        const delta = requiredShift(children[i - 1], children[i]);
        if (delta > 0) {
          shiftSubtree(children[i], delta);
          leafX += delta;
        }
      }
      node._x = (children[0]._x + children[children.length - 1]._x) / 2;
      node._y = marginY + depth * levelHeight;
    }

    position(root, 0);

    // Shift everything right so the leftmost node sits at marginX
    const allNodes = [];
    const allLinks = [];
    collectVisibleNodes(root, allNodes, allLinks);
    const minX = Math.min(...allNodes.map((n) => n._x - n._boxWidth / 2));
    const shift = marginX - minX;
    allNodes.forEach((n) => { n._x += shift; });
    const maxX = Math.max(...allNodes.map((n) => n._x + n._boxWidth / 2));
    const width = Math.max(maxX + marginX, 160);
    const height =
      Math.max(...allNodes.map((n) => n._y), leafBaseline) +
      (options && options.labelHeight ? options.labelHeight : 52);
    const nodes = allNodes;
    const links = allLinks;
    return { height, links, nodes, width };
  }

  function svgElement(name, attrs) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      element.setAttribute(key, String(value));
    });
    return element;
  }

  function ensureStyles() {
    if (document.getElementById("ltdb-tree-style")) {
      return;
    }
    const style = document.createElement("style");
    style.id = "ltdb-tree-style";
    style.textContent = `
      .ltdb-tree-svg { width: 100%; height: auto; overflow: visible; }
      .ltdb-tree-link { fill: none; stroke: #b9c0c7; stroke-width: 1.25; }
      .ltdb-tree-node text { fill: #222; font: 12px sans-serif; }
      .ltdb-tree-node rect,
      .ltdb-tree-node polygon { fill: #fff; stroke: #61748a; stroke-width: 1.25; }
      .ltdb-tree-node.leaf rect { fill: #f4f6f8; stroke: #9aa4af; }
      .ltdb-tree-node.root polygon { fill: #fff1cf; stroke: #a87400; stroke-width: 1.75; }
      .ltdb-tree-node.rule rect { fill: #eaf2ff; stroke: #2f6fb6; }
      .ltdb-tree-node.lex-entry rect { fill: #f8f8f8; stroke: #111; stroke-width: 1.75; }
      .ltdb-tree-node.lex-rule rect { fill: #f4eaff; stroke: #7655a6; }
      .ltdb-tree-node.lex-type rect { fill: #fff0f4; stroke: #b85b73; }
      .ltdb-tree-node.highlight rect,
      .ltdb-tree-node.highlight polygon { fill: #dff5df; stroke: #25853a; stroke-width: 2; }
      .ltdb-tree-node.interactive { cursor: pointer; }
      .ltdb-tree-node.collapsed rect,
      .ltdb-tree-node.collapsed polygon { fill: #d8e9ff; stroke: #2f6fb6; stroke-width: 1.75; }
      .ltdb-tree-node.collapsed.highlight rect,
      .ltdb-tree-node.collapsed.highlight polygon { fill: #c9efc9; stroke: #25853a; }
      .ltdb-tree-node.collapsed text { font-weight: 600; }
      .ltdb-tree-node.leaf text { font-style: italic; }
      .ltdb-tree-node-title { text-anchor: middle; dominant-baseline: central; pointer-events: none; }
    `;
    document.head.appendChild(style);
  }

  function linkPath(link) {
    const srcX = link.source._x;
    const srcY = link.source._y + link.source._boxHeight / 2;
    const tgtX = link.target._x;
    const tgtY = link.target._y - link.target._boxHeight / 2;
    return `M${srcX},${srcY} L${tgtX},${tgtY}`;
  }

  function typeHrefForNode(node, options) {
    const typ = node.entity || node.name;
    if (options && typeof options.typeHref === "function") {
      return options.typeHref(typ, node);
    }
    const suffix = `${encodeURIComponent(typ)}.html`;
    if (options && options.typeBaseHref) {
      return `${options.typeBaseHref.replace(/\/$/, "")}/${suffix}`;
    }
    return suffix;
  }

  function renderTree(container, root, options) {
    ensureStyles();
    container.textContent = "";
    const layout = layoutTree(root, options || {});
    const svg = svgElement("svg", {
      class: "ltdb-tree-svg",
      role: "img",
      viewBox: `0 0 ${Math.ceil(layout.width)} ${Math.ceil(layout.height)}`,
      width: Math.ceil(layout.width),
      height: Math.ceil(layout.height),
    });
    const linkLayer = svgElement("g", { class: "ltdb-tree-links" });
    layout.links.forEach((link) => {
      linkLayer.appendChild(
        svgElement("path", { class: "ltdb-tree-link", d: linkPath(link) })
      );
    });
    svg.appendChild(linkLayer);

    const nodeLayer = svgElement("g", { class: "ltdb-tree-nodes" });
    layout.nodes.forEach((node) => {
      const hasChildren = Boolean(node.children && node.children.length);
      const nodeClass = classifyNode(node);
      const classes = [
        "ltdb-tree-node",
        node.leaf ? "leaf" : "",
        nodeClass,
        isHighlightedNode(node, options || {}) ? "highlight" : "",
        hasChildren ? "collapsible" : "",
        node.leaf ? "" : "interactive",
        node.collapsed ? "collapsed" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const group = svgElement("g", {
        class: classes,
        transform: `translate(${node._x},${node._y})`,
      });
      const openType = () => {
        window.location.href = typeHrefForNode(node, options || {});
      };
      const toggle = () => {
        if (hasChildren) {
          node.collapsed = !node.collapsed;
          renderTree(container, root, options);
        }
      };
      if (!node.leaf) {
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "button");
        group.setAttribute(
          "aria-label",
          `Collapse, expand, or shift-click to open ${node.name}`
        );
        group.addEventListener("click", (event) => {
          if (event.shiftKey) {
            openType();
          } else {
            toggle();
          }
        });
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter" && event.shiftKey) {
            event.preventDefault();
            openType();
          } else if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggle();
          }
        });
      }
      if (nodeClass === "root") {
        group.appendChild(
          svgElement("polygon", {
            points: rootShapePoints(node._boxWidth, node._boxHeight),
          })
        );
      } else {
        group.appendChild(
          svgElement("rect", {
            x: -node._boxWidth / 2,
            y: -node._boxHeight / 2,
            width: node._boxWidth,
            height: node._boxHeight,
            rx: 3,
            ry: 3,
          })
        );
      }
      const text = svgElement("text", {
        class: "ltdb-tree-node-title",
        x: 0,
        y: 0,
      });
      text.textContent = labelForNode(node, options);
      const title = svgElement("title");
      const entityName = node.entity || node.name;
      title.textContent = node.leaf
        ? node.name
        : `${entityName} (${nodeClass}; click to collapse, shift-click to open type)`;
      group.appendChild(title);
      group.appendChild(text);
      nodeLayer.appendChild(group);
    });
    svg.appendChild(nodeLayer);
    container.appendChild(svg);
    return layout;
  }

  function parseDerivation(input) {
    if (typeof input === "string") return toTree(parseSexp(input));
    return fromDict(input);
  }

  return {
    boxWidthForLabel,
    classifyNode,
    fromDict,
    isHighlightedNode,
    labelForNode,
    layoutTree,
    maxLeafDepth,
    parseDerivation,
    parseSexp,
    renderTree,
    rootShapePoints,
    tokenize,
    toTree,
    typeHrefForNode,
  };
});
