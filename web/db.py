import os
import sqlite3
from collections import defaultdict as dd

from flask import g

from .ltdb import deriv_to_dict, mrs_to_dicts

### limit for most queries
### not much point showing more examples than this
###
lim = 512
sentlim = 8


def get_db(root, db):
    key = f"db_{root}_{db}"
    conn = g.get(key)
    if conn is None:
        conn = sqlite3.connect(os.path.join(root, f"db/{db}"))
        setattr(g, key, conn)
    return conn


def close_db(e=None):
    for attr in list(vars(g)):
        if attr.startswith("db_"):
            conn = g.pop(attr, None)
            if conn is not None:
                conn.close()


############################################################


def holders(lst):
    """
    return the parameter placeholders for a query
    """
    return ",".join(["?"] * len(lst))


def get_md(conn):
    c = conn.cursor()
    c.execute("SELECT att, val FROM meta")
    md = dict()
    for att, val in c:
        md[att] = val
    return md


def get_rules(conn):
    c = conn.cursor()

    c.execute("""SELECT types.typ, parents, lname, status,
    COALESCE(freq,0), arity, head
    FROM types left join typfreq on types.typ=typfreq.typ
    WHERE status in ('rule', 'lex-rule', 'inf-rule', 'root') 
    ORDER BY status, types.typ""")

    results = c.fetchall()
    return results


def get_ltypes(conn):
    c = conn.cursor()

    c.execute("""SELECT lex.typ, lname, count(lex.typ), COALESCE(freq,0), '' 
    FROM types LEFT JOIN lex ON types.typ = lex.typ
    LEFT JOIN typfreq ON lex.typ = typfreq.typ
    WHERE status ='lex-type' 
    GROUP BY lex.typ ORDER BY lex.typ""")
    results = c.fetchall()

    return results


def search_for(conn, query):
    """
    Look up the query with glb in a variety of tables


    return a dictionary of lists of results
    """
    c = conn.cursor()
    results = dd(list)

    ## lemmas
    c.execute(
        """SELECT orth, typ, 'freq', 'words'
    FROM lex
    WHERE orth glob ?""",
        [query],
    )
    if returned := c.fetchall():
        results["lemmas"] = returned

    ## predicates
    c.execute(
        """SELECT pred, lexid, typ FROM lex WHERE pred glob ?
    UNION SELECT altpred, lexid, typ FROM lex WHERE altpred glob ?""",
        [query, query],
    )
    if returned := c.fetchall():
        results["predicates"] = returned

    ## types
    c.execute(
        """SELECT types.typ, parents, status, freq,
    lname 
    FROM types left join typfreq on types.typ=typfreq.typ
    WHERE types.typ glob  ?
    ORDER BY status, types.typ""",
        [query],
    )

    for typ, parents, status, freq, lname in c:
        results[status].append((typ, parents, freq, lname))

    return results


def get_type(conn, typ):
    """Return a dict of type info, or {} if the type does not exist."""
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute(
            """SELECT  parents,  children,  cat,  val,
        cont, definition,  status, arity, head,
        lname, tdl.docstring,
        criteria, reference, todo,
        src, line, kind, tdl
        FROM types LEFT JOIN tdl
        ON types.typ = tdl.typ
        WHERE types.typ=? limit 1""",
            (typ,),
        )
        row = c.fetchone()
        return dict(zip(row.keys(), row)) if row else {}
    finally:
        conn.row_factory = prev_factory


def get_lxids(conn, typ):
    """
    return lexical items that have this lexical type
    or {} if the type is not a lexical type
    """
    c = conn.cursor()
    c.execute(
        f"""SELECT lex.lexid, orth, COALESCE(freq,0) FROM lex 
             LEFT JOIN lexfreq ON lex.lexid = lexfreq.lexid
             WHERE typ=? 
    ORDER BY freq DESC
    LIMIT {lim // 2}""",
        (typ,),
    )
    lem = dict()
    for lxid, orth, freq in c:
        lem[lxid] = (orth, freq)

    return lem


def get_lxid(conn, typ):
    """
    return lexical item
    """
    c = conn.cursor()
    c.execute(
        f"""SELECT lexid, word, COALESCE(freq,0) FROM lexfreq
             WHERE lexid=? 
    LIMIT {lim // 2}""",
        (typ,),
    )
    lem = dict()
    for lxid, orth, freq in c:
        lem[lxid] = (orth, freq)

    return lem


