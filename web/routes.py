"""Route declaration."""
from flask import current_app as app
from flask import render_template

import toml
import pathlib
import sqlite3, os

from .db import get_db, get_md, get_rules, get_ltypes, \
    get_type


def get_db_connection(root, db):
    dbpath = os.path.join(root, db)
    conn = sqlite3.connect(dbpath)
    #conn.row_factory = sqlite3.Row
    return conn

current_directory = os.path.abspath(os.path.dirname(__file__))


# nav = [
#     {"name": "Home", 'page' : 'home'},
#     {"name": "Short CV", 'page':'cv'},
#     {"name": "Publications", 'page':'pubs'},
#     {"name": "Recipes", 'page':'recipes'},
#     ]
nav = {
    'index': {"name": "Overview",
              'desc': "An overview of the OMW project"},
    'omw1':  {"name": "OMW v1",
              'desc': "The original version linked by PWN"},
    'omw2':  {"name": "OMW v2",
              'desc': 'The new version linked by CILI'},
    'news':  {"name": "News",
              'desc': 'News and Updates'},
    'docs':  {"name": "Documentation",
              'desc': 'Links to some useful documentation'}
}

grm='db/ERG_(2020).db'
#grm='db/Portuguese_(2022-08-10).db'


@app.route("/<page>.html")
def show(page):
    """Show a page"""
    return render_template(
        f"{page}.html",
        page=page,
        nav=nav,
        title=nav[page]['name'],
        description=nav[page]['desc'],
    )


@app.route("/doc/<page>.html")
def show_doc(page):
    """Show a doc page"""
    try:
        with app.open_resource(f'etc/{page}.toml', mode='rt') as f:
            data = toml.loads(f.read())
    except:
        data = dict()
    try:
        with app.open_resource(f'etc/{page}.examples.toml', mode='rt') as f:
            examples = toml.loads(f.read())
    except:
         examples = dict()

      
    return render_template(
        f"doc/{page}.html",
        page=page,
        nav=nav,
        data = data,
        examples = examples,
    )


@app.route("/")
def home():
    """show the home page"""
    conn = get_db_connection(current_directory,
                             grm)
    c = conn.cursor()
    c.execute("SELECT val FROM meta WHERE att='GRAMMAR_NAME'")
    title = c.fetchone()
    page='index'
    return render_template(
        f"index.html",
        page=page,
        nav=nav,
        title=title,
        description=nav[page]['desc'],
    )


@app.route("/grammar.html")
def grammar():
    """show the grammar page"""
    conn = get_db(current_directory, grm)
    c = conn.cursor()
    md = get_md(conn)
    return render_template(
        f"grammar.html",
        nav=nav,
        title=md['GRAMMAR_NAME'],
        meta=md,
    )

@app.route("/rules.html")
def rules():
    """show the rules"""
    conn = get_db(current_directory, grm)
    md   = get_md(conn)
    data = get_rules(conn)

    return render_template(
        f"rules.html",
        meta=md,
        data=data
    )

@app.route("/ltypes.html")
def ltypes():
    """show the rules"""
    conn = get_db(current_directory, grm)

    md   = get_md(conn)
    data = get_ltypes(conn)

    return render_template(
        f"ltypes.html",
        meta=md,
        data=data
    )



@app.route("/type/<typ>")
def type(typ):
    """show the type"""
    conn = get_db(current_directory, grm)

    typeinfo=get_type(conn, typ)

    return render_template(
        f"typeinfo.html",
        nav=nav,
        typ=typ,
        info=typeinfo,
    )
