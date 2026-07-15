(function () {
  const dbCache = new Map();
  const scriptUrl = document.currentScript
    ? document.currentScript.src
    : window.location.href;

  let _sqlPromise = null;
  function getSql() {
    if (!_sqlPromise) {
      if (!window.initSqlJs) {
        return Promise.reject(new Error("SQLite WASM loader is unavailable"));
      }
      _sqlPromise = window.initSqlJs({
        locateFile: (file) => new URL(file, scriptUrl).href,
      });
    }
    return _sqlPromise;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function isHighlighted(wid, spans) {
    return spans.some(([from, to]) => wid >= from && wid < to);
  }

  function renderTokens(tokens, spans) {
    return tokens
      .map((token) => {
        const word = escapeHtml(token.word);
        if (isHighlighted(token.wid, spans)) {
          return `<span class="text-success">${word}</span>`;
        }
        return word;
      })
      .join(" ");
  }

  async function loadDb(grammar, dbUrl) {
    if (dbCache.has(grammar)) {
      return dbCache.get(grammar);
    }
    const SQL = await getSql();
    const response = await fetch(dbUrl);
    if (!response.ok) {
      throw new Error(`Could not fetch examples DB: ${response.status}`);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    const db = new SQL.Database(bytes);
    dbCache.set(grammar, db);
    return db;
  }

  function queryExamples(db, typ) {
    const stmt = db.prepare(`
      SELECT te.rank, te.spans_json, te.source,
             e.profile, e.sid, e.sentence, e.tokens_json, e.deriv, e.mrs
      FROM type_examples AS te
      JOIN examples AS e ON te.example_id = e.example_id
      WHERE te.typ = ?
      ORDER BY te.rank
    `);
    const rows = [];
    stmt.bind([typ]);
    while (stmt.step()) {
      rows.push(stmt.getAsObject());
    }
    stmt.free();
    return rows;
  }

  function renderExamples(container, rows) {
    if (!rows.length) {
      container.innerHTML = `
        <h3>Sentences</h3>
        <p class="text-muted">No examples available in the static mirror.</p>
      `;
      return;
    }
    const items = rows
      .map((row) => {
        const tokens = JSON.parse(row.tokens_json || "[]");
        const spans = JSON.parse(row.spans_json || "[]");
        const sentence = tokens.length
          ? renderTokens(tokens, spans)
          : escapeHtml(row.sentence || "");
        const source = row.source
          ? `<small class="text-muted"> ${escapeHtml(row.source)}</small>`
          : "";
        const mrs = row.mrs
          ? `<details class="mt-2 ltdb-mrs-details"><summary>MRS</summary>
              <div class="ltdb-mrs-view" data-mrs="${escapeHtml(row.mrs)}"></div>
              <details class="mt-1 ltdb-dmrs-details"><summary>DMRS</summary>
                <div class="ltdb-dmrs-view" data-mrs="${escapeHtml(row.mrs)}"></div>
              </details>
             </details>`
          : "";
        const deriv = row.deriv
          ? `<details class="mt-2 ltdb-tree-details"><summary>Tree</summary>
              <div class="ltdb-tree" data-deriv="${escapeHtml(row.deriv)}"></div>
             </details>`
          : "";
        return `
          <li>
            <div><a title="${escapeHtml(row.profile)}, ${row.sid}">🗩</a>
              ${sentence}${source}
            </div>
            ${mrs}
            ${deriv}
          </li>
        `;
      })
      .join("");
    container.innerHTML = `<h3>Sentences <small>(${rows.length})</small></h3><ul>${items}</ul>`;
  }

  async function hydrate(container) {
    const grammar = container.dataset.grammar;
    const typ = container.dataset.type;
    const dbUrl = container.dataset.db;
    try {
      const db = await loadDb(grammar, dbUrl);
      renderExamples(container, queryExamples(db, typ));
    } catch (error) {
      container.innerHTML = `
        <h3>Sentences</h3>
        <p class="text-muted">Examples are unavailable: ${escapeHtml(
          error.message
        )}</p>
      `;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".ltdb-examples").forEach((container) => {
      hydrate(container);
    });
    document.addEventListener("toggle", (event) => {
      const details = event.target;
      if (!details.open) return;

      if (details.classList.contains("ltdb-tree-details")) {
        const tree = details.querySelector(".ltdb-tree");
        if (!tree || tree.dataset.rendered) return;
        try {
          const parsed = window.LTDBTree.parseDerivation(tree.dataset.deriv);
          const examples = tree.closest(".ltdb-examples");
          const grammar = examples ? examples.dataset.grammar : "";
          window.LTDBTree.renderTree(tree, parsed, {
            highlightType: examples ? examples.dataset.type : "",
            typeHref: (typ) => {
              if (!grammar) {
                return encodeURIComponent(typ);
              }
              const base = window.location.pathname.endsWith("/type.html")
                ? "type.html"
                : "../type.html";
              const params = new URLSearchParams({ grammar, type: typ });
              return `${base}?${params.toString()}`;
            },
          });
          tree.dataset.rendered = "true";
        } catch (error) {
          tree.innerHTML = `<p class="text-muted">Tree unavailable: ${escapeHtml(
            error.message
          )}</p><pre>${escapeHtml(tree.dataset.deriv || "")}</pre>`;
        }
        return;
      }

      if (details.classList.contains("ltdb-mrs-details")) {
        const view = details.querySelector(".ltdb-mrs-view");
        if (!view || view.dataset.rendered) return;
        try {
          const mrs = window.LTDBMrs.parseMrs(view.dataset.mrs);
          window.LTDBMrs.renderMrs(view, mrs);
          view.dataset.rendered = "true";
        } catch (error) {
          view.innerHTML = `<pre>${escapeHtml(view.dataset.mrs || "")}</pre>`;
          view.dataset.rendered = "true";
        }
        return;
      }

      if (details.classList.contains("ltdb-dmrs-details")) {
        const view = details.querySelector(".ltdb-dmrs-view");
        if (!view || view.dataset.rendered) return;
        try {
          const mrs = window.LTDBMrs.parseMrs(view.dataset.mrs);
          window.LTDBMrs.renderDmrs(view, mrs);
          view.dataset.rendered = "true";
        } catch (error) {
          view.innerHTML = `<p class="text-muted" style="font-size:12px">DMRS unavailable: ${escapeHtml(
            error.message
          )}</p>`;
          view.dataset.rendered = "true";
        }
      }
    }, true);

    // details that are open on page load (e.g. the sentence page) never
    // fire a user toggle, so render them now
    document.querySelectorAll(
      "details.ltdb-tree-details[open], details.ltdb-mrs-details[open], " +
      "details.ltdb-dmrs-details[open]"
    ).forEach((details) => {
      details.dispatchEvent(new Event("toggle"));
    });
  });

  window.LTDBExamples = {
    hydrate,
  };
})();
