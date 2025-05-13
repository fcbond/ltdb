"""Route declaration."""
from flask import current_app as app
from flask import render_template, request, session

import toml
import pathlib
import sqlite3, os


from .db import get_db, get_md, \
    get_summary, get_tb_summary, \
    get_rules, get_ltypes, \
    get_type, get_lxids, get_wrds_by_lexids, \
    get_phenomena_by_lexids, get_sents, get_gold, \
    get_phenomena_by_cx, get_lxid

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
    grammars.sort()
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
    summ = get_summary(conn)
    tsumm = get_tb_summary(conn)
    return render_template(
        f"grammar.html",
        title=md['GRAMMAR_NAME'],
        meta=md,
        grm=grm,
        summ=summ,
        tsumm=tsumm,
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
    grm = session['grm']
    conn = get_db(current_directory, grm)

    typeinfo=get_type(conn, query)
   
    desc = rst2html(query, typeinfo['docstring'])


    status = typeinfo['status']
    
    if status == 'lex-type':
        lexids = get_lxids(conn, query)

        words = get_wrds_by_lexids(conn, list(lexids.keys()))

        phenomena = get_phenomena_by_lexids(conn, list(lexids.keys()))

        sents = get_sents(conn, list(phenomena.keys()))

        gold = get_gold(conn, list(phenomena.keys()))
    elif  status == 'lex-entry':
        lexids = get_lxid(conn, query)

        words = get_wrds_by_lexids(conn, list(lexids.keys()))

        phenomena = get_phenomena_by_lexids(conn, list(lexids.keys()))

        sents = get_sents(conn, list(phenomena.keys()))

        gold = get_gold(conn, list(phenomena.keys()))

        lexids = []
        words = []

    elif  status in ('root', 'rule', 'lex-rule'):
        phenomena = get_phenomena_by_cx(conn, query)

        sents = get_sents(conn, list(phenomena.keys()))

        gold = get_gold(conn, list(phenomena.keys()))

        lexids = []
        words = []
    else:
        lexids = []
        words = []
        phenomena = []
        sents= []
        gold = []

    results = {'derivj':'Tree', 
               'mrs':'MRS',
               'dmrsj':'DMRS',
               'mrsj':'[MRS]',
               }
    
    return render_template(
        f"lextype.html",
        query=query,
        info=typeinfo,
        grm=grm,
        desc=desc,
        lexids=lexids,
        words=words,
        phenomena=phenomena,
        sents=sents,
        gold=gold,
        results=results
    )

@app.route("/lextype/<query>")
def ltype(query):
    """show the lexical type"""
    grm = session['grm']
    conn = get_db(current_directory, grm)

    typeinfo=get_type(conn, query)

    desc = rst2html(query, typeinfo['docstring'])

    lexids = get_lxids(conn, query)

    words = get_wrds_by_lexids(conn, list(lexids.keys()))

    phenomena = get_phenomena_by_lexids(conn, list(lexids.keys()))

    sents = get_sents(conn, list(phenomena.keys()))

    gold = get_gold(conn, list(phenomena.keys()))

    results = {'derivj':'Tree', 
               'mrs':'MRS',
               'dmrsj':'DMRS',
               'mrsj':'[MRS]',
    }

    
    return render_template("lextype.html",
               query=query,
               info=typeinfo,
               grm=grm,
               desc=desc,
               lexids=lexids,
               words=words,
               phenomena=phenomena,
               sents=sents,
               gold=gold,
               results=results
    )



@app.route('/search', methods=['POST'])
def submit_fsearch():
    grm = session['grm']
    conn = get_db(current_directory, grm)

    
    searched = request.form['search']

    results= dict()
    
    results['rules']  = get_rules(conn, query=searched)
    results['ltypes'] = get_ltypes(conn, query=searched)

    path = dict()
    
    path['rules'] = 'type'
    path['ltypes'] = 'ltype'
    path['lemmas'] = 'lemma'
    path['predicates'] = 'pred'
    
    return render_template('searched.html',
                           grm=grm,
                           searched=searched,
                           results=results,
                           path=path)
