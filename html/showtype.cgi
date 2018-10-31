#!/usr/bin/python
# -*- coding: utf-8 -*-
import cgi
import cgitb; cgitb.enable()  # for troubleshooting
import sqlite3, collections
import sys,codecs 
sys.stdout = codecs.getwriter('utf8')(sys.stdout)
from collections import defaultdict as dd
import ltdb
import docutils.core

form = cgi.FieldStorage()
#synset = form.getfirst("synset", "")
# lemma = form.getfirst("lemma", "")
# lemma = lemma.strip().decode('utf-8')
typ = form.getfirst("typ", "")
typ = typ.strip().decode('utf-8')
maxexe = 3

par=ltdb.getpar('params')

print ltdb.header()

print ltdb.searchbar()

### labels for branching: arity, head
headedness = {(1,0):('unary: headed'),
              (1,None):('unary: non-headed'),
              (2,0):('binary: left-headed'),
              (2,1):('binary: right-headed'),
              (2,None):('binary: non-headed'),
              (None,None):(' ')}
 
###
### Print out the type
###
if typ == '':
    print "<br><br><p style='font-size:large;'>Please give me a type (or rule or lexeme)"
else:
    con = sqlite3.connect(par['db'])
    c = con.cursor()
    ### check if it is a lexeme:
    lexid = ''
    c.execute("""SELECT typ, orth from lex 
                 WHERE lexid =? """, (typ,))
    lexinfo=c.fetchone()
    if lexinfo:
        lexid = typ
        (typ, orth) = lexinfo
    c.execute("""SELECT  parents,  children,  cat,  val,
	 	         cont, definition,  status, arity, head, 
                 lname, description,
                 criteria, reference, todo  
                 FROM types WHERE typ=? limit 1""", (typ,))
    typinfo=c.fetchone()
    if typinfo:
        (parents,  children,  cat,  val,  
         cont, definition,  status, arity, head,
         name, description, criteria, reference, todo ) = typinfo
    else:
        status='Unknown'
        name=None
        description=[]
        parents = []
        criteria=None
        reference=None
        todo=None
        definition=None
        cat = ''
        val=''
        cont=''
        children=''
        arity=None
        head=None
    c.execute("""SELECT  src, line, tdl, docstring 
                  FROM tdl WHERE typ=?""", (typ,))
    tdlinfo = c.fetchall()

        
        
    dscp = ""
    if description:
        for l in description:
            if l.startswith('+') or l.startswith('-'): 
                dscp += l
            else:
                dscp += l
                # dscp += ltdb.hlall(l)
            
        
    # LETS CONVERT DESCRIPTION FROM RTS TO HTML
    description_html = docutils.core.publish_parts(dscp,writer_name='html',
                                     settings_overrides= {'table_style':'colwidths-auto',
                                                          'initial_header_level':'3'})['body']

    if lexid:
        print ("""
<div id="contents">
        <h1>%s "%s" is-a %s (%s)</h1>""" % (lexid, orth,
                                            typ, status))
    else:
        print ("""
        <div id="contents">
        <h1>%s (%s)</h1>""" % (typ, status)) ## FIXME show headedness
    if name or description or criteria or reference or todo:
        if criteria:
            cr="<p><table>"
            for crit in criteria.split('\n'):
                cr += "<tr><th>%s</th><td>%s</td></tr>" % tuple(crit.split('\t')) 
            cr +="</table>"
        else:
            cr= ''
        print("""<h2>Linguistic Documentation</h2><p>%s%s<p>%s""" % (
                # ltdb.hlall(description),    #ADD LINKS LATER
                description_html,
                cr,
                reference))
    ###
    ### Corpus examples of lextype, type
    ###
    ltdb.showlexs(c, typ,  maxexe, 50) 
    ltdb.showsents(c, typ,  maxexe, 50)



    ### TDL and type info
    if status != 'Unknown':
        print("""<h2>Type Information</h2>""")
        print("""<div class='tdl'>""")
        if tdlinfo:
            for src, lineno, tdl, docstring in tdlinfo:
                print("""<pre class='code'>%s</pre>""" % ltdb.hlall(tdl))
                print("(%s: %s)" % (src, lineno))
                if docstring:
                    print("""<h4>docstring</h4>""")
                    print(docstring)
        print("</div>")
        print("""<table><tr><th>Supertypes</th><th>Head Category</th>
        <th>Valence</th><th>Content</th><th>Subtypes</th>
        <th>Headedness</th></tr>
        <tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>
        </tr></table>""" % (ltdb.hlt(parents), 
                            ltdb.hlt(cat),  
                            ltdb.hlt(val),  
                            ltdb.hlt(cont),  
                            ltdb.hlt(children) or "<span class=match>LEAF</span>",
                            headedness[(arity,head)]))
        if definition:
            print("""<h3>TDL from LKB comment</h3>""")
            print("""<pre class='code'>%s</pre>""" % ltdb.hlall(definition))

print ltdb.footer()