def get_wrds_by_ltypes(conn, wlimit=5):
    """
    return a dictionary with words and frequencies
    for all the lexical types
    """
    words = dd(lambda: dd(int))
    c = conn.cursor()

    c.execute(
        """ 
    WITH types_with_words AS (
        SELECT DISTINCT lex.typ
        FROM lex
        JOIN lexfreq ON lex.lexid = lexfreq.lexid
    ),
    
    top_words AS (
        SELECT typ, word, freq AS word_count
        FROM (
            SELECT 
                lex.typ, 
                lexfreq.word, 
                lexfreq.freq,
                ROW_NUMBER() OVER (
                    PARTITION BY lex.typ ORDER BY lexfreq.freq DESC) AS rank
            FROM lex
            JOIN lexfreq ON lex.lexid = lexfreq.lexid
            GROUP BY lex.typ, lexfreq.word, lexfreq.freq
        ) 
        WHERE rank <= ?
    ),
    
    -- Second part: Types without words
    types_without_words AS (
        SELECT l.typ, l.orth AS word
        FROM lex l
        WHERE NOT EXISTS (SELECT 1 FROM types_with_words t WHERE t.typ = l.typ)
        GROUP BY l.typ, l.orth
    ),
    
    top_orths AS (
        SELECT typ, word
        FROM (
            SELECT 
                typ, 
                word,
                ROW_NUMBER() OVER (PARTITION BY typ ORDER BY word) AS rank
            FROM types_without_words
        )
        WHERE rank <= ?
    )
    
    -- Combine and return results
    SELECT typ, word, word_count FROM top_words
    
    UNION ALL
    
    SELECT typ, word, 0 AS word_count FROM top_orths
    
    ORDER BY typ, word_count DESC, word
    """,
        (wlimit, wlimit),
    )
    for ltype, word, freq in c:
        words[ltype][word] = freq
    return words


def get_wrds_by_lexids(conn, lexids):
    """
    return a dictionary with words and frequencies for each lexid
    words[lexid][word] = freq
    """
    if not lexids:
        return dd(lambda: dd(int))
    c = conn.cursor()
    words = dd(lambda: dd(int))
    c.execute(
        f"""
    SELECT lexid, word, count(word) FROM sent
    WHERE (lexid IN ({holders(lexids)}))
    GROUP BY lexid, word 
    ORDER BY lexid
    LIMIT {lim}""",
        lexids,
    )
    for lexid, word, freq in c:
        words[lexid][word] = freq
    return words


def calculate_offset_limit(N, L):
    """
    Calculate appropriate OFFSET and LIMIT values for SQL query.

    Args:
        N (int): Total number of available examples
        L (int): Desired number of examples

    Returns:
        tuple: (offset, limit) values to use in SQL query
    """
    if L >= N:
        # If we want more examples than exist, return all
        offset, limit = 0, N
    else:
        # Skip first 20% of examples
        offset = round(N * 0.2)

        # Make sure we still have at least L examples
        remaining = N - offset
        if remaining < L:
            # Adjust offset down so we get at least L examples
            offset = N - L
        limit = L
    return offset, limit


# Optimal sentence length range for GDEX scoring (easily adjusted here).
# Shorter than the original GDEX standard (10–25) because grammar parse trees
# grow complex quickly; 6–18 balances informativeness with readability.
_GDEX_OPT_MIN: int = 6
_GDEX_OPT_MAX: int = 18


def _is_fragment_cx(cx: str) -> bool:
    """Return True if cx is a fragment construction type.

    Fragment constructions (names containing '_frg') parse sub-sentential
    inputs such as section headings or isolated phrases.  Their examples are
    expected to be fragments, so the whole-sentence and position criteria must
    not be applied against them.
    """
    return "_frg" in cx


