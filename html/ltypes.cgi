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
# typ = form.getfirst("typ", "")
# typ = typ.strip().decode('utf-8')


par=ltdb.getpar('params')

print ltdb.header()

print ltdb.searchbar()

con = sqlite3.connect(par['db'])
c = con.cursor()
c.execute("""SELECT types.typ, lname, words, lfreq, cfreq 
             FROM types LEFT JOIN ltypes ON types.typ=ltypes.typ  
             WHERE status ='ltype' ORDER BY types.typ""")
results = c.fetchall()
if results:
    print """
<div align ='center' id="contents">
<h1>List of all %d Lexical Types (%s)</h1>
""" % (len(results), par['ver'])
    
    print "<table>"
    print """<tr><th>%s</th><th>%s</th>
<th colspan='2'>%s</th><th>%s</th></tr>""" % ("Lexical Type", 
                                              "Name", 
                                              "&nbsp;&nbsp;&nbsp;&nbsp;Frequency<br>Lexicon, Corpus",
                                              "Examples")
    for (typ,  name, words, lfreq, cfreq) in results:
        ### FIXME --- set to zero in the DB
        if not lfreq: 
            lfreq=0
        if not cfreq:
            cfreq=0
        if not name:
            name = '<br>'
        wrds = "<br>"
        if words:
            wrds = ", ".join(["<span title='%s (%s)'>%s</a>" % tuple(r.split('\t')) for 
                             r in words.split('\n')])
        print u"""<tr><td>{}</td>
 <td>{}</td><td align='right'>{:,}</td><td align='right'>{:,}</td>
 <td>{}</td></tr>""".format(ltdb.hlt(typ), 
                        name,
                        lfreq, cfreq, wrds)
    print "</table>"


print ltdb.footer()

