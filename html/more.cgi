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
lextyp = form.getfirst("lextyp", "")
lextyp = lextyp.strip().decode('utf-8')
limit = int(form.getfirst("limit", 50))


par=ltdb.getpar('params')

print ltdb.header()

print ltdb.searchbar()
###
### Print out the type
###
print("<div id='contents'>")
if (typ):
    print(u"<h1>{}</h2>".format(typ))
    con = sqlite3.connect(par['db'])
    c = con.cursor() 
    ltdb.showsents(c, typ,  limit, 50)
elif(lextyp):
    print(u"<h1>{}</h2>".format(lextyp))
    con = sqlite3.connect(par['db'])
    c = con.cursor() 
    ltdb.showlexs(c, lextyp,  limit, 50) 
else:
    print("<p>More examples of what?" %(typ, 
                                              lextyp, 
                                              limit))
print("</div>")
print ltdb.footer()