def _gdex_score_sql(
    kw_pos_expr: str,
    len_expr: str,
    sent_expr: str,
    fragment: bool = False,
    rule_count_expr: str | None = None,
) -> str:
    """Return a SQL expression computing a GDEX-inspired quality score (0–1).

    Combines up to four soft ranking preferences adapted from Kilgarriff et al.
    (2008) and Kosem et al. (2019) for grammar treebank corpora:

    1. Sentence length — optimal range ``_GDEX_OPT_MIN``–``_GDEX_OPT_MAX``
       words (default 6–18); linear ramp below, harmonic decay above.
       Fragment constructions use a tighter range (2–5 words ideal, 6–8
       acceptable) because their canonical examples are short phrases.
    2. Whole sentence — prefer sentences ending in terminal punctuation (.!?);
       for fragment constructions the rule is inverted (penalise .!? endings,
       as genuine fragments should not look like complete sentences).
    3. Keyword position — prefer the target not at word index 0.
       Neutral (1.0) for fragment constructions (which naturally start there).
    4. Derivation simplicity (optional) — if ``rule_count_expr`` is given,
       prefer sentences with fewer construction applications in ``typind``
       (proxy for shallower parse trees).

    All criteria are ranking weights, not hard filters: the candidate pool is
    already constrained by the queried construction or lexid.

    Args:
        kw_pos_expr: SQL expression for the 0-based keyword word index.
        len_expr: SQL expression for the sentence length (max wid).
        sent_expr: SQL expression for the full sentence string (may be NULL).
        fragment: If True, apply fragment-type scoring (short length range,
            neutral terminal and position criteria).
        rule_count_expr: Optional SQL expression giving the total number of
            construction applications for the sentence (from ``typind``).
            When provided, adds a derivation-simplicity factor.
    """
    if fragment:
        # Prefer short genuine-fragment examples (2–5 words ideal).
        # Fragments should NOT look like complete sentences, so terminal
        # punctuation is penalised (inverse of the full-sentence rule).
        # Position criterion is neutral (fragments naturally start at pos 0).
        len_score = f"""CASE
            WHEN {len_expr} < 2   THEN 0.0
            WHEN {len_expr} <= 5  THEN 1.0
            WHEN {len_expr} <= 8  THEN 0.8
            ELSE 4.0 / CAST({len_expr} AS REAL)
        END"""
        terminal_score = (
            f"CASE WHEN SUBSTR({sent_expr}, -1) IN ('.', '!', '?')"
            f" THEN 0.7 ELSE 1.0 END"
        )
        pos_score = "1.0"
    else:
        lo, hi = _GDEX_OPT_MIN, _GDEX_OPT_MAX
        len_score = f"""CASE
            WHEN {len_expr} < 3              THEN 0.0
            WHEN {len_expr} < {lo}           THEN CAST({len_expr} AS REAL) / {lo}.0
            WHEN {len_expr} <= {hi}          THEN 1.0
            ELSE {hi}.0 / CAST({len_expr} AS REAL)
        END"""
        terminal_score = (
            f"CASE WHEN SUBSTR({sent_expr}, -1) IN ('.', '!', '?')"
            f" THEN 1.0 ELSE 0.7 END"
        )
        pos_score = f"""CASE
            WHEN {len_expr} = 0                                 THEN 0.8
            WHEN CAST({kw_pos_expr} AS REAL) / {len_expr} > 0.1 THEN 1.0
            ELSE 0.8
        END"""

    # Derivation density = rules / sentence_length; average ERG sentence ≈ 3.
    # Score 1.0 for very simple trees, decays softly for denser derivations.
    rule_factor = (
        f"\n        * 5.0 / (5.0 + COALESCE("
        f"CAST({rule_count_expr} AS REAL) / NULLIF(CAST({len_expr} AS REAL), 1.0)"
        f", 3.0))"
        if rule_count_expr
        else ""
    )
    # Corpus markup (⌊…⌋ annotation) indicates problematic/edited text; exclude.
    markup_factor = (
        f"\n        * CASE WHEN INSTR({sent_expr}, '⌊') > 0 THEN 0.0 ELSE 1.0 END"
    )
    # Technical-text penalty: count atypical chars ([, {, \, |) that almost never
    # appear in natural prose.  Score = 5 / (5 + count), so one such char gives
    # ~0.83, six give ~0.45, driving regex/code sentences well below natural text.
    _tc = sent_expr
    tech_count = (
        f"(LENGTH({_tc})"
        f" - LENGTH(REPLACE({_tc}, '[', ''))"
        f" + LENGTH({_tc}) - LENGTH(REPLACE({_tc}, '{{', ''))"
        f" + LENGTH({_tc}) - LENGTH(REPLACE({_tc}, '\\', ''))"
        f" + LENGTH({_tc}) - LENGTH(REPLACE({_tc}, '|', '')))"
    )
    punct_factor = f"\n        * 5.0 / (5.0 + {tech_count})"
    return (
        f"\n        {len_score}"
        f"\n        * {terminal_score}"
        f"\n        * {pos_score}"
        f"{rule_factor}"
        f"{markup_factor}"
        f"{punct_factor}"
    )


