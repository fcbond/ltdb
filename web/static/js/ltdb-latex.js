(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.LTDBLatex = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Escape LaTeX special characters in text mode
  function esc(s) {
    return String(s)
      .replace(/\\/g, "\\textbackslash{}")
      .replace(/[{}&%$#~]/g, (c) => "\\" + c)
      .replace(/_/g, "\\_")
      .replace(/\^/g, "\\^{}");
  }

  // MRS variable name → LaTeX subscript: h0 → h_{0}, e12 → e_{12}
  function v(name) {
    return String(name).replace(/^([a-zA-Z]+)(\d+)$/, "$1_{$2}");
  }

  // ── Derivation tree → forest ───────────────────────────────────────────────
  // Input: the tree object returned by LTDBTree.parseDerivation()
  // Output: \begin{forest}...\end{forest} block

  function nodeToForest(node, depth) {
    const pad = "  ".repeat(depth);
    const label = "{" + esc(node.name) + "}";
    if (!node.children || !node.children.length) {
      return `${pad}[${label}]`;
    }
    const kids = node.children.map((c) => nodeToForest(c, depth + 1)).join("\n");
    return `${pad}[${label}\n${kids}\n${pad}]`;
  }

  function derivationToForest(parsedTree) {
    return [
      "% \\usepackage{forest}",
      "\\begin{forest}",
      "  for leaves={tier=word, font=\\itshape},",
      nodeToForest(parsedTree, 1),
      "\\end{forest}",
    ].join("\n");
  }

  // ── MRS → langsci-avm ─────────────────────────────────────────────────────
  // Input: the MRS object returned by LTDBMrs.parseMrs()
  // Output: \avm{...} block for the langsci-avm package

  // Format [{feat, val}] pairs as an indented AVM at column `pad`.
  // Optional `sort` emits \type{sort} \\ as a header row before the features.
  // Multiline values are supported: row-separator \\ and closing ] are
  // appended to the last line of each value string.
  function fmtAvm(pairs, pad, sort) {
    const inner = pad + "  ";

    if (!pairs.length) {
      return sort ? `${pad}[ \\type{${esc(sort)}} ]` : `${pad}[ ]`;
    }

    const lines = [];
    if (sort) {
      // Sort name on its own row, then features indented below
      lines.push(`${pad}[ \\type{${esc(sort)}} \\\\`);
      pairs.forEach(([feat, val], i) => {
        const suffix = i < pairs.length - 1 ? " \\\\" : " ]";
        lines.push(`${inner}${feat} & ${val}${suffix}`);
      });
    } else {
      pairs.forEach(([feat, val], i) => {
        const suffix = i < pairs.length - 1 ? " \\\\" : " ]";
        const prefix = i === 0 ? `${pad}[ ` : inner;
        lines.push(`${prefix}${feat} & ${val}${suffix}`);
      });
    }
    return lines.join("\n");
  }

  function epToPairs(ep) {
    const pairs = [
      ["pred", `\\textit{${esc(ep.predicate)}}`],
      ["lbl",  v(ep.label)],
      ["arg0", v(ep.arg0)],
    ];
    // ep.args holds every role except LBL and ARG0 (stored on ep directly);
    // preserve insertion order to match the original MRS role ordering
    Object.entries(ep.args).forEach(([role, val]) => {
      if (typeof val === "string") {
        pairs.push([role.toLowerCase(), v(val)]);
      } else if (val && val.carg !== undefined) {
        pairs.push(["carg", `"${esc(val.carg)}"`]);
      }
    });
    return pairs;
  }

  function mrsToAvm(mrs) {
    const I  = "  ";    // indent inside \avm{ }
    const I2 = "    ";  // continuation column (after opening feature name)
    const EP = I2 + "  "; // EP / hcon block indent

    const pairs = [];
    if (mrs.top)   pairs.push(["top",   v(mrs.top)]);
    if (mrs.index) pairs.push(["index", v(mrs.index)]);

    function mkList(blocks, close) {
      // Wrap blocks in \< ... \> with each block on its own indented lines.
      // close is the suffix after \> (" \\" between features, " ]" for last)
      return `<\n${blocks}\n${I2}>${close}`;
    }

    if (mrs.rels && mrs.rels.length) {
      const blocks = mrs.rels
        .map((ep, i) => fmtAvm(epToPairs(ep), EP) + (i < mrs.rels.length - 1 ? "," : ""))
        .join("\n");
      pairs.push(["rels", mkList(blocks, "")]);
    }

    if (mrs.hcons && mrs.hcons.length) {
      const blocks = mrs.hcons
        .map((hc, i) =>
          fmtAvm([["harg", v(hc.high)], ["larg", v(hc.low)]], EP, hc.rel) +
          (i < mrs.hcons.length - 1 ? "," : "")
        )
        .join("\n");
      pairs.push(["hcons", mkList(blocks, "")]);
    }

    if (mrs.icons && mrs.icons.length) {
      const blocks = mrs.icons
        .map((ic, i) =>
          fmtAvm([["left", v(ic.left)], ["right", v(ic.right)]], EP, ic.rel) +
          (i < mrs.icons.length - 1 ? "," : "")
        )
        .join("\n");
      pairs.push(["icons", mkList(blocks, "")]);
    }

    return [
      "% \\usepackage{langsci-avm}",
      "\\avm{",
      fmtAvm(pairs, I),
      "}",
    ].join("\n");
  }

  // ── DMRS → tikz-dependency ────────────────────────────────────────────────
  // Input: the DMRS object returned by LTDBMrs.mrsToDmrs()
  // Output: \begin{dependency}...\end{dependency} block

  function dmrsToTikz(dmrs) {
    // Sort nodes left-to-right by character span, then by nodeid
    const nodes = dmrs.nodes.slice().sort((a, b) => {
      const af = a.lnk ? a.lnk.from : 1e9;
      const bf = b.lnk ? b.lnk.from : 1e9;
      return af !== bf ? af - bf : a.nodeid - b.nodeid;
    });

    // 1-indexed position map for \depedge
    const pos = Object.fromEntries(nodes.map((n, i) => [n.nodeid, i + 1]));

    // Predicate label, including CARG if present
    function predLabel(n) {
      const pred = `\\textit{${esc(n.predicate)}}`;
      return n.carg !== undefined ? `${pred}(\\textrm{"${esc(String(n.carg))}"})` : pred;
    }

    const deptext = nodes.map(predLabel).join(" \\& ") + " \\\\";

    const arcs = [];
    for (const link of dmrs.links) {
      const label = link.rargname ? `${link.rargname}/${link.post}` : link.post;
      if (link.from === 0) {
        const tp = pos[link.to];
        if (tp !== undefined) arcs.push(`  \\deproot{${tp}}{TOP}`);
      } else {
        const fp = pos[link.from], tp = pos[link.to];
        if (fp !== undefined && tp !== undefined)
          arcs.push(`  \\depedge{${fp}}{${tp}}{${esc(label)}}`);
      }
    }

    return [
      "% \\usepackage{tikz-dependency}",
      "\\begin{dependency}[edge slant=4pt, label style={inner sep=.75ex}]",
      "  \\begin{deptext}[column sep=1.5em]",
      `    ${deptext}`,
      "  \\end{deptext}",
      ...arcs,
      "\\end{dependency}",
    ].join("\n");
  }

  return { derivationToForest, mrsToAvm, dmrsToTikz };
});
