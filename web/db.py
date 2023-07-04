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


def params(lst):
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
    c.execute("""SELECT types.typ, parents, lname, status, COALESCE(freq,0), arity, head 
    FROM types left join typfreq on types.typ=typfreq.typ
    WHERE status in ('rule', 'lex-rule', 'inf-rule', 'root') order by
    status, types.typ""" )
    results = c.fetchall()
    return results

def get_ltypes(conn):
    c = conn.cursor()
    c.execute("""SELECT lex.typ, lname, count(lex.typ), COALESCE(freq,0), '' 
             FROM types LEFT JOIN lex ON types.typ = lex.typ
    LEFT JOIN typfreq ON lex.typ = typfreq.typ
    WHERE status ='lex-type' 
    GROUP BY lex.typ ORDER BY lex.typ""" )
    results = c.fetchall()


    
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


def get_wrds_by_lexids(conn, lexids):
    """
    return a dictionary with words frequencies for each lexid
    words[lexid][word] = freq
    """
    c = conn.cursor()
    words=dd(lambda: dd(int))
    c.execute(f"""
    SELECT lexid, word, count(word) FROM sent
    WHERE (lexid IN ({params(lexids)}))
    GROUP BY lexid, word 
    ORDER BY lexid
    LIMIT {lim}""", lexids)
    for (lexid, word, freq) in c:
        words[lexid][word] = freq
    return words
    
def get_phenomena_by_lexids(conn, lexids):
    """ 
    return a dict of profile, sid, with the lexid in question marked
    phenom[profile, sid = [(from, to), ....]
    ToDo try to pick short sentences
    """
    c = conn.cursor()
    phenomena=dd(list)
    c.execute(f"""SELECT a.profile, a.sid, a.wid , max(b.wid)
    FROM sent as a LEFT JOIN sent as b
    ON a.profile=b.profile and a.sid=b.sid
    WHERE a.lexid IN ({params(lexids)})
    GROUP BY b.profile, b.sid
    ORDER BY max(b.wid) 
    LIMIT ?""", (lexids + [sentlim]))
    for (profile, sid, wid, max) in c:
        phenomena[profile, sid].append((wid, wid+1))
    return phenomena

def get_phenomena_by_cx(conn, cx):
    """ 
    return a dict of profile, sid, with the cx in question marked
    use for rules, roots, dlr, iflr, 

    phenom[profile, sid = [(from, to), ....]
    try to pick short sentences
    """
    c = conn.cursor()
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
        
    return phenomena



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