def get_phenomena_by_lexids(conn, lexids):
    """Return sentences containing any of the given lexids, ranked by GDEX score.

    Args:
        conn: SQLite connection.
        lexids: List of lexid strings to match.

    Returns:
        Tuple of (total_count, phenomena) where phenomena maps
        (profile, sid) → list of (from, to) highlight spans.
    """
    if not lexids:
        return 0, dd(list)

    c = conn.cursor()
    c.execute(
        f"""SELECT COUNT(*)
        FROM (
            SELECT DISTINCT profile, sid
            FROM sent
            WHERE lexid IN ({holders(lexids)})
        )""",
        lexids,
    )
    result = c.fetchone()
    maxp = result[0] if result else 0

    gdex = _gdex_score_sql(
        kw_pos_expr="MIN(a.wid)",
        len_expr="MAX(b.wid)",
        sent_expr="g.sent",
        rule_count_expr="COALESCE(g.rule_count, 10)",
    )
    phenomena = dd(list)
    c.execute(
        f"""SELECT a.profile, a.sid, MIN(a.wid) AS kw_wid,
               {gdex} AS gdex_score
        FROM sent AS a
        LEFT JOIN sent AS b
            ON a.profile = b.profile AND a.sid = b.sid
        LEFT JOIN gold AS g
            ON a.profile = g.profile AND a.sid = g.sid
        WHERE a.lexid IN ({holders(lexids)})
        GROUP BY a.profile, a.sid
        ORDER BY gdex_score DESC
        LIMIT ?""",
        lexids + [sentlim],
    )
    for profile, sid, wid, _score in c:
        phenomena[profile, sid].append((wid, wid + 1))
    return maxp, phenomena


def get_phenomena_by_cx(conn, cx):
    """Return sentences using construction cx, ranked by GDEX score.

    Used for rules, roots, dlr, iflr.

    Args:
        conn: SQLite connection.
        cx: Type name string (construction identifier).

    Returns:
        Tuple of (total_count, phenomena) where phenomena maps
        (profile, sid) → list of (kara, made) highlight spans.
    """
    c = conn.cursor()
    c.execute(
        """SELECT COUNT(*)
        FROM (
            SELECT DISTINCT profile, sid
            FROM typind
            WHERE typ = ?
        )""",
        (cx,),
    )
    result = c.fetchone()
    maxp = result[0] if result else 0

    is_frg = _is_fragment_cx(cx)
    gdex = _gdex_score_sql(
        kw_pos_expr="MIN(COALESCE(a.kara, 0))",
        len_expr="MAX(b.wid)",
        sent_expr="g.sent",
        fragment=is_frg,
        rule_count_expr="COALESCE(g.rule_count, 10)",
    )
    phenomena = dd(list)
    c.execute(
        f"""SELECT a.profile, a.sid,
               MIN(COALESCE(a.kara, 0)) AS kara,
               COALESCE(MAX(a.made), MAX(b.wid) + 1) AS made,
               {gdex} AS gdex_score
        FROM typind AS a
        LEFT JOIN sent AS b
            ON a.profile = b.profile AND a.sid = b.sid
        LEFT JOIN gold AS g
            ON a.profile = g.profile AND a.sid = g.sid
        WHERE a.typ = ?
        GROUP BY a.profile, a.sid
        ORDER BY gdex_score DESC
        LIMIT ?""",
        (cx, sentlim),
    )
    for profile, sid, kara, made, _score in c:
        phenomena[profile, sid].append((kara, made))

    return maxp, phenomena


