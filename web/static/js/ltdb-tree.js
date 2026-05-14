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
      return { name: node[0], entity: node[0], children };
    }
    const name = String(node[1] || node[0] || "");
    const children = visibleChildren(node, 2);
    if (!children.length) {
      return { name, leaf: true };
    }
    return { name, entity: name, children };
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

  function labelForNode(node) {
    return node.form || node.name;
  }

  function boxWidthForLabel(label) {
    return Math.max(44, Math.min(140, String(label).length * 7 + 18));
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
    return Boolean(
      options &&
        options.highlightType &&
        (node.name === options.highlightType || node.entity === options.highlightType)
    );
  }

  function layoutTree(root, options) {
    const rowWidth = options && options.rowWidth ? options.rowWidth : 92;
    const levelHeight = options && options.levelHeight ? options.levelHeight : 64;
    const marginX = options && options.marginX ? options.marginX : 42;
    const marginY = options && options.marginY ? options.marginY : 28;
    const leafDepths = [];
    visibleLeafDepths(root, 0, leafDepths);
    const leafBaseline = Math.max(0, ...leafDepths) * levelHeight + marginY;
    countRows(root);
    let row = 0;

    function position(node, depth) {
      node._boxWidth = boxWidthForLabel(labelForNode(node));
      node._boxHeight = 24;
      const children = visibleChildrenFor(node);
      if (!children.length) {
        node._x = marginX + row * rowWidth;
        row += 1;
      } else {
        children.forEach((child) => position(child, depth + 1));
        node._x =
          children.reduce((total, child) => total + child._x, 0) / children.length;
      }
      node._y = node.leaf ? leafBaseline : marginY + depth * levelHeight;
    }

    position(root, 0);
    const nodes = [];
    const links = [];
    collectVisibleNodes(root, nodes, links);
    const width = Math.max(row * rowWidth + marginX * 2, 160);
    const height =
      Math.max(...nodes.map((node) => node._y), leafBaseline) +
      (options && options.labelHeight ? options.labelHeight : 52);
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
      .ltdb-tree-svg { max-width: 100%; height: auto; overflow: visible; }
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
    const sx = link.source._y + link.source._boxHeight / 2;
    const sy = link.source._x;
    const tx = link.target._y - link.target._boxHeight / 2;
    const ty = link.target._x;
    const mid = sx + (tx - sx) / 2;
    return `M${sy},${sx} C${sy},${mid} ${ty},${mid} ${ty},${tx}`;
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
      text.textContent = labelForNode(node);
      const title = svgElement("title");
      title.textContent = node.leaf
        ? node.name
        : `${node.name} (${nodeClass}; click to collapse, shift-click to open type)`;
      group.appendChild(title);
      group.appendChild(text);
      nodeLayer.appendChild(group);
    });
    svg.appendChild(nodeLayer);
    container.appendChild(svg);
    return layout;
  }

  function parseDerivation(input) {
    return toTree(parseSexp(input));
  }

  return {
    boxWidthForLabel,
    classifyNode,
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
