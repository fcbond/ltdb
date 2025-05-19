import sqlite3, os
from flask import current_app, g
from collections import defaultdict as dd

### limit for most queries
### not much point showing more examples than this
###
lim = 512
sentlim = 8


def get_db(root, db):
    if 'db' not in g:
        g.db = sqlite3.connect(
            os.path.join(root, f'db/{db}')
            #detect_types=sqlite3.PARSE_DECLTYPES
        )
#        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()


############################################################


def holders(lst):
    """
    return the parameter placeholders for a query 
    """
    return ','.join(['?']*len(lst))

def get_md(conn):
    c = conn.cursor()
    c.execute("SELECT att, val FROM meta")
    print(c)
    md = dict()
    for (att, val) in c:
        md[att]=val
    return md


def get_rules(conn):
    c = conn.cursor()
        
    c.execute(f"""SELECT types.typ, parents, lname, status, COALESCE(freq,0), arity, head 
    FROM types left join typfreq on types.typ=typfreq.typ
    WHERE status in ('rule', 'lex-rule', 'inf-rule', 'root') 
    ORDER BY status, types.typ""")
        
    results = c.fetchall()
    return results

def get_ltypes(conn):
    c = conn.cursor()

    c.execute(f"""SELECT lex.typ, lname, count(lex.typ), COALESCE(freq,0), '' 
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
    c.execute(f"""SELECT orth, typ, 'freq', 'words' 
    FROM lex
    WHERE orth glob ?""", [query])
    if (returned := c.fetchall()):
        results['lemmas'] =  returned

    ## types
    c.execute(f"""SELECT types.typ, parents, status, freq,
    lname 
    FROM types left join typfreq on types.typ=typfreq.typ
    WHERE types.typ glob  ?
    ORDER BY status, types.typ""", [query])
    
    for (typ, parents, status, freq, lname) in c:
        results[status].append((typ, parents, freq, lname))

    return results


def get_type(conn, typ):
    """
    ToDo: also get the status of the children so we can link them better.
    """
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""SELECT  parents,  children,  cat,  val,
    cont, definition,  status, arity, head, 
    lname, tdl.docstring,
    criteria, reference, todo,
    src, line, kind, tdl 
    FROM types LEFT JOIN tdl 
    ON types.typ = tdl.typ
    WHERE types.typ=? limit 1""", (typ,))
    row = c.fetchone()
    if row:
        return dict(zip(row.keys(), row))  
    else:
        return dict()

def get_lxids(conn, typ):
    """
    return lexical items that have this lexical type
    or {} if the type is not a lexical type
    """
    c = conn.cursor()
    c.execute(f"""SELECT lex.lexid, orth, COALESCE(freq,0) FROM lex 
             LEFT JOIN lexfreq ON lex.lexid = lexfreq.lexid
             WHERE typ=? 
    ORDER BY freq DESC
    LIMIT {lim / 2}""", (typ,))
    lem = dict()
    for (lxid, orth, freq) in c:
        lem[lxid] = (orth, freq)
        
    return lem

def get_lxid(conn, typ):
    """
    return lexical item 
    """
    c = conn.cursor()
    c.execute(f"""SELECT lexid, word, COALESCE(freq,0) FROM lexfreq
             WHERE lexid=? 
    LIMIT {lim / 2}""", (typ,))
    lem = dict()
    for (lxid, orth, freq) in c:
        lem[lxid] = (orth, freq)
        
    return lem


def get_wrds_by_ltypes(conn, wlimit=5):
    """
    return a dictionary with words and frequencies 
    for all the lexical types
    """
    words=dd(lambda: dd(int))
    c = conn.cursor()

    c.execute(f""" 
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
                ROW_NUMBER() OVER (PARTITION BY lex.typ ORDER BY lexfreq.freq DESC) AS rank
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
    """, (wlimit, wlimit))
    for (ltype, word, freq) in c:
        words[ltype][word] = freq
    return words
    
    