def get_sents(conn, psids):
    """
    given a list of (profile, sid)
    return enough information to display it
    sent[(p, s)][wid] = word
    """
    if not psids:
        return dd(dict)
    c = conn.cursor()
    sents = dd(dict)
    conditions = " OR ".join(["(profile=? AND sid=?)"] * len(psids))
    params = [x for ps in psids for x in ps]
    c.execute(
        f"""SELECT profile, sid, wid, word, lexid FROM sent
    WHERE {conditions}
    ORDER BY profile, sid, wid""",
        params,
    )
    for prof, sid, wid, word, lexid in c:
        sents[prof, sid][wid] = word
    return sents


def get_gold(conn, psids, convert=True):
    """Given a list of (profile, sid), return per-sentence linguistic data.

    Keys per (profile, sid): 'mrs', 'mrsj', 'dmrsj', 'derivj', 'deriv', 'item'.
    If convert is true, 'derivj'/'mrsj'/'dmrsj' are computed on the fly. The
    raw 'deriv' and 'mrs' strings are always returned for browser rendering.
    """
    if not psids:
        return dd(dict)
    c = conn.cursor()
    data = dd(dict)
    conditions = " OR ".join(["(profile=? AND sid=?)"] * len(psids))
    params = [x for ps in psids for x in ps]
    c.execute(
        f"SELECT profile, sid, deriv, mrs, sent FROM gold WHERE {conditions}",
        params,
    )
    for prof, sid, deriv, mrs, sent in c:
        data[prof, sid]["mrs"] = mrs
        if convert:
            mrs_d, dmrs_d = mrs_to_dicts(mrs)
            data[prof, sid]["mrsj"] = mrs_d
            data[prof, sid]["dmrsj"] = dmrs_d
            data[prof, sid]["derivj"] = deriv_to_dict(deriv)
        else:
            data[prof, sid]["mrsj"] = None
            data[prof, sid]["dmrsj"] = None
            data[prof, sid]["derivj"] = None
        # Raw UDF; shown as fallback when derivj is None.
        data[prof, sid]["deriv"] = deriv
        data[prof, sid]["item"] = sent
    return data


def get_summary(conn, grm=None):
    """
    Return a summary of the grammar"
    """
    if grm and grm in _summary_cache:
        return _summary_cache[grm]
    c = conn.cursor()
    summary = dict()
    c.execute("""-- Get counts for regular types using typfreq
    SELECT t.status, 
           COUNT(DISTINCT t.typ) AS total_types,
           COUNT(DISTINCT tf.typ) AS types_in_corpus
    FROM types t
    LEFT JOIN typfreq tf ON t.typ = tf.typ
    WHERE t.status NOT IN ('lex-entry', 'generic-lex-entry')
    GROUP BY t.status

    UNION ALL

    -- Get counts for lex-entry types using lexfreq
    SELECT t.status,
           COUNT(DISTINCT t.typ) AS total_types,
           COUNT(DISTINCT lf.lexid) AS types_in_corpus
    FROM types t
    LEFT JOIN lexfreq lf ON t.typ = lf.lexid
    WHERE t.status IN ('lex-entry', 'generic-lex-entry')
    GROUP BY t.status

    ORDER BY status;""")
    for status, freq, cfreq in c:
        summary[status] = freq, cfreq

    if grm:
        _summary_cache[grm] = summary
    return summary


def get_tb_summary(conn, grm=None):
    """
    Return a summary of the treebank"
    """
    if grm and grm in _tb_summary_cache:
        return _tb_summary_cache[grm]
    c = conn.cursor()
    summary = dict()
    c.execute("""
    SELECT COUNT(DISTINCT profile) AS profiles,
    COUNT(DISTINCT sid || ',' || profile) AS sents,
    COUNT(word) AS words FROM sent""")
    profiles, sents, words = c.fetchone()
    summary["Profiles"] = profiles
    summary["Sents"] = sents
    summary["Tokens"] = words

    if grm:
        _tb_summary_cache[grm] = summary
    return summary


_short_summary_cache: dict = {}
_summary_cache: dict = {}
_tb_summary_cache: dict = {}


def _has_ltdb_summary_schema(path):
    """Return True if a database has the tables used by summary queries."""
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


def _valid_grammar_files(db_dir):
    """Return grammar database filenames with the LTDB summary schema."""
    return sorted(
        file
        for file in os.listdir(db_dir)
        if file.endswith(".db")
        and _has_ltdb_summary_schema(os.path.join(db_dir, file))
    )


