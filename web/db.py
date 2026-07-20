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
        f"""SELECT lex.lexid, lex.orth, COALESCE(SUM(lexfreq.freq), 0) AS freq
             FROM lex
             LEFT JOIN lexfreq ON lex.lexid = lexfreq.lexid
             WHERE lex.typ=?
    GROUP BY lex.lexid, lex.orth
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


def get_phenomena_by_lexids(conn, lexids):
    """
    return a dict of profile, sid, with the lexid in question marked
    phenom[profile, sid = [(from, to), ....]

    Pick short sentences, starting 20% in
    """
    ### get the total number
    c = conn.cursor()
    c.execute(
        f"""SELECT COUNT(*) 
    FROM (
    SELECT DISTINCT profile, sid 
    FROM sent 
    WHERE lexid IN ({holders(lexids)})
    )""",
        (lexids),
    )
    result = c.fetchone()
    if result:
        maxp = result[0]
    else:
        maxp = 0

    offset, limit = calculate_offset_limit(maxp, sentlim)

    ### get a sample
    phenomena = dd(list)
    c.execute(
        f"""SELECT a.profile, a.sid, a.wid , max(b.wid)
    FROM sent as a LEFT JOIN sent as b
    ON a.profile=b.profile and a.sid=b.sid
    WHERE a.lexid IN ({holders(lexids)})
    GROUP BY b.profile, b.sid
    ORDER BY max(b.wid) 
    LIMIT ? OFFSET ?""",
        (lexids + [limit, offset]),
    )
    for profile, sid, wid, max in c:
        phenomena[profile, sid].append((wid, wid + 1))
    return maxp, phenomena


def get_phenomena_by_cx(conn, cx):
    """
    return a dict of profile, sid, with the cx in question marked
    use for rules, roots, dlr, iflr,

    phenom[profile, sid = [(from, to), ....]
    try to pick short sentences
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
    if result:
        maxp = result[0]
    else:
        maxp = 0

    offset, limit = calculate_offset_limit(maxp, sentlim)

    ### get a sample
    phenomena = dd(list)
    c.execute(
        """SELECT a.profile, a.sid, COALESCE(a.kara, 0),
    COALESCE(a.made, max(b.wid) + 1), max(b.wid)
    FROM typind as a LEFT JOIN sent as b
    ON a.profile=b.profile and a.sid=b.sid
    WHERE a.typ = ?
    GROUP BY b.profile, b.sid
    ORDER BY max(b.wid)
    LIMIT ? OFFSET ?""",
        (cx, limit, offset),
    )
    for profile, sid, kara, made, maxwid in c:
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
        dbpath = os.path.join(current_directory, f"db/{grm}")
        # key the cache on mtime/size so a rebuilt db is re-read
        st = os.stat(dbpath)
        key = (grm, st.st_mtime, st.st_size)
        if key in _short_summary_cache:
            summ[grm] = _short_summary_cache[key]
            continue
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
            entry = dict(c.fetchall())
            try:
                entry["DOCTESTS"] = c.execute(
                    "SELECT count(*) FROM doctest"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                # database built before the doctest table existed
                entry["DOCTESTS"] = 0
        _short_summary_cache[key] = entry
        summ[grm] = entry
    return summ