def get_wrds_by_lexids(conn, lexids):
    """
    return a dictionary with words and frequencies for each lexid
    words[lexid][word] = freq
    """
    c = conn.cursor()
    words=dd(lambda: dd(int))
    c.execute(f"""
    SELECT lexid, word, count(word) FROM sent
    WHERE (lexid IN ({holders(lexids)}))
    GROUP BY lexid, word 
    ORDER BY lexid
    LIMIT {lim}""", lexids)
    for (lexid, word, freq) in c:
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
        offset, limit  = 0, N
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
    c.execute(f"""SELECT COUNT(*) 
    FROM (
    SELECT DISTINCT profile, sid 
    FROM sent 
    WHERE lexid IN ({holders(lexids)})
    )""", (lexids))
    result = c.fetchone()
    if result:
        maxp = result[0]
    else:
        maxp = 0

    offset, limit = calculate_offset_limit(maxp, sentlim)

    ### get a sample
    phenomena=dd(list)
    c.execute(f"""SELECT a.profile, a.sid, a.wid , max(b.wid)
    FROM sent as a LEFT JOIN sent as b
    ON a.profile=b.profile and a.sid=b.sid
    WHERE a.lexid IN ({holders(lexids)})
    GROUP BY b.profile, b.sid
    ORDER BY max(b.wid) 
    LIMIT ? OFFSET ?""", (lexids + [limit, offset]))
    for (profile, sid, wid, max) in c:
        phenomena[profile, sid].append((wid, wid+1))
    return maxp, phenomena

def get_phenomena_by_cx(conn, cx):
    """ 
    return a dict of profile, sid, with the cx in question marked
    use for rules, roots, dlr, iflr, 

    phenom[profile, sid = [(from, to), ....]
    try to pick short sentences
    """
    c = conn.cursor()
        ### get the total number
    c = conn.cursor()
    c.execute(f"""SELECT COUNT(*) 
    FROM (
    SELECT DISTINCT profile, sid 
    FROM typind 
    WHERE typ = ?
    )""", (cx,))
    result = c.fetchone()
    if result:
        maxp = result[0]
    else:
        maxp = 0

    offset, limit = calculate_offset_limit(maxp, sentlim)

    ### get a sample
    phenomena=dd(list)
    c.execute(f"""SELECT a.profile, a.sid, COALESCE(a.kara, -1),
    COALESCE(a.made, -1), max(b.wid)
    FROM typind as a LEFT JOIN sent as b
    ON a.profile=b.profile and a.sid=b.sid
    WHERE a.typ = ?
    GROUP BY b.profile, b.sid
    ORDER BY max(b.wid)
    LIMIT ?""", (cx, sentlim))
    print("CX", cx)
    
    for (profile, sid, kara, made, max) in c:
        phenomena[profile, sid].append((kara, made))
        
    return maxp, phenomena



def get_sents(conn, psids):
    """
    given a list of (profile, sid)
    return enough information to display it
    sent[(p, s)][wid] = word
    """
    c = conn.cursor()
    sents = dd(dict)
    for profile, sid in psids:
        c.execute("""SELECT profile, sid, wid, word, lexid FROM SENT 
        WHERE profile = ? AND sid = ? order by profile, sid, wid""",
                  (profile, sid))
        for (prof, sid, wid, word, lexid) in c:
            sents[prof, sid][wid] = word
    return sents

def get_gold(conn, psids):
    """
    given a list of (profile, sid)
    return the mrs, dmrs_json, mrs_json and deriv_json
    sent[(p, s)]['mrs'] = mrs
    ...
    """
    c = conn.cursor()
    data = dd(dict)
    for profile, sid in psids:
        c.execute("""SELECT profile, sid, deriv_json, mrs, mrs_json, dmrs_json, sent
        FROM GOLD 
        WHERE profile = ? AND sid = ?""",
                  (profile, sid))
        for (prof, sid, deriv_json, mrs, mrs_json, dmrs_json, sent) in c:
            data[prof, sid]['mrs'] = mrs
            data[prof, sid]['mrsj'] = mrs_json
            data[prof, sid]['dmrsj'] = dmrs_json
            data[prof, sid]['derivj'] = deriv_json
            data[prof, sid]['item'] = sent
    return data

def get_summary(conn):
    """
    Return a summary of the grammar"
    """
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

    return summary

def get_tb_summary(conn):
    """
    Return a summary of the treebank"
    """
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

    return summary


