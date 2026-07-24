"""Route declaration."""

import json
import os
import pathlib
import re as _re
import shutil
import sqlite3
import sys
import threading
import traceback
from functools import lru_cache
from urllib.parse import quote

from delphin import ace as _ace
from delphin import dmrs as _dmrs
from delphin.codecs import dmrsjson as _dmrsjson
from delphin.codecs import mrsjson as _mrsjson
from delphin.codecs import simplemrs as _simplemrs
from delphin.highlight import TDLLexer
from flask import current_app as app
from flask import (
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from pygments import highlight
from pygments.formatters import HtmlFormatter

from .db import (
    get_all_doctests,
    get_db,
    get_doctest,
    get_gold,
    get_ltypes,
    get_lxid,
    get_lxids,
    get_md,
    get_phenomena_by_cx,
    get_phenomena_by_lexids,
    get_rules,
    get_sents,
    get_short_summary,
    get_summary,
    get_tb_summary,
    get_type,
    get_wrds_by_lexids,
    get_wrds_by_ltypes,
    search_for,
)
from .ltdb import docstring2html, render_markdown, sanitize_grm

_tdl_formatter = HtmlFormatter(style="friendly")
PYGMENTS_CSS = _tdl_formatter.get_style_defs(".highlight")
_type_span_re = _re.compile(r'<span class="(nc|n)">([^<]+)</span>')


def tdl2html(tdl_str, grm=None):
    """Render a TDL string to syntax-highlighted HTML with clickable type links."""
    if not tdl_str:
        return ""
    html = highlight(tdl_str, TDLLexer(), _tdl_formatter)
    endpoint = request.endpoint or ""
    render_url_for = app.jinja_env.globals.get("url_for", url_for)

    def href_for_type(query):
        if endpoint.startswith("mirror_"):
            return _mirror_type_href(grm, query, render_url_for)
        return render_url_for("type", query=query)

    return _type_span_re.sub(
        lambda m: (
            f'<a href="{href_for_type(m.group(2))}"'
            f' class="{m.group(1)}">{m.group(2)}</a>'
        ),
        html,
    )


current_directory = os.path.abspath(os.path.dirname(__file__))
FULL_LTDB_BASE_URL = os.environ.get(
    "FULL_LTDB_BASE_URL", "https://compling.upol.cz/ltdb"
)
STATIC_MIRROR_STATUSES = {
    status.strip()
    for status in os.environ.get(
        "STATIC_MIRROR_STATUSES", "lex-type,rule,lex-rule,root"
    ).split(",")
    if status.strip()
}
STATIC_MIRROR_ALL_NON_LEX = os.environ.get("STATIC_MIRROR_ALL_NON_LEX") == "1"
STATIC_MIRROR_DYNAMIC_TYPES = os.environ.get("STATIC_MIRROR_DYNAMIC_TYPES") == "1"


def _load_home_blurb():
    """Render HOME_BLURB_FILE (if set) to HTML for the home page.

    Lets a deployment (e.g. a curated grammar collection) add its own
    intro blurb without forking the app: point the env var at a
    Markdown file and it's rendered above the generic Overview text.
    Unset by default, so other local/standalone installs see nothing.
    """
    path = os.environ.get("HOME_BLURB_FILE")
    if not path:
        return ""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"HOME_BLURB_FILE={path!r} could not be read: {e}", file=sys.stderr)
        return ""
    return render_markdown(text)


HOME_BLURB_HTML = _load_home_blurb()


def _is_mirror_request():
    endpoint = request.endpoint or ""
    return endpoint.startswith("mirror_")


def _mirror_grm():
    if request.view_args and request.view_args.get("grm"):
        return request.view_args["grm"]
    grm = session.get("grm")
    if grm:
        return grm[:-3] if grm.endswith(".db") else grm
    return None


def _full_type_href(grm, query):
    db = _db_for_stem(grm)
    return f"{FULL_LTDB_BASE_URL.rstrip('/')}/type/{quote(query)}?grm={quote(db)}"


@lru_cache(maxsize=50000)
def _mirror_type_status(grm, query):
    db = _db_for_stem(grm)
    path = os.path.join(current_directory, "db", db)
    if not os.path.isfile(path):
        return None
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT status FROM types WHERE typ = ? LIMIT 1", (query,)
        ).fetchone()
    return row[0] if row else None


