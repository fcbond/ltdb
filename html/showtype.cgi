#!/usr/bin/python
# -*- coding: utf-8 -*-
###
### Show the type or lexeme
###


import cgi
import cgitb; cgitb.enable()  # for troubleshooting
import sqlite3
import docutils.core
import ltdb


form = cgi.FieldStorage()
#synset = form.getfirst("synset", "")
# lemma = form.getfirst("lemma", "")
# lemma = lemma.strip().decode('utf-8')
typ = form.getfirst("typ", "")
typ = typ.strip()
lexid = form.getfirst("lexid", "")
lexid = lexid.strip()
maxexe = 3

par = ltdb.getpar('params')

print(ltdb.header())

print(ltdb.searchbar())



def get_typinfo (typ, c):
    """Information about a type, instance or class"""
    c.execute("""SELECT  parents,  children,  cat,  val,
	 	         cont, definition,  status, arity, head, 
                 lname, description,
                 criteria, reference, todo  
                 FROM types WHERE typ=? limit 1""", (typ,))
    row = c.fetchone()
    if row:
       return row
    else:
        return ()



def showtype (typinfo, tdlinfo):
    """print the type summary"""
    (parents,  children,  cat,  val, cont, definition,  status, arity, head, name, description, criteria, reference, todo) = typinfo
    print("""<h2>Type Information</h2>""")
    print("""<div class='tdl'>""")
    if tdlinfo:
        print("""<h3>TDL from docstrings with pydelphin</h3>""")
        for src, lineno, tdl, docstring in tdlinfo:
            print("""<pre class='code'>%s</pre>""" % ltdb.hlall(tdl))
            print("(%s: %s)" % (src, lineno))
    print("</div>")
    print("""<table><tr><th>Supertypes</th><th>Head Category</th>
    <th>Valence</th><th>Content</th><th>Subtypes</th>
    <th>Headedness</th></tr>
    <tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s (%s)</td>
    </tr></table>""" % (ltdb.hlt(parents), 
                        ltdb.hlt(cat),  
                        ltdb.hlt(val),  
                        ltdb.hlt(cont),  
                        ltdb.hlt(children) or "<span class=match>LEAF</span>",
                        ltdb.headedness[(arity,head)][0],
                        ltdb.headedness[(arity,head)][1]))
    if definition:
        print("""<h3>TDL from LKB comment</h3>""")
        print("""<pre class='code'>%s</pre>""" % ltdb.hlall(definition))    ### TDL and type info

def show_description(typ, description, tdlinfo):
    """print out the linguistic description in the doscstring
       use the value from the LKB if possible, if not then from pydelphin"""
    if description:
        print("""<h2>Linguistic Documentation</h2>
        {}""".format(docutils.core.publish_parts("\n"+ description +"\n",
                                                 writer_name='html',
                                                 settings_overrides= {'table_style':'colwidths-auto',
                                                                      'initial_header_level':'3'})['body']))
    else:
        for  src, line, tdl, docstring in  tdlinfo:
            if docstring:
                description, examples, names=  ltdb.munge_desc(typ,docstring)
                print("""<h2>Linguistic Documentation (TDL)</h2>
                {}""".format(docutils.core.publish_parts("\n"+ description +"\n",
                                                         writer_name='html',
                                                         settings_overrides= {'table_style':'colwidths-auto',
                                                                              'initial_header_level':'3'})['body']))

                
###
### Print out the type
###
con = sqlite3.connect(par['db'])
c = con.cursor()
if (lexid):
    ## Show the lexeme
    lexinfo = ltdb.get_lexinfo(lexid,c)
    if not lexinfo:
        print("<p>Unknown lexical identifier: {}".format(lexid))
    else:
        (typ, orth) = lexinfo
        description = ''
        tdlinfo = ltdb.get_tdlinfo(lexid, c)
        ### Header
        print("""<div id="contents">
        <h1>{0} (<a href='showtype.cgi?typ={1}'>{1}</a>)</h1>""".format(lexid, typ))
       
        ### Show docstring 
        show_description(typ, description, tdlinfo)
        ### Corpus examples of lextype, type
        ltdb.showlexs(c, typ, lexid, maxexe, 50) 
        ltdb.showsents(c, typ, lexid, maxexe, 50)

        ### TDL and type info
        #showtype(typinfo, tdlinfo)
        if tdlinfo:
            print("""<h3>TDL from docstrings with pydelphin</h3>""")
            for src, lineno, tdl, docstring in tdlinfo:
                print("""<pre class='code'>%s</pre>""" % ltdb.hlall(tdl))
                print("(%s: %s)" % (src, lineno))
        
elif (typ):
    typinfo = get_typinfo(typ, c)
    if not typinfo:
        print("<p>Unknown type: {}".format(typ))
    else:
        (parents,  children,  cat,  val, cont, definition,  status, arity, head, name, description, criteria, reference, todo) = typinfo

        tdlinfo = ltdb.get_tdlinfo(typ, c)
        
        ### Header
        print("""<div id="contents">
        <h1>%s (%s)</h1>""" % (typ, status)) ## FIXME show headedness

        ### Show docstring 
        show_description(typ, description, tdlinfo)
        ### Corpus examples of lextype, type
        ltdb.showlexs(c, typ, lexid, maxexe, 50) 
        ltdb.showsents(c, typ, lexid, maxexe, 50)

        ### TDL and type info
        showtype(typinfo, tdlinfo)
    
else:
    ## no type or lexid given
    print("<br><br><p style='font-size:large;'>Please give me a type (or rule or lexeme)")
    

print(ltdb.footer(par['ver']))

