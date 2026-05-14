(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.LTDBMrs = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ── Tokeniser ──────────────────────────────────────────────────────────────
  // Produces token objects: { t: type, v?: value }
  // Types: '[' ']' '<' '>' ':' 'lnk' (v="from:to") 'a' (atom) 'str' (quoted)

  function tokenize(input) {
    const tokens = [];
    let i = 0;
    const n = input.length;
    while (i < n) {
      const c = input[i];
      if (/\s/.test(c)) { i++; continue; }
      if (c === "[") { tokens.push({ t: "[" }); i++; continue; }
      if (c === "]") { tokens.push({ t: "]" }); i++; continue; }
      if (c === ":") { tokens.push({ t: ":" }); i++; continue; }
      if (c === ">") { tokens.push({ t: ">" }); i++; continue; }
      if (c === "<") {
        // Distinguish <from:to> lnk from < (list-open)
        let j = i + 1;
        while (j < n && input[j] !== ">" && !/[\s\[<]/.test(input[j])) j++;
        const inner = input.slice(i + 1, j);
        if (j < n && input[j] === ">" && /^-?\d+:-?\d+$/.test(inner)) {
          tokens.push({ t: "lnk", v: inner });
          i = j + 1;
        } else {
          tokens.push({ t: "<" });
          i++;
        }
        continue;
      }
      if (c === '"') {
        let j = i + 1, val = "";
        while (j < n) {
          if (input[j] === "\\" && j + 1 < n) { val += input[j + 1]; j += 2; }
          else if (input[j] === '"') { j++; break; }
          else { val += input[j++]; }
        }
        tokens.push({ t: "str", v: val });
        i = j;
        continue;
      }
      // Atom: anything up to whitespace or delimiter
      let j = i;
      while (j < n && !/[\s[\]<>:"]/.test(input[j])) j++;
      if (j > i) { tokens.push({ t: "a", v: input.slice(i, j) }); i = j; }
      else i++;
    }
    return tokens;
  }

  // ── Parser helpers ─────────────────────────────────────────────────────────

  function peek(s) {
    return s.pos < s.toks.length ? s.toks[s.pos].t : null;
  }
  function advance(s) {
    return s.pos < s.toks.length ? s.toks[s.pos++] : null;
  }
  function expect(s, t) {
    const tok = advance(s);
    if (!tok || tok.t !== t) {
      throw new Error(
        `MRS parse: expected '${t}' at pos ${s.pos}, got '${tok ? tok.t : "EOF"}'`
      );
    }
    return tok;
  }
  function eatAtom(s) {
    return expect(s, "a").v;
  }

  // Read a variable name; if followed by [ type feat: val … ], record properties
  function readVar(s, vars) {
    const name = eatAtom(s);
    if (peek(s) === "[") {
      advance(s);
      const type = eatAtom(s);
      const props = {};
      while (peek(s) !== "]" && peek(s) !== null) {
        const feat = eatAtom(s);
        expect(s, ":");
        // Values are usually atoms but some grammars use quoted strings
        props[feat] = peek(s) === "str" ? advance(s).v : eatAtom(s);
      }
      expect(s, "]");
      if (!vars[name]) vars[name] = { type, props };
    }
    return name;
  }

  function readEp(s, vars) {
    expect(s, "[");
    // Some grammars quote their predicate names; trim trailing whitespace inside quotes
    const predicate = peek(s) === "str" ? advance(s).v.trim() : eatAtom(s);
    let lnk = null;
    if (peek(s) === "lnk") {
      const tok = advance(s);
      const [f, t] = tok.v.split(":");
      lnk = { from: parseInt(f, 10), to: parseInt(t, 10) };
    }
    let label = null, arg0 = null;
    const args = {};
    // Guard against infinite loops on malformed input
    let safety = 4096;
    while (peek(s) !== "]" && peek(s) !== null && --safety > 0) {
      const feat = eatAtom(s);
      expect(s, ":");
      let val;
      if (peek(s) === "str") {
        val = { carg: advance(s).v };
      } else {
        val = readVar(s, vars);
      }
      if (feat === "LBL") label = val;
      else if (feat === "ARG0") arg0 = val;
      else args[feat] = val;
    }
    expect(s, "]");
    return { predicate, lnk, label, arg0, args };
  }

  // ── Public: parseMrs ───────────────────────────────────────────────────────

  function parseMrs(input) {
    if (!input || !input.trim()) throw new Error("Empty MRS string");
    const s = { toks: tokenize(input), pos: 0 };
    const vars = {};
    let top = null, index = null;
    let rels = [], hcons = [], icons = [];

    expect(s, "[");
    let safety = 65536;
    while (peek(s) === "a" && --safety > 0) {
      const key = eatAtom(s).toUpperCase();
      expect(s, ":");
      switch (key) {
        case "TOP":
        case "LTOP":
          top = readVar(s, vars);
          break;
        case "INDEX":
          index = readVar(s, vars);
          break;
        case "RELS":
          expect(s, "<");
          while (peek(s) === "[") rels.push(readEp(s, vars));
          expect(s, ">");
          break;
        case "HCONS":
          expect(s, "<");
          while (peek(s) === "a") {
            const hi = eatAtom(s), rel = eatAtom(s), lo = eatAtom(s);
            hcons.push({ high: hi, rel, low: lo });
          }
          expect(s, ">");
          break;
        case "ICONS":
          expect(s, "<");
          while (peek(s) === "a") {
            // Variables may carry inline type annotations: var [ type feat: val … ] rel var
            const left = readVar(s, vars);
            const rel = eatAtom(s);
            const right = readVar(s, vars);
            icons.push({ left, rel, right });
          }
          expect(s, ">");
          break;
        default:
          break;
      }
    }
    expect(s, "]");
    return { top, index, rels, hcons, icons, variables: vars };
  }

  // ── MRS → DMRS conversion ─────────────────────────────────────────────────

  function varSort(name) {
    const m = String(name || "").match(/^([a-z]+)/i);
    return m ? m[1].toLowerCase() : "u";
  }

  // Quantifiers have RSTR and BODY arguments; they share ARG0 with their bound variable.
  function isQuantifier(ep) {
    return "RSTR" in (ep.args || {}) && "BODY" in (ep.args || {});
  }

  // Priority rank for selecting the representative EP in a shared-label group.
  // Matches pydelphin's default: lower rank = higher priority = sorted first.
  // x-type (0) > tensed-e (1) > untensed-e (2) > other (3).
  function repRank(ep, variables) {
    const sort = varSort(ep.arg0 || "");
    if (sort === "x") return 0;
    if (sort === "e") {
      const props = (variables[ep.arg0] || {}).props || {};
      const tense = (props.TENSE || "").toLowerCase();
      return tense === "" || tense === "untensed" ? 2 : 1;
    }
    return 3;
  }

  // Compute scope representatives per label, exactly matching pydelphin's
  // scope.representatives algorithm.
  //
  // pydelphin eliminates an EP from candidacy if any of its non-handle outgoing
  // args is either:
  //   (a) the intrinsic variable (ARG0) of a sibling EP in the same scope group
  //       [direct check], or
  //   (b) the intrinsic variable of any EP that lives in a scope transitively
  //       governed by a sibling via HCONS qeq [descendants check].
  //
  // The "descendants" here are scope-tree descendants (not argument-graph), so an
  // EP's descendants are all EPs in scopes it governs through its handle arguments
  // (resolved via HCONS), transitively.
  function computeReps(mrs) {
    // Build structures needed for both checks
    const qeq = {};
    (mrs.hcons || []).forEach((hc) => {
      if (hc.rel === "qeq") qeq[hc.high] = hc.low;
    });

    const byLabel = {};
    mrs.rels.forEach((ep) => {
      if (ep.label) (byLabel[ep.label] = byLabel[ep.label] || []).push(ep);
    });

    // Compute scope-tree descendants for each EP:
    // the set of arg0 values of all EPs in scopes transitively governed by this EP.
    // An EP governs scope S if it has a handle arg h where h qeq S.
    const descsCache = new Map(); // ep._nid → Set<string>
    function scopeDescs(ep, visiting = new Set()) {
      if (descsCache.has(ep._nid)) return descsCache.get(ep._nid);
      if (visiting.has(ep._nid)) return new Set();
      visiting.add(ep._nid);
      const result = new Set();
      for (const val of Object.values(ep.args || {})) {
        if (typeof val !== "string" || varSort(val) !== "h") continue;
        // Follow qeq if present; otherwise the handle directly equals a scope label (HEQ)
        const lo = qeq[val] !== undefined ? qeq[val] : val;
        for (const child of byLabel[lo] || []) {
          if (child.arg0) result.add(child.arg0);
          scopeDescs(child, visiting).forEach((d) => result.add(d));
        }
      }
      descsCache.set(ep._nid, result);
      return result;
    }
    mrs.rels.forEach((ep) => scopeDescs(ep));

    const repsByLabel = {};
    for (const [label, group] of Object.entries(byLabel)) {
      let candidates;
      if (group.length === 1) {
        candidates = group.slice();
      } else {
        // Non-handle outgoing args for each EP in the group
        const nsArgs = (ep) =>
          Object.values(ep.args || {}).filter(
            (v) => typeof v === "string" && varSort(v) !== "h"
          );

        const siblingArg0s = new Set(group.map((ep) => ep.arg0).filter(Boolean));

        candidates = group.filter((ep) => {
          const myArgs = nsArgs(ep);
          const siblings = group.filter((o) => o !== ep);

          // (a) Direct check: any outgoing arg is a sibling's ARG0
          if (myArgs.some((v) => siblingArg0s.has(v) && siblings.some((s) => s.arg0 === v))) {
            return false;
          }

          // (b) Descendants check: any outgoing arg is in a sibling's scope subtree
          if (
            myArgs.length > 0 &&
            siblings.some((s) => {
              const sd = scopeDescs(s);
              return myArgs.some((v) => sd.has(v));
            })
          ) {
            return false;
          }

          return true;
        });
        if (!candidates.length) candidates = group.slice();
      }

      candidates.sort((a, b) => {
        const ra = repRank(a, mrs.variables);
        const rb = repRank(b, mrs.variables);
        if (ra !== rb) return ra - rb;
        return mrs.rels.indexOf(a) - mrs.rels.indexOf(b);
      });
      repsByLabel[label] = candidates;
    }
    return repsByLabel;
  }

  function mrsToDmrs(mrs) {
    // Validate: non-quantifier EPs must each have a unique ARG0
    const arg0Seen = new Set();
    for (const ep of mrs.rels) {
      if (isQuantifier(ep)) continue;
      if (!ep.arg0 || typeof ep.arg0 !== "string") {
        throw new Error(`EP ${ep.predicate} has no ARG0`);
      }
      if (arg0Seen.has(ep.arg0)) {
        throw new Error(`Duplicate ARG0 ${ep.arg0} (MRS violates intrinsic variable property)`);
      }
      arg0Seen.add(ep.arg0);
    }

    const BASE = 10000;
    mrs.rels.forEach((ep, i) => { ep._nid = BASE + i; });

    // arg0 → ep (quantifiers excluded so the bound variable maps to the restriction EP)
    const arg0Map = {};
    mrs.rels.forEach((ep) => {
      if (!isQuantifier(ep) && ep.arg0) arg0Map[ep.arg0] = ep;
    });

    // Scope representatives: primary target for H links at each label
    const reps = computeReps(mrs);

    // qeq: high handle → low handle
    const qeq = {};
    (mrs.hcons || []).forEach((hc) => {
      if (hc.rel === "qeq") qeq[hc.high] = hc.low;
    });

    const nodes = mrs.rels.map((ep) => {
      const v = mrs.variables[ep.arg0] || {};
      const sortinfo = { cvarsort: varSort(ep.arg0), ...(v.props || {}) };
      const node = { nodeid: ep._nid, predicate: ep.predicate, sortinfo };
      if (ep.lnk) node.lnk = ep.lnk;
      if (ep.args.CARG && ep.args.CARG.carg !== undefined) node.carg = ep.args.CARG.carg;
      return node;
    });

    const links = [];

    // TOP link: synthetic from=0 using the primary representative at the top label
    if (mrs.top) {
      const lo = qeq[mrs.top] || mrs.top;
      const rep = reps[lo];
      if (rep && rep.length) links.push({ from: 0, to: rep[0]._nid, rargname: "", post: "H" });
    }

    // Argument links (ARG0 is the intrinsic variable, not an outgoing edge)
    mrs.rels.forEach((ep) => {
      Object.entries(ep.args).forEach(([role, val]) => {
        if (!val || typeof val !== "string") return; // skip CARG objects
        const sort = varSort(val);
        if (sort === "h") {
          // Scopal argument: resolve via HCONS (H) or direct label match (HEQ)
          const lo = qeq[val];
          if (lo) {
            const rep = reps[lo];
            if (rep && rep.length) {
              links.push({ from: ep._nid, to: rep[0]._nid, rargname: role, post: "H" });
            }
          } else if (reps[val]) {
            const head = reps[val][0];
            if (head && head !== ep) {
              links.push({ from: ep._nid, to: head._nid, rargname: role, post: "HEQ" });
            }
          }
        } else {
          // Non-scopal variable argument
          const target = arg0Map[val];
          if (target) {
            const post = ep.label && ep.label === target.label ? "EQ" : "NEQ";
            links.push({ from: ep._nid, to: target._nid, rargname: role, post });
          }
        }
      });
    });

    // MOD/EQ links: when a label has multiple representatives, the non-primary
    // ones link to the primary (BARE_EQ_ROLE="MOD" in pydelphin).
    for (const repList of Object.values(reps)) {
      if (repList.length > 1) {
        const head = repList[0];
        for (let i = 1; i < repList.length; i++) {
          links.push({ from: repList[i]._nid, to: head._nid, rargname: "MOD", post: "EQ" });
        }
      }
    }

    // Resolve top/index to nodeids
    let topNid = null, indexNid = null;
    if (mrs.top) {
      const lo = qeq[mrs.top] || mrs.top;
      const rep = reps[lo];
      if (rep && rep.length) topNid = rep[0]._nid;
    }
    if (mrs.index) {
      const ep = arg0Map[mrs.index];
      if (ep) indexNid = ep._nid;
    }

    return { nodes, links, top: topNid, index: indexNid };
  }

  // ── HTML MRS renderer ─────────────────────────────────────────────────────

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function spanV(name) {
    return `<span class="ltdb-mrs-v ltdb-mrs-${varSort(name)}">${esc(name)}</span>`;
  }

  function propsHtml(name, vars) {
    const e = vars[name];
    if (!e || !e.props || !Object.keys(e.props).length) return "";
    const ps = Object.entries(e.props)
      .map(([f, v]) => `${esc(f)}: <span class="ltdb-mrs-val">${esc(v)}</span>`)
      .join(" ");
    return ` <span class="ltdb-mrs-vp">[${esc(e.type)} ${ps}]</span>`;
  }

  function ensureMrsStyles() {
    if (document.getElementById("ltdb-mrs-style")) return;
    const s = document.createElement("style");
    s.id = "ltdb-mrs-style";
    s.textContent = `
      .ltdb-mrs-wrap{font:13px/1.5 monospace;overflow-x:auto}
      .ltdb-mrs-head{margin-bottom:6px}
      .ltdb-mrs-head span{margin-right:14px}
      .ltdb-mrs-lbl{font-weight:700;color:#333;margin-right:3px}
      .ltdb-mrs-rels{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px}
      .ltdb-mrs-ep{border:1px solid #ccc;border-radius:4px;padding:3px 7px;background:#fafafa;font-size:12px;line-height:1.6}
      .ltdb-mrs-pred{font-weight:700}
      .ltdb-mrs-lnk{color:#999;font-size:11px;margin-left:1px}
      .ltdb-mrs-feat{color:#666}
      .ltdb-mrs-vp{color:#999;font-size:11px}
      .ltdb-mrs-val{color:#444}
      .ltdb-mrs-hc,.ltdb-mrs-ic{font-size:12px;color:#444;margin-top:3px}
      .ltdb-mrs-v{font-weight:600}
      .ltdb-mrs-h{color:#7b35c9}
      .ltdb-mrs-e{color:#1565c0}
      .ltdb-mrs-x{color:#2e7d32}
      .ltdb-mrs-i,.ltdb-mrs-u,.ltdb-mrs-p,.ltdb-mrs-q,.ltdb-mrs-a{color:#795548}
    `;
    document.head.appendChild(s);
  }

  function renderMrs(container, mrs) {
    ensureMrsStyles();
    const vs = mrs.variables || {};

    let head = "";
    if (mrs.top) {
      head += `<span><span class="ltdb-mrs-lbl">TOP:</span>${spanV(mrs.top)}</span>`;
    }
    if (mrs.index) {
      head += `<span><span class="ltdb-mrs-lbl">INDEX:</span>${spanV(mrs.index)}${propsHtml(mrs.index, vs)}</span>`;
    }

    const relsHtml = (mrs.rels || [])
      .map((ep) => {
        const lnk = ep.lnk
          ? `<span class="ltdb-mrs-lnk">&lt;${ep.lnk.from}:${ep.lnk.to}&gt;</span>`
          : "";
        const lbl = ep.label
          ? ` <span class="ltdb-mrs-feat">LBL:</span>${spanV(ep.label)}`
          : "";
        const a0 = ep.arg0
          ? ` <span class="ltdb-mrs-feat">ARG0:</span>${spanV(ep.arg0)}${propsHtml(ep.arg0, vs)}`
          : "";
        const rest = Object.entries(ep.args || {})
          .map(([f, v]) => {
            const vh =
              v && v.carg !== undefined
                ? `<span class="ltdb-mrs-val">"${esc(v.carg)}"</span>`
                : spanV(String(v));
            return `<br><span style="padding-left:8px"><span class="ltdb-mrs-feat">${esc(f)}:</span>${vh}</span>`;
          })
          .join("");
        return (
          `<div class="ltdb-mrs-ep">` +
          `<span class="ltdb-mrs-pred">${esc(ep.predicate)}</span>${lnk}${lbl}${a0}${rest}` +
          `</div>`
        );
      })
      .join("");

    const hcHtml =
      (mrs.hcons || []).length
        ? `<div class="ltdb-mrs-hc"><span class="ltdb-mrs-lbl">HCONS:</span> ${mrs.hcons
            .map((hc) => `${spanV(hc.high)} ${esc(hc.rel)} ${spanV(hc.low)}`)
            .join(", ")}</div>`
        : "";
    const icHtml =
      (mrs.icons || []).length
        ? `<div class="ltdb-mrs-ic"><span class="ltdb-mrs-lbl">ICONS:</span> ${mrs.icons
            .map((ic) => `${spanV(ic.left)} ${esc(ic.rel)} ${spanV(ic.right)}`)
            .join(", ")}</div>`
        : "";

    container.innerHTML = `
      <div class="ltdb-mrs-wrap">
        <div class="ltdb-mrs-head">${head}</div>
        <div class="ltdb-mrs-rels">${relsHtml}</div>
        ${hcHtml}${icHtml}
      </div>`;
  }

  // ── SVG DMRS renderer ─────────────────────────────────────────────────────

  // Layout constants
  const NW_PAD = 9, NH = 24, NGAP = 12, LH = 22, MX = 10, MTOP = 6;

  function svgEl(tag, attrs, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, String(v)));
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function nodeLabel(node) {
    return node.carg ? `${node.predicate}("${node.carg}")` : node.predicate;
  }

  function nodeW(node) {
    return Math.max(38, Math.min(180, nodeLabel(node).length * 6.8 + NW_PAD * 2));
  }

  function ensureDmrsStyles() {
    if (document.getElementById("ltdb-dmrs-style")) return;
    const s = document.createElement("style");
    s.id = "ltdb-dmrs-style";
    s.textContent = `
      .ltdb-dmrs-svg{max-width:100%;height:auto;overflow:visible;font:12px sans-serif}
      .ltdb-dmrs-box{fill:#fff;stroke:#61748a;stroke-width:1.25}
      .ltdb-dmrs-txt{fill:#222;text-anchor:middle;dominant-baseline:central;pointer-events:none}
      .ltdb-dmrs-arc{fill:none;stroke-width:1.1}
      .ltdb-dmrs-arc.h{stroke:#7b35c9}
      .ltdb-dmrs-arc.heq{stroke:#a55}
      .ltdb-dmrs-arc.neq{stroke:#1565c0}
      .ltdb-dmrs-arc.eq{stroke:#999;stroke-dasharray:3 2}
      .ltdb-dmrs-arc.top{stroke:#bbb;stroke-dasharray:4 2}
      .ltdb-dmrs-elbl{fill:#555;text-anchor:middle;font-size:10px}
      .ltdb-dmrs-ah{fill:#555}
    `;
    document.head.appendChild(s);
  }

  function renderDmrs(container, mrs) {
    ensureDmrsStyles();
    container.textContent = "";
    let dmrs;
    try {
      dmrs = mrsToDmrs(mrs);
    } catch (e) {
      container.innerHTML = `<p class="text-muted" style="font-size:12px">DMRS unavailable: ${esc(e.message)}</p>`;
      return;
    }
    if (!dmrs.nodes.length) return;

    // Sort nodes L→R by lnk.from, then nodeid
    const sorted = [...dmrs.nodes].sort((a, b) => {
      const af = a.lnk ? a.lnk.from : 1e9;
      const bf = b.lnk ? b.lnk.from : 1e9;
      return af !== bf ? af - bf : a.nodeid - b.nodeid;
    });

    // Assign centre x for each node
    const pos = {}; // nodeid → { cx, w }
    let x = MX;
    sorted.forEach((n) => {
      const w = nodeW(n);
      pos[n.nodeid] = { cx: x + w / 2, w };
      x += w + NGAP;
    });
    const totalW = x + MX;

    // sorted index per nodeid (used for collision detection)
    const sidx = {};
    sorted.forEach((n, i) => { sidx[n.nodeid] = i; });

    // Assign arc levels to non-TOP links (shorter spans first to minimise crossings)
    const nonTop = dmrs.links
      .filter((l) => l.from !== 0)
      .sort((a, b) => {
        const da = Math.abs(sidx[a.from] - sidx[a.to]);
        const db = Math.abs(sidx[b.from] - sidx[b.to]);
        return da - db;
      });
    const occupied = {}; // "segIdx,level" → true
    nonTop.forEach((link) => {
      const dir = link.post === "EQ" ? -1 : 1; // above (+) or below (-)
      const lo = Math.min(sidx[link.from], sidx[link.to]);
      const hi = Math.max(sidx[link.from], sidx[link.to]);
      let level = dir;
      outer: while (true) {
        for (let i = lo; i < hi; i++) {
          if (occupied[`${i},${level}`]) { level += dir; continue outer; }
        }
        for (let i = lo; i < hi; i++) occupied[`${i},${level}`] = true;
        link._level = level;
        return;
      }
    });

    const maxTop = Math.max(1, ...nonTop.filter((l) => l._level > 0).map((l) => l._level));
    const maxBot = Math.max(0, ...nonTop.filter((l) => l._level < 0).map((l) => -l._level));

    // Y of node top edge; leave room above for TOP line + arcs
    const nodeY = MTOP + (maxTop + 1) * LH;
    const totalH = nodeY + NH + (maxBot > 0 ? (maxBot + 1) * LH : LH * 0.5);

    const svg = svgEl("svg", {
      class: "ltdb-dmrs-svg",
      viewBox: `0 0 ${Math.ceil(totalW)} ${Math.ceil(totalH)}`,
      width: Math.ceil(totalW),
      height: Math.ceil(totalH),
    });

    // Arrow marker (points right; orient=auto rotates it)
    const defs = svgEl("defs", {});
    const mk = svgEl("marker", {
      id: "ltdb-dmrs-ah",
      markerWidth: 6, markerHeight: 6,
      refX: 5, refY: 3,
      orient: "auto",
    });
    mk.appendChild(svgEl("path", { d: "M0,1 L5,3 L0,5 Z", class: "ltdb-dmrs-ah" }));
    defs.appendChild(mk);
    svg.appendChild(defs);

    // Draw links
    const linkG = svgEl("g", {});
    dmrs.links.forEach((link) => {
      const isTOP = link.from === 0;
      const ep = pos[link.to];
      if (!ep) return;

      const post = link.post.toLowerCase();
      const cls = `ltdb-dmrs-arc ${isTOP ? "top" : post}`;

      if (isTOP) {
        // Vertical dashed line from top margin into node top
        const cx = ep.cx;
        const lineTop = MTOP;
        linkG.appendChild(
          svgEl("line", {
            class: cls,
            x1: cx, y1: lineTop,
            x2: cx, y2: nodeY,
          })
        );
        // Small downward triangle at node top
        const tp = svgEl("polygon", {
          points: `${cx - 4},${nodeY - 7} ${cx + 4},${nodeY - 7} ${cx},${nodeY - 1}`,
          class: "ltdb-dmrs-ah",
        });
        linkG.appendChild(tp);
      } else {
        const sp = pos[link.from];
        if (!sp) return;
        const level = link._level || (link.post === "EQ" ? -1 : 1);
        const above = level > 0;
        const x1 = sp.cx, x2 = ep.cx;
        const yEdge = above ? nodeY : nodeY + NH;
        const arcY = above
          ? nodeY - level * LH
          : nodeY + NH + Math.abs(level) * LH;

        const d = `M${x1},${yEdge} C${x1},${arcY} ${x2},${arcY} ${x2},${yEdge}`;
        const hasArrow = post !== "eq";
        linkG.appendChild(
          svgEl("path", {
            class: cls,
            d,
            "marker-end": hasArrow ? "url(#ltdb-dmrs-ah)" : "none",
          })
        );
        if (link.rargname) {
          const midX = (x1 + x2) / 2;
          const midY = above ? arcY - 3 : arcY + 11;
          linkG.appendChild(
            svgEl("text", { class: "ltdb-dmrs-elbl", x: midX, y: midY },
              `${link.rargname}/${link.post}`)
          );
        }
      }
    });
    svg.appendChild(linkG);

    // Draw nodes
    const nodeG = svgEl("g", {});
    sorted.forEach((n) => {
      const { cx, w } = pos[n.nodeid];
      const g = svgEl("g", {});
      g.appendChild(
        svgEl("rect", {
          class: "ltdb-dmrs-box",
          x: cx - w / 2, y: nodeY,
          width: w, height: NH,
          rx: 3,
        })
      );
      g.appendChild(
        svgEl("text", { class: "ltdb-dmrs-txt", x: cx, y: nodeY + NH / 2 },
          nodeLabel(n))
      );
      nodeG.appendChild(g);
    });
    svg.appendChild(nodeG);

    container.appendChild(svg);
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  return { parseMrs, mrsToDmrs, renderMrs, renderDmrs };
});
