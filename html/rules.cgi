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
c.execute("""SELECT types.typ, parents, lname, status, freq 
             FROM types left join typfreq on types.typ=typfreq.typ
             WHERE status in ('rule', 'lrule', 'irule', 'root') order by
             types.typ""" )
results = c.fetchall()
if results:
    print u"""
<div align ='center' id="contents">
<h1>List of all {:,} Rules ({})</h1>
""".format(len(results), par['ver'])
    
    print "<table>"
    print "<tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>" % ("Rule", 
                                                                                "Type",
                                                                                "Name", 
                                                                                 "Kind",
                                                                                "Frequency")
    for (typ,  parent, name, status, freq) in results:
        if not name:
            name = '<br>'
        if not freq:
            freq=0
        print u"""<tr class='{}'><td>{}</td><td>{}</td>
<td>{}</td><td>{}</td><td align='right'>{:,}</td></tr>""".format(status,
                                                           ltdb.hlt(typ),
                                                           ltdb.hlt(parent),
                                                           name, status, 
                                                           freq)
    print "</table>"


print ltdb.footer()