def _mirror_has_static_type(grm, query):
    status = _mirror_type_status(grm, query)
    if STATIC_MIRROR_ALL_NON_LEX:
        return status not in (None, "lex-entry", "generic-lex-entry")
    return status in STATIC_MIRROR_STATUSES


def _mirror_type_href(grm, query, render_url_for):
    if STATIC_MIRROR_DYNAMIC_TYPES:
        return render_url_for(
            "mirror_type_shell",
            grammar=_stem_for_grm(grm),
            type=query,
        )
    if _mirror_has_static_type(grm, query):
        return render_url_for("mirror_type", grm=_stem_for_grm(grm), query=query)
    return _full_type_href(grm, query)


@app.context_processor
def _inject_static_mirror_helpers():
    def render_url_for(*args, **kwargs):
        return app.jinja_env.globals.get("url_for", url_for)(*args, **kwargs)

    def type_href(query):
        if _is_mirror_request():
            if query == "":
                base = render_url_for("mirror_grammar", grm=_mirror_grm()).rsplit(
                    "/", 1
                )[0]
                return f"{base}/type/"
            return _mirror_type_href(_mirror_grm(), query, render_url_for)
        if query == "":
            return "/type/"
        return render_url_for("type", query=query)

    def grammar_href(grm=None):
        if _is_mirror_request():
            grm = grm or _mirror_grm()
            return render_url_for("mirror_grammar", grm=_stem_for_grm(grm))
        return render_url_for("grammar")

    def rules_href():
        if _is_mirror_request():
            return render_url_for("mirror_rules", grm=_mirror_grm())
        return render_url_for("rules")

    def ltypes_href():
        if _is_mirror_request():
            return render_url_for("mirror_ltypes", grm=_mirror_grm())
        return render_url_for("ltypes")

    def doctests_href():
        return render_url_for("doctests")

    def example_db_href(grm=None):
        grm = _stem_for_grm(grm or _mirror_grm())
        return f"../../db/{grm}.examples.sqlite"

    # per-grammar navigation flags: hide tabs that would be empty
    grm = session.get("grm")
    live_grm = grm if grm and not _is_mirror_request() else None
    return {
        "is_static_mirror": _is_mirror_request(),
        "static_mirror_all_non_lex": STATIC_MIRROR_ALL_NON_LEX,
        "static_mirror_statuses": STATIC_MIRROR_STATUSES,
        "full_ltdb_base_url": FULL_LTDB_BASE_URL.rstrip("/"),
        "type_href": type_href,
        "grammar_href": grammar_href,
        "rules_href": rules_href,
        "ltypes_href": ltypes_href,
        "doctests_href": doctests_href,
        "example_db_href": example_db_href,
        "has_doctests": bool(live_grm) and _grm_has_doctests(live_grm),
        "has_demo": bool(live_grm) and dat_path_for(live_grm) is not None,
    }


_summ_cache: tuple[frozenset, list, dict] | None = None

MAX_PARSE_CHARS = 500
MAX_GENERATE_MRS_CHARS = 10_000
ACE_CONCURRENCY = 4
_ace_slots = threading.Semaphore(ACE_CONCURRENCY)


def _db_fingerprint(db_dir: str) -> frozenset:
    """Return a frozenset of (name, mtime, size) for every .db file in db_dir."""
    result = set()
    for f in os.listdir(db_dir):
        if f.endswith(".db"):
            st = os.stat(os.path.join(db_dir, f))
            result.add((f, st.st_mtime, st.st_size))
    return frozenset(result)


