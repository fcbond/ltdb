"""Route declaration."""

import json
import os
import pathlib
import re as _re
import shutil
import sys
import traceback

from delphin.highlight import TDLLexer
from flask import current_app as app
from flask import jsonify, redirect, render_template, request, session, url_for
from pygments import highlight
from pygments.formatters import HtmlFormatter

from .db import (
    get_db,
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
from .ltdb import rst2html

_tdl_formatter = HtmlFormatter(style="friendly")
PYGMENTS_CSS = _tdl_formatter.get_style_defs(".highlight")
_type_span_re = _re.compile(r'<span class="(nc|n)">([^<]+)</span>')


def tdl2html(tdl_str):
    """Render a TDL string to syntax-highlighted HTML with clickable type links."""
    if not tdl_str:
        return ""
    html = highlight(tdl_str, TDLLexer(), _tdl_formatter)
    return _type_span_re.sub(
        lambda m: (
            f'<a href="{url_for("type", query=m.group(2))}"'
            f' class="{m.group(1)}">{m.group(2)}</a>'
        ),
        html,
    )


current_directory = os.path.abspath(os.path.dirname(__file__))


_ace_bin = None


def find_ace():
    """Locate the ACE binary once and cache it."""
    global _ace_bin
    if _ace_bin is not None:
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
    """show the home page"""
    grammars = []
    # Iterate directory
    for file in os.listdir(os.path.join(current_directory, "db")):
        # check only text files
        if file.endswith(".db"):
            grammars.append(file)
    grammars.sort()
    summ = get_short_summary(current_directory, grammars)
    if "grm" in request.form:
        session["grm"] = request.form["grm"]
        return redirect(url_for("grammar"))
    page = "index"
    return render_template(
        "index.html",
        page=page,
        title="LTDB",
        grammars=grammars,
        summ=summ,
        grm=session.get("grm", None),
    )


@app.route("/grammar.html")
def grammar():
    """show the grammar page"""
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
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
    conn = get_db(current_directory, grm)

    typeinfo = get_type(conn, query)
    lexids = []
    words = []
    maxp, phenomena = 0, []
    sents = []
    gold = []
    desc = ""

    if typeinfo:
        desc = rst2html(query, typeinfo["docstring"])

        status = typeinfo["status"]

        if status == "lex-type":
            lexids = get_lxids(conn, query)

            words = get_wrds_by_lexids(conn, list(lexids.keys()))

            maxp, phenomena = get_phenomena_by_lexids(conn, list(lexids.keys()))

            sents = get_sents(conn, list(phenomena.keys()))

            gold = get_gold(conn, list(phenomena.keys()))
        elif status == "lex-entry":
            lexids = get_lxid(conn, query)

            words = get_wrds_by_lexids(conn, list(lexids.keys()))

            maxp, phenomena = get_phenomena_by_lexids(conn, list(lexids.keys()))

            sents = get_sents(conn, list(phenomena.keys()))

            gold = get_gold(conn, list(phenomena.keys()))

            lexids = []
            words = []

        elif status in ("root", "rule", "lex-rule"):
            maxp, phenomena = get_phenomena_by_cx(conn, query)

            sents = get_sents(conn, list(phenomena.keys()))

            gold = get_gold(conn, list(phenomena.keys()))

            lexids = []
            words = []

    results = {
        "derivj": "Tree",
        "mrs": "MRS",
        "dmrsj": "DMRS",
        "mrsj": "[MRS]",
    }

    return render_template(
        "type.html",
        query=query,
        info=typeinfo,
        grm=grm,
        desc=desc,
        tdl_html=tdl2html(typeinfo.get("tdl") if typeinfo else None),
        pygments_css=PYGMENTS_CSS,
        lexids=lexids,
        words=words,
        maxp=maxp,
        phenomena=phenomena,
        sents=sents,
        gold=gold,
        results=results,
    )


def dat_path_for(grm):
    """Return the .dat path for a grammar filename, or None if it doesn't exist."""
    dat = os.path.join(current_directory, "db", grm[:-3] + ".dat")
    return dat if os.path.exists(dat) else None


@app.route("/demo")
def demo():
    """Show the interactive parsing demo page."""
    grammars_with_dat = sorted(
        f
        for f in os.listdir(os.path.join(current_directory, "db"))
        if f.endswith(".db") and dat_path_for(f)
    )
    grm = session.get("grm")
    # Fall back to first available grammar if current one has no .dat
    if grm and not dat_path_for(grm):
        grm = grammars_with_dat[0] if grammars_with_dat else None
    return render_template(
        "demo.html", title="LTDB Demo", grm=grm, grammars=grammars_with_dat
    )


@app.route("/parse", methods=["POST"])
def parse_sentence():
    """Parse a sentence with ACE and return JSON in delphin-viz format."""
    from delphin import ace
    from delphin import dmrs as dmrs_module
    from delphin.codecs import dmrsjson, mrsjson

    grm = request.form.get("grm") or session.get("grm")
    if not grm:
        return jsonify({"error": "No grammar selected"}), 400

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

    n_results = min(int(request.form.get("results", 5)), 10)
    want_derivation = request.form.get("derivation") == "json"
    want_mrs = request.form.get("mrs") == "json"
    want_dmrs = request.form.get("dmrs") == "json"

    try:
        response = ace.parse(
            dat, input_text, executable=find_ace(), cmdargs=[f"-n{n_results}"]
        )
    except Exception as e:
        return jsonify({"error": f"ACE error: {e}"}), 500

    results = []
    errors = []
    for i, result in enumerate(response.results()):
        r = {"result-id": i}

        if want_derivation:
            try:
                r["derivation"] = result.derivation().to_dict(
                    fields=["id", "entity", "score", "form", "tokens"]
                )
            except Exception as e:
                r["derivation"] = None
                errors.append(f"result {i} derivation: {e}")

        if want_mrs or want_dmrs:
            mrs_obj = None
            try:
                mrs_obj = result.mrs()
                if want_mrs:
                    r["mrs"] = json.loads(mrsjson.encode(mrs_obj))
            except Exception as e:
                r["mrs"] = None
                errors.append(f"result {i} mrs: {e}")

            if want_dmrs:
                try:
                    r["dmrs"] = json.loads(
                        dmrsjson.encode(dmrs_module.from_mrs(mrs_obj))
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
    from delphin import ace
    from delphin.codecs import mrsjson, simplemrs

    grm = request.form.get("grm") or session.get("grm")
    if not grm:
        return jsonify({"error": "No grammar selected"}), 400

    dat = dat_path_for(grm)
    if not dat:
        return jsonify({"error": f"No compiled grammar (.dat) for {grm}"}), 400

    mrs_json_str = request.form.get("mrs")
    if not mrs_json_str:
        return jsonify({"error": "No MRS provided"}), 400

    try:
        mrs_obj = mrsjson.decode(mrs_json_str)
        mrs_str = simplemrs.encode(mrs_obj)
        response = ace.generate(dat, mrs_str, executable=find_ace())
        surfaces = [
            r.get("surface", "") for r in response.results() if r.get("surface")
        ]
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500

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


@app.route("/search", methods=["POST"])
def submit_fsearch():
    grm = session.get("grm")
    if not grm:
        return redirect(url_for("home"))
    conn = get_db(current_directory, grm)

    searched = request.form["search"]

    results = search_for(conn, query=searched)

    return render_template("searched.html", grm=grm, searched=searched, results=results)