def get_grammar_names(root):
    """Return sorted list of valid grammar .db filenames found in root/db/."""
    return _valid_grammar_files(os.path.join(root, "db"))


def warm_caches(current_directory):
    """Pre-populate all summary caches at server startup.

    Called once per worker process so that no user request ever blocks on
    the slow COUNT queries.
    """
    db_dir = os.path.join(current_directory, "db")
    if not os.path.isdir(db_dir):
        return
    grammars = _valid_grammar_files(db_dir)
    get_short_summary(current_directory, grammars)
    for grm in grammars:
        with sqlite3.connect(os.path.join(db_dir, grm)) as conn:
            get_summary(conn, grm)
            get_tb_summary(conn, grm)


def get_all_doctests(conn):
    """Return all doctest results for the grammar, grouped for a summary page.

    Returns a list of dicts (one per row), sorted by typ then kind then sent,
    or None if the doctest table does not exist or is empty.
    """
    c = conn.cursor()
    try:
        c.execute(
            """SELECT typ, sent, kind, wf, n_parses, type_found, pass, verdict
               FROM doctest ORDER BY typ, kind, sent"""
        )
    except sqlite3.OperationalError:
        return None

    rows = [
        {
            "typ": typ,
            "sent": sent,
            "kind": kind,
            "wf": wf,
            "n_parses": n_parses,
            "type_found": type_found,
            "pass": ok,
            "verdict": verdict,
        }
        for typ, sent, kind, wf, n_parses, type_found, ok, verdict in c
    ]
    return rows or None


def get_doctest(conn, typ):
    """Return docstring test results for *typ*.

    Returns a tuple (summary, examples) where:
      summary  — dict mapping kind ('ex','nex','mex') →
                 {'total': int, 'pass': int, 'fail': dict[verdict→count]}
      examples — list of dicts with keys: sent, kind, wf, n_parses,
                 type_found, pass, verdict

    Returns (None, None) if the doctest table does not exist or has no rows
    for this type.
    """
    c = conn.cursor()
    try:
        c.execute(
            """SELECT sent, kind, wf, n_parses, type_found, pass, verdict
               FROM doctest WHERE typ=? ORDER BY kind, sent""",
            (typ,),
        )
    except sqlite3.OperationalError:
        return None, None

    examples = [
        {
            "sent": sent,
            "kind": kind,
            "wf": wf,
            "n_parses": n_parses,
            "type_found": type_found,
            "pass": ok,
            "verdict": verdict,
        }
        for sent, kind, wf, n_parses, type_found, ok, verdict in c
    ]
    if not examples:
        return None, None

    summary = {}
    for ex in examples:
        k = ex["kind"]
        if k not in summary:
            summary[k] = {"total": 0, "pass": 0, "fail": {}}
        summary[k]["total"] += 1
        if ex["pass"]:
            summary[k]["pass"] += 1
        else:
            v = ex["verdict"]
            summary[k]["fail"][v] = summary[k]["fail"].get(v, 0) + 1

    return summary, examples


def get_short_summary(current_directory, grammars):
    """
    Return a brief summary of all the grammars

    you should give a dictionary of dictionaries
    summ[grm]['Name'] = GRAMMAR_NAME
    website: website
    rules: number of rules
    lexicon: number of entries
    trees: number of trees
    license: url
    """
    summ = dict()
    for grm in grammars:
        if grm in _short_summary_cache:
            summ[grm] = _short_summary_cache[grm]
            continue
        dbpath = os.path.join(current_directory, f"db/{grm}")
        with sqlite3.connect(dbpath) as conn:
            c = conn.cursor()
            c.execute("""
            SELECT att, val
            FROM meta
            WHERE att IN ('GRAMMAR_NAME', 'WEBSITE', 'LICENSE')
            UNION
            select 'RULES', count(*) from types
            where status in ('rule', 'lex-rule')
            UNION
            select 'LEXICON', count(*) from types
            where status in ('lex-entry', 'generic-lex-entry')
            UNION
            SELECT 'TREES', COUNT(DISTINCT sid || ',' || profile)
            FROM sent
            """)
            _short_summary_cache[grm] = dict(c.fetchall())
        summ[grm] = _short_summary_cache[grm]
    return summ
