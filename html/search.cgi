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

con = sqlite3.connect(par['db'])
c = con.cursor()

lexinfo = ltdb.get_lexinfo(typ,c)

    
if (lemma):
    leminfo = ltdb.get_leminfo (lemma,c)
    if leminfo:
        print """
<div align ='center' id="contents">
<h1>Lexical Types matching "%s" (%s)</h1>
%d Type(s) found.
""" % (lemma, par['ver'], len(leminfo))
        print "<table>"
        print ("""<tr>
        <th>{}</th><th>{}</th><th>{}</th><th>{}</th><th>{}</th>
        </tr>""".format("Lexical Entry",
                        "Orthography",
                        "Lexical Type",
                        "Name", 
                        "Example (Lexicon, Corpus)"))
        for (typ,  orth, name,
             words, typefreq, tokenfreq, lexid) in leminfo:
            ## FIXME ':' -> '\t'
            if not name:
                name = '<br>'
            wrds = "<br>"
            if words:
                wrds = ", ".join(["<span title='%s (%s)'>%s</a>" % tuple(r.split('\t')) for 
                                  r in words.split('\n')])
            print("""<tr>
            <td><a href='showtype.cgi?typ={0}'>{0}</a></td>
            <td><a href='search.cgi?lemma={1}'>{1}</a></td>
            <td>{2}</td>
            <td>{3}</td>
            <td>{4} ({5}, {6})</td>
</tr>""".format(lexid, orth, ltdb.hlt(typ), name,
                 wrds, typefreq, tokenfreq))
        print "</table>"
    else:
        print "<p>No matches found for lemma %s in %s."  % (lemma, par['ver'])
elif(typ):
    typsum = ltdb.get_typsum (typ, c)
    if typsum:
        print """
<div id="contents">
<h1>Types matching "%s" (%s)</h1>
%d Type(s) found.
""" % (typ, par['ver'], len(typsum))
        print "<table>"
        print "<tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>" % ("Type", 
                                                                         "Name", 
                                                                         "Status", 
                                                                         "Freq.")
        for (typ, name, status, freq) in typsum:
            if not name:
                name='<br>'
            if not freq:
                freq=0
            print """<tr class='%s'><td>%s</td><td>%s</td>
 <td>%s</td><td align='right'>%s</td></tr>""" % (status, ltdb.hlt(typ), name, 
                                   status, freq)
        print "</table>"
    elif (lexinfo):
        lexid=typ
        print ("""
        <div id="contents"> """)
        print ("<table>")
        print ("<tr><th>{}</th><th>{}</th><th>{}</th></tr>".format("LexID", 
                                                                   "Type", 
                                                                   "Orthography"))
        print("<tr>")
        print("<td><a href='showtype.cgi?lexid={0}'>{0}</a></td>".format(lexid))
        print("<td><a href='showtype.cgi?typ={0}'>{0}</a></td>".format(lexinfo[0]))
        print("<td><a href='search.cgi?lemma={0}'>{0}</a></td>".format(lexinfo[1]))
        print ("</table>")
    else:
        print ("""
  <div align ='center' id="contents">
    <p>No matches found for type {} in {}.
  </div>""".format(typ, par['ver']))


print ltdb.footer()