def _grm_exists(grm: str) -> bool:
    """Return True if a valid ltdb .db file exists for the given grammar name."""
    path = os.path.join(current_directory, "db", grm)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    with sqlite3.connect(path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    return {"gold", "lexfreq", "meta", "sent", "types"}.issubset(tables)


_doctest_flag_cache: dict = {}


def _grm_has_doctests(grm):
    """Return True if the grammar db has doctest rows (cached by mtime/size)."""
    path = os.path.join(current_directory, "db", grm)
    try:
        st = os.stat(path)
    except OSError:
        return False
    key = (grm, st.st_mtime, st.st_size)
    if key not in _doctest_flag_cache:
        with sqlite3.connect(path) as conn:
            try:
                has = (
                    conn.execute("SELECT 1 FROM doctest LIMIT 1").fetchone()
                    is not None
                )
            except sqlite3.OperationalError:
                has = False
        _doctest_flag_cache[key] = has
    return _doctest_flag_cache[key]


def _db_for_stem(stem):
    """Return the .db filename for a mirror grammar stem."""
    return stem if stem.endswith(".db") else f"{stem}.db"


def _stem_for_grm(grm):
    """Return a mirror URL grammar stem for a .db filename or stem."""
    return grm[:-3] if grm and grm.endswith(".db") else grm


# Build logs live next to the database (copied into web/db/ by
# build-ltdb.sh alongside the .db/.dat files); each maps a stable
# "kind" for the download URL to the filename suffix grm2db.py/
# db2grew.py actually write.
_LOG_SUFFIXES = {
    "grammar": ".log",  # TDL read + docstring-test log (grm2db.py)
    "ace": "-ace.log",  # ACE compile log (grm2db.py --ace)
    "grew": "-grew.log",  # grew export conversion-failure log (db2grew.py)
}


def _available_logs(grm):
    """Return download links for this grammar's build logs that exist."""
    stem = _stem_for_grm(grm)
    db_dir = os.path.join(current_directory, "db")
    logs = []
    for kind, suffix in _LOG_SUFFIXES.items():
        if os.path.isfile(os.path.join(db_dir, f"{stem}{suffix}")):
            logs.append({"kind": kind, "url": url_for("download_log", grm=grm, kind=kind)})
    return logs


def _all_grammars():
    grammars = []
    for file in os.listdir(os.path.join(current_directory, "db")):
        if file.endswith(".db") and _grm_exists(file):
            grammars.append(file)
    grammars.sort()
    return grammars


@app.before_request
def _apply_grm_param():
    """Store ?grm= in the session when the requested grammar exists."""
    grm = sanitize_grm(request.args.get("grm", ""))
    if grm and _grm_exists(grm):
        session["grm"] = grm


_ace_bin = None


def _ace_error_message(exc: Exception, dat: str) -> str:
    """Return a human-readable error string for an ACE failure.

    Inspects the exception message to surface actionable diagnostics for the
    most common failure modes (version mismatch, missing binary, fd exhaustion).
    """
    msg = str(exc)
    if "closed on startup" in msg or "process closed" in msg:
        ace_bin = _ace_bin or "ace"
        return (
            f"ACE exited immediately when loading {os.path.basename(dat)}. "
            f"This usually means the grammar was compiled with a different version "
            f"of ACE than the one now in use ({ace_bin}). "
            "Rebuild the .dat file with: python scripts/grm2db.py --ace"
        )
    if "too many open files" in msg or "EMFILE" in msg:
        return (
            "ACE failed: too many open files. "
            "The server may be under heavy load; try again in a moment."
        )
    if "FileNotFoundError" in exc.__class__.__name__ or "No such file" in msg:
        return (
            "ACE binary not found. "
            "Run scripts/setup_ace.py to install a platform-appropriate binary, "
            "or set the ACE_BIN environment variable."
        )
    return f"ACE error: {msg}"


def find_ace():
    """Locate the ACE binary once and cache it.

    Checks ACE_BIN env var first, then system PATH, then the bundled binary
    under etc/ace-*/ as a last resort.  Run scripts/setup_ace.py to install
    a platform-appropriate bundled binary.
    """
    global _ace_bin
    if _ace_bin is not None:
        return _ace_bin
    env_bin = os.environ.get("ACE_BIN")
    if env_bin and os.access(env_bin, os.X_OK):
        _ace_bin = env_bin
        return _ace_bin
    found = shutil.which("ace")
    if found:
        _ace_bin = found
        return _ace_bin
    etc_dir = os.path.join(current_directory, "..", "etc")
    for candidate in sorted(pathlib.Path(etc_dir).glob("ace-*/ace"), reverse=True):
        if os.access(candidate, os.X_OK):
            _ace_bin = str(candidate)
            return _ace_bin
    raise FileNotFoundError(
        "ACE binary not found. Run scripts/setup_ace.py or install ACE."
    )


@app.route("/", methods=["GET", "POST"])
def home():
    """Render the home page with a grammar selector.

    Grammar summaries are cached by a directory fingerprint (filename, mtime,
    size) and recomputed only when the db/ directory changes.
    """
    global _summ_cache
    db_dir = os.path.join(current_directory, "db")
    fingerprint = _db_fingerprint(db_dir)
    if _summ_cache is None or _summ_cache[0] != fingerprint:
        grammars = _all_grammars()
        summ = get_short_summary(current_directory, grammars)
        _summ_cache = (fingerprint, grammars, summ)
    grammars, summ = _summ_cache[1], _summ_cache[2]
    if "grm" in request.form:
        grm = sanitize_grm(request.form["grm"])
        if grm is None:
            return jsonify({"error": "Invalid grammar name"}), 400
        if _grm_exists(grm):
            session["grm"] = grm
        return redirect(url_for("grammar"))
    if request.args.get("grm") and session.get("grm"):
        return redirect(url_for("grammar"))
    page = "index"
    # not cached with summ: a .dat can be (re)compiled without the .db
    # changing, so this must reflect the current filesystem state
    can_parse = {g: dat_path_for(g) is not None for g in grammars}
    return render_template(
        "index.html",
        page=page,
        title="LTDB",
        grammars=grammars,
        summ=summ,
        can_parse=can_parse,
        any_doctests=any(s.get("DOCTESTS") for s in summ.values()),
        grm=session.get("grm", None),
        home_blurb=HOME_BLURB_HTML,
    )


@app.route("/grammar.html")
def grammar():
    """show the grammar page"""
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    conn = get_db(current_directory, grm)
    md = get_md(conn)
    summ = get_summary(conn, grm)
    tsumm = get_tb_summary(conn, grm)
    return render_template(
        "grammar.html",
        title=md["GRAMMAR_NAME"],
        meta=md,
        grm=grm,
        summ=summ,
        tsumm=tsumm,
        logs=_available_logs(grm),
    )


def _render_grammar(grm):
    """Render grammar.html for the static mirror (see mirror_grammar).

    No `logs` here: build-log download is a live-backend-only feature
    (see download_log) with nothing for Flask-Frozen to freeze, and a
    link into it would 404 on the static mirror.
    """
    conn = get_db(current_directory, grm)
    md = get_md(conn)
    summ = get_summary(conn)
    tsumm = get_tb_summary(conn)
    return render_template(
        "grammar.html",
        title=md["GRAMMAR_NAME"],
        meta=md,
        grm=grm,
        summ=summ,
        tsumm=tsumm,
    )


@app.route("/log/<path:grm>/<kind>")
def download_log(grm, kind):
    """Download a grammar's build log (grammar/ACE/grew-export)."""
    suffix = _LOG_SUFFIXES.get(kind)
    if suffix is None:
        abort(404)
    stem = _stem_for_grm(grm)
    fname = f"{stem}{suffix}"
    db_dir = os.path.join(current_directory, "db")
    if not os.path.isfile(os.path.join(db_dir, fname)):
        abort(404)
    # send_from_directory rejects paths that would escape db_dir, so a
    # crafted grm (e.g. containing "../") can't read files outside it
    return send_from_directory(db_dir, fname, as_attachment=True)


@app.route("/rules.html")
def rules():
    """show the rules"""
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    conn = get_db(current_directory, grm)
    md = get_md(conn)
    data = get_rules(conn)

    return render_template("rules.html", meta=md, data=data, grm=grm)


def _render_rules(grm):
    conn = get_db(current_directory, grm)
    md = get_md(conn)
    data = get_rules(conn)
    return render_template("rules.html", meta=md, data=data, grm=grm)


@app.route("/ltypes.html")
def ltypes():
    """show the lexical types"""
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    conn = get_db(current_directory, grm)

    md = get_md(conn)
    data = get_ltypes(conn)
    words = get_wrds_by_ltypes(conn)
    return render_template(
        "ltypes.html",
        meta=md,
        data=data,
        words=words,
        grm=grm,
    )


def _render_ltypes(grm):
    conn = get_db(current_directory, grm)
    md = get_md(conn)
    data = get_ltypes(conn)
    words = get_wrds_by_ltypes(conn)
    return render_template(
        "ltypes.html",
        meta=md,
        data=data,
        words=words,
        grm=grm,
    )


@app.route("/doctests.html")
def doctests():
    """Show all docstring test results for the current grammar."""
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    conn = get_db(current_directory, grm)
    md = get_md(conn)
    rows = get_all_doctests(conn)
    return render_template("doctests.html", meta=md, rows=rows, grm=grm)



@app.route("/type/<query>")
def type(query):
    """show the type

    May do different things for different types
     * token-mapping-rule
     * post-generation-mapping-rule
     * lexical-filtering-rule
     * type
     * lex-type: show lexemes, words and sentences
     * lex-entry
     * generic-lex-entry
     * rule
     * lex-rule
     * labels
     * root
    """
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    return _render_type(grm, query)


def _render_type(grm, query):
    conn = get_db(current_directory, grm)
    include_examples = not _is_mirror_request()

    typeinfo = get_type(conn, query)
    lexids = []
    words = []
    maxp, phenomena = 0, []
    sents = []
    gold = []
    desc = ""

    if typeinfo:
        desc = docstring2html(query, typeinfo["docstring"])

        status = typeinfo["status"]

        if status == "lex-type":
            lexids = get_lxids(conn, query)

            words = get_wrds_by_lexids(conn, list(lexids.keys()))

            if include_examples:
                maxp, phenomena = get_phenomena_by_lexids(conn, list(lexids.keys()))

                sents = get_sents(conn, list(phenomena.keys()))

                gold = get_gold(conn, list(phenomena.keys()), convert=False)
        elif status == "lex-entry":
            lexids = get_lxid(conn, query)

            words = get_wrds_by_lexids(conn, list(lexids.keys()))

            if include_examples:
                maxp, phenomena = get_phenomena_by_lexids(conn, list(lexids.keys()))

                sents = get_sents(conn, list(phenomena.keys()))

                gold = get_gold(conn, list(phenomena.keys()), convert=False)

            lexids = []
            words = []

        elif status in ("root", "rule", "lex-rule"):
            if include_examples:
                maxp, phenomena = get_phenomena_by_cx(conn, query)

                sents = get_sents(conn, list(phenomena.keys()))

                gold = get_gold(conn, list(phenomena.keys()), convert=False)

            lexids = []
            words = []

    results = {
        "derivj": "Tree",
        "mrs": "MRS",
        "dmrsj": "DMRS",
        "mrsj": "[MRS]",
    }

    doctest_summary, doctest_examples = get_doctest(conn, query)

    return render_template(
        "type.html",
        query=query,
        info=typeinfo,
        grm=grm,
        desc=desc,
        tdl_html=tdl2html(typeinfo.get("tdl") if typeinfo else None, grm),
        pygments_css=PYGMENTS_CSS,
        lexids=lexids,
        words=words,
        maxp=maxp,
        phenomena=phenomena,
        sents=sents,
        gold=gold,
        results=results,
        doctest_summary=doctest_summary,
        doctest_examples=doctest_examples,
    )


@app.route("/ltdb/")
def mirror_home():
    """Static mirror landing page for Frozen-Flask."""
    grammars = _all_grammars()
    summ = get_short_summary(current_directory, grammars)
    return render_template(
        "index.html",
        page="index",
        title="LTDB Static Mirror",
        grammars=grammars,
        summ=summ,
        any_doctests=any(s.get("DOCTESTS") for s in summ.values()),
        grm=None,
        home_blurb=HOME_BLURB_HTML,
    )


@app.route("/sent/<profile>/<int:sid>")
def sent(profile, sid):
    """Show one treebanked sentence with its tree, MRS and DMRS.

    Deep links (e.g. from grew-match results) select the grammar with
    ?grm=<db>, which is handled by _apply_grm_param.
    """
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    conn = get_db(current_directory, grm)
    gold = get_gold(conn, [(profile, sid)], convert=False)
    return render_template(
        "sent.html", grm=grm, profile=profile, sid=sid, gold=gold
    )


@app.route("/ltdb/<path:grm>/grammar.html")
def mirror_grammar(grm):
    """Static mirror grammar summary page."""
    db = _db_for_stem(grm)
    if not _grm_exists(db):
        return redirect(url_for("mirror_home"))
    return _render_grammar(db)


@app.route("/ltdb/<path:grm>/rules.html")
def mirror_rules(grm):
    """Static mirror rules page."""
    db = _db_for_stem(grm)
    if not _grm_exists(db):
        return redirect(url_for("mirror_home"))
    return _render_rules(db)


@app.route("/ltdb/<path:grm>/ltypes.html")
def mirror_ltypes(grm):
    """Static mirror lexical type page."""
    db = _db_for_stem(grm)
    if not _grm_exists(db):
        return redirect(url_for("mirror_home"))
    return _render_ltypes(db)


@app.route("/ltdb/<path:grm>/type/<query>.html")
def mirror_type(grm, query):
    """Static mirror type page."""
    db = _db_for_stem(grm)
    if not _grm_exists(db):
        return redirect(url_for("mirror_home"))
    return _render_type(db, query)


@app.route("/ltdb/type.html")
def mirror_type_shell():
    """Static mirror client-side type viewer shell."""
    return render_template(
        "type_shell.html",
        title="LTDB Static Type Viewer",
        grm=None,
    )


def dat_path_for(grm):
    """Return the .dat path for a grammar, or None if missing or empty."""
    dat = os.path.join(current_directory, "db", grm[:-3] + ".dat")
    return dat if os.path.isfile(dat) and os.path.getsize(dat) > 0 else None


@app.route("/demo")
def demo():
    """Show the interactive parsing demo page."""
    grammars_with_dat = sorted(
        f
        for f in os.listdir(os.path.join(current_directory, "db"))
        if f.endswith(".db") and dat_path_for(f)
    )
    grm = session.get("grm")
    if grm and not dat_path_for(grm):
        grm = grammars_with_dat[0] if grammars_with_dat else None

    examples = {}
    can_generate = {}
    for g in grammars_with_dat:
        dbpath = os.path.join(current_directory, "db", g)
        with sqlite3.connect(dbpath) as conn:
            rows = dict(
                conn.execute(
                    "SELECT att, val FROM meta "
                    "WHERE att IN ('EXAMPLES', 'CAN_GENERATE')"
                )
            )
        try:
            examples[g] = json.loads(rows.get("EXAMPLES", "[]"))
        except (json.JSONDecodeError, TypeError):
            examples[g] = []
        can_generate[g] = bool(rows.get("CAN_GENERATE"))

    return render_template(
        "demo.html",
        title="LTDB Demo",
        grm=grm,
        grammars=grammars_with_dat,
        max_parse_chars=MAX_PARSE_CHARS,
        examples=examples,
        can_generate=can_generate,
    )


@app.route("/parse", methods=["POST"])
def parse_sentence():
    """Parse a sentence with ACE and return JSON in delphin-viz format."""
    grm = sanitize_grm(request.form.get("grm", "")) or session.get("grm")
    if not grm:
        return jsonify({"error": "No grammar selected"}), 400
    if sanitize_grm(grm) is None:
        return jsonify({"error": "Invalid grammar name"}), 400

    dat = dat_path_for(grm)
    if not dat:
        return jsonify(
            {
                "error": f"No compiled grammar (.dat) for {grm}. "
                f"Run grm2db.py --ace to build it."
            }
        ), 400

    input_text = request.form.get("input", "").strip()
    if not input_text:
        return jsonify({"error": "No input provided"}), 400
    if len(input_text) > MAX_PARSE_CHARS:
        return jsonify({"error": f"Input is too long (max {MAX_PARSE_CHARS} characters)"}), 400

    results_raw = request.form.get("results", "5")
    try:
        n_results = int(results_raw)
        if n_results < 1 or n_results > 10:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": f"Results must be an integer between 1 and 10"}), 400
    n_results = min(n_results, 10)
    want_derivation = request.form.get("derivation") == "json"
    want_mrs = request.form.get("mrs") == "json"
    want_dmrs = request.form.get("dmrs") == "json"

    if not _ace_slots.acquire(blocking=False):
        return jsonify({"error": "ACE is busy; please try again in a moment."}), 503

    try:
        # --udx=all annotates every node with its type (lexical type for
        # lexemes, phrase type for rules); --rooted-derivations puts the
        # matching root condition at the top of the tree
        response = _ace.parse(
            dat,
            input_text,
            executable=find_ace(),
            cmdargs=[f"-n{n_results}", "--udx=all", "--rooted-derivations"],
        )
    except Exception as e:
        return jsonify({"error": _ace_error_message(e, dat)}), 500
    finally:
        _ace_slots.release()

    results = []
    errors = []
    for i, result in enumerate(response.results()):
        r = {"result-id": i}

        if want_derivation:
            try:
                deriv = result.derivation()
                r["derivation"] = deriv.to_dict()
                # raw UDX string (ACE's own derivation format) for display
                r["derivation_str"] = deriv.to_udx()
            except Exception as e:
                r["derivation"] = None
                errors.append(f"result {i} derivation: {e}")

        if want_mrs or want_dmrs:
            mrs_obj = None
            try:
                mrs_obj = result.mrs()
                if want_mrs:
                    # mrs_str: simplemrs string for browser-side LTDBMrs rendering
                    # mrs: mrsjson dict kept for the generate endpoint
                    r["mrs_str"] = _simplemrs.encode(mrs_obj)
                    r["mrs"] = json.loads(_mrsjson.encode(mrs_obj))
            except Exception as e:
                r["mrs"] = None
                errors.append(f"result {i} mrs: {e}")
                # Fall back to the raw ACE MRS string so the browser can still
                # attempt rendering even when pydelphin cannot parse it
                if want_mrs:
                    raw = result.get("mrs")
                    if raw and isinstance(raw, str):
                        r["mrs_str"] = raw

            if want_dmrs:
                try:
                    r["dmrs"] = json.loads(
                        _dmrsjson.encode(_dmrs.from_mrs(mrs_obj))
                    )
                except Exception as e:
                    r["dmrs"] = None
                    errors.append(f"result {i} dmrs: {e}")

        results.append(r)

    return jsonify(
        {
            "input": input_text,
            "readings": len(results),
            "results": results,
            "errors": errors,
        }
    )


@app.route("/generate", methods=["POST"])
def generate_sentence():
    """Generate surface strings from an MRS using ACE."""
    grm = sanitize_grm(request.form.get("grm", "")) or session.get("grm")
    if not grm:
        return jsonify({"error": "No grammar selected"}), 400
    if sanitize_grm(grm) is None:
        return jsonify({"error": "Invalid grammar name"}), 400

    dat = dat_path_for(grm)
    if not dat:
        return jsonify({"error": f"No compiled grammar (.dat) for {grm}"}), 400

    mrs_json_str = request.form.get("mrs")
    if not mrs_json_str:
        return jsonify({"error": "No MRS provided"}), 400
    if len(mrs_json_str) > MAX_GENERATE_MRS_CHARS:
        return jsonify({"error": f"MRS is too large (max {MAX_GENERATE_MRS_CHARS} characters)"}), 400

    if not _ace_slots.acquire(blocking=False):
        return jsonify({"error": "ACE is busy; please try again in a moment."}), 503

    try:
        mrs_obj = _mrsjson.decode(mrs_json_str)
        mrs_str = _simplemrs.encode(mrs_obj)
        response = _ace.generate(dat, mrs_str, executable=find_ace())
        surfaces = [
            r.get("surface", "") for r in response.results() if r.get("surface")
        ]
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": _ace_error_message(e, dat)}), 500
    finally:
        _ace_slots.release()

    if not surfaces:
        notes = response.get("NOTES", [])
        unknown = [n for n in notes if "unknown in the semantic index" in n]
        if unknown:
            return jsonify(
                {
                    "error": "This grammar is not configured for generation "
                    "(missing generation-roots in ACE config). "
                    "Try the ERG instead.",
                    "results": [],
                }
            )

    return jsonify({"results": surfaces})


@app.route("/help")
def help():
    """Show the help/documentation page."""
    return render_template("help.html", title="LTDB Help", grm=session.get("grm"))


@app.route("/search", methods=["POST"])
def submit_fsearch():
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    conn = get_db(current_directory, grm)

    searched = request.form.get("search", "").strip()
    if not searched:
        return redirect(url_for("home"))

    results = search_for(conn, query=searched)

    return render_template("searched.html", grm=grm, searched=searched, results=results)
