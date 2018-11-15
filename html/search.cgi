#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import cgi
import cgitb; cgitb.enable()  # for troubleshooting
import sqlite3, collections
import sys,codecs 
sys.stdout = codecs.getwriter('utf8')(sys.stdout)
from collections import defaultdict as dd
import ltdb

form = cgi.FieldStorage()
#synset = form.getfirst("synset", "")
lemma = form.getfirst("lemma", "")
lemma = lemma.strip().decode('utf-8')
typ = form.getfirst("typ", "")
typ = typ.strip().decode('utf-8')


par=ltdb.getpar('params')

print (ltdb.header())

print (ltdb.searchbar())

if (lemma):
    con = sqlite3.connect(par['db'])
    c = con.cursor()
    c.execute("""SELECT lex.typ,  types.lname, words, lfreq, cfreq, lex.lexid 
                 FROM ltypes LEFT JOIN lex 
                 ON ltypes.typ = lex.typ 
                 LEFT JOIN types ON lex.typ = types.typ
                 WHERE orth GLOB ?""", ('*{}*'.format(lemma),) )
    results = c.fetchall()
    if results:
        print """
<div align ='center' id="contents">
<h1>Lexical Types matching "%s" (%s)</h1>
%d Type(s) found.
""" % (lemma, par['ver'], len(results))
        print "<table>"
        print ("""<tr>
        <th>{}</th><th>{}</th><th>{}</th><th>{}</th>
        </tr>""".format("Lexical Entry",
                        "Lexical Type",
                        "Name", 
                        "Example (Lexicon, Corpus)"))
        for (typ,  name,
             words, typefreq, tokenfreq, lexid) in results:
            ## FIXME ':' -> '\t'
            if not name:
                name = '<br>'
            wrds = "<br>"
            if words:
                wrds = ", ".join(["<span title='%s (%s)'>%s</a>" % tuple(r.split('\t')) for 
                                  r in words.split('\n')])
            print("""<tr>
   <td><a href='showtype.cgi?typ={}'>{}</a></td>
   <td>{}</td>
   <td>{}</td>
   <td>{} ({}, {})</td>
</tr>""".format(lexid, lexid, ltdb.hlt(typ), name,
                 wrds, typefreq, tokenfreq))
        print "</table>"
    else:
        print "<p>No matches found for lemma %s in %s."  % (lemma, par['ver'])
elif(typ):
    con = sqlite3.connect(par['db'])
    c = con.cursor()
    c.execute("""SELECT types.typ,  lname, status, freq 
              FROM types LEFT JOIN typfreq ON types.typ=typfreq.typ
              WHERE types.typ LIKE ?""", ('%%%s%%' % typ,) )
    results = c.fetchall()
    if results:
        print """
<div id="contents">
<h1>Types matching "%s" (%s)</h1>
%d Type(s) found.
""" % (typ, par['ver'], len(results))
        print "<table>"
        print "<tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>" % ("Type", 
                                                                         "Name", 
                                                                         "Status", 
                                                                         "Freq.")
        for (typ, name, status, freq) in results:
            if not name:
                name='<br>'
            if not freq:
                freq=0
            print """<tr class='%s'><td>%s</td><td>%s</td>
 <td>%s</td><td align='right'>%s</td></tr>""" % (status, ltdb.hlt(typ), name, 
                                   status, freq)
        print "</table>"
    else:
        print "<p>No matches found for type %s in %s."  % (typ, par['ver'])


print ltdb.footer()
