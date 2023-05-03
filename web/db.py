import sqlite3, os
from flask import current_app, g


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
    c.execute("""SELECT types.typ, parents, lname, status, freq, arity, head 
    FROM types left join typfreq on types.typ=typfreq.typ
    WHERE status in ('rule', 'lex-rule', 'inf-rule', 'root') order by
    status, types.typ""" )
    results = c.fetchall()
    return results

def get_ltypes(conn):
    c = conn.cursor()
    c.execute("""SELECT lex.typ, lname, count(lex.typ), freq, '' 
             FROM types LEFT JOIN lex ON types.typ = lex.typ
    LEFT JOIN typfreq ON lex.typ = typfreq.typ
    WHERE status ='lex-type' 
    GROUP BY lex.typ ORDER BY lex.typ""" )
    results = c.fetchall()


    
    return results


def get_type(conn, typ):
    
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
    c.execute("""SELECT lex.lexid, orth, COALESCE(freq,0) FROM lex 
             LEFT JOIN lexfreq ON lex.lexid = lexfreq.lexid
             WHERE typ=? ORDER BY freq DESC""", (typ,))
    lem = dict()
    for (lxid, orth, freq) in c:
        lem[lxid] = (orth, freq)
        
    return lem
