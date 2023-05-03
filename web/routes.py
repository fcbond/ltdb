"""Route declaration."""
from flask import current_app as app
from flask import render_template, request, session

import toml
import pathlib
import sqlite3, os

from .db import get_db, get_md, get_rules, get_ltypes, \
    get_type, get_lxids

from .ltdb import rst2html

def get_db_connection(root, db):
    dbpath = os.path.join(root, db)
    conn = sqlite3.connect(dbpath)
    #conn.row_factory = sqlite3.Row
    return conn

current_directory = os.path.abspath(os.path.dirname(__file__))



#session['grm']=None
#'db/ERG_(2020).db'
#grm='db/Portuguese_(2022-08-10).db'




@app.route("/", methods=["GET", "POST"])
def home():
    """show the home page"""
    grammars = []
    # Iterate directory
    for file in os.listdir(os.path.join(current_directory, 'db')):
    # check only text files
        if file.endswith('.db'):
            grammars.append(file)

    if 'grm' in request.form:
        session['grm'] = request.form['grm']
    page='index'
    return render_template(
        f"index.html",
        page=page,
        title='LTDB',
        grammars=grammars,
        grm =  session.get('grm', None)
    )


@app.route("/grammar.html")
def grammar():
    """show the grammar page"""
    grm = session['grm']
    conn = get_db(current_directory, grm)
    md = get_md(conn)
    return render_template(
        f"grammar.html",
        title=md['GRAMMAR_NAME'],
        meta=md,
        grm=grm,
    )

@app.route("/rules.html")
def rules():
    """show the rules"""
    grm = session['grm']
    conn = get_db(current_directory, grm)
    md   = get_md(conn)
    data = get_rules(conn)

    return render_template(
        f"rules.html",
        meta=md,
        data=data,
        grm=grm
    )

@app.route("/ltypes.html")
def ltypes():
    """show the rules"""
    grm = session['grm']
    conn = get_db(current_directory, grm)

    md   = get_md(conn)
    data = get_ltypes(conn)

    return render_template(
        f"ltypes.html",
        meta=md,
        data=data,
        grm=grm,
    )



@app.route("/type/<typ>")
def type(typ):
    """show the type"""
    grm = session['grm']
    conn = get_db(current_directory, grm)

    typeinfo=get_type(conn, typ)

    desc = rst2html(typ, typeinfo['docstring'])

   
    return render_template(
        f"typeinfo.html",
        typ=typ,
        info=typeinfo,
        grm=grm,
        desc=desc,
    )

@app.route("/lextype/<typ>")
def ltype(typ):
    """show the lexical type"""
    grm = session['grm']
    conn = get_db(current_directory, grm)

    typeinfo=get_type(conn, typ)

    desc = rst2html(typ, typeinfo['docstring'])

    words = get_lxids(conn, typ)
    
    return render_template(
        f"ltype.html",
        typ=typ,
        info=typeinfo,
        grm=grm,
        desc=desc,
        words=words,
    )
