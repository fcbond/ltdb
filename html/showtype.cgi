#!/usr/bin/python
# -*- coding: utf-8 -*-
import cgi
import cgitb; cgitb.enable()  # for troubleshooting
import sqlite3, collections
import sys,codecs 
sys.stdout = codecs.getwriter('utf8')(sys.stdout)
from collections import defaultdict as dd
import ltdb

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
###
### Print out the type
###
if (typ):
    con = sqlite3.connect(par['db'])
    c = con.cursor() 
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
        description=None
        criteria=None
        reference=None
        todo=None
        definition=None

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
                ltdb.hlall(description),
                cr,
                reference))
    ###
    ### Corpus examples of lextype, type
    ###
    ltdb.showlexs(c, typ,  maxexe, 50) 
    ltdb.showsents(c, typ,  maxexe, 50)



    ### TDL and type info
    print("""<h2>Type Information</h2>""")
    if definition:
        print("""<pre class='code'>%s</pre>""" % ltdb.hlall(definition).replace(',\n',',<br>').replace('&\n','&amp;<br>').replace('\n',''))
    print("""<table><tr><th>Supertypes</th><th>Head Category</th>
<th>Valence</th><th>Content</th><th>Subtypes</th>
<th>Arity</th><th>head</th></tr>
<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>
</tr></table>""" % (ltdb.hlt(parents), 
                    ltdb.hlt(cat),  
                    ltdb.hlt(val),  
                    ltdb.hlt(cont),  
                    ltdb.hlt(children) or "<span class=match>LEAF</span>",
                    arity or "<br>", head or "<br>"))

print ltdb.footer()

