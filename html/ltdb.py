### --*-- coding: utf-8 --*--
### shared code for the ltdb
###
from __future__ import unicode_literals
from __future__ import print_function


import sqlite3, collections
import cgi, re, urllib, sys
from collections import defaultdict as dd
import json

def getpar (params):
    par=dict()
    try:
        f = open(params)
        for l in f:
            (ft,vl)=l.strip().split('=')
            par[ft]=vl
    except:
        pass
    return par

par=getpar('params')

def hlt (typs):
    "hyperlink a list of space seperated types"
    l = unicode()
    if typs:
        for t in typs.split():
            l += "<a href='%s/showtype.cgi?typ=%s'>%s</a> " % (par['cgidir'], 
                                                           urllib.quote(t, ''),
                                                           t)
        return l
    else:
        return '<br>'



retyp=re.compile(r"(?<![#])\b([-A-Za-z_+*0-9]+)\b")

def hltyp(match):
    types=set()
    con = sqlite3.connect(par['db'])
    c = con.cursor()
    c.execute("SELECT typ FROM types")
    for typ in c:
        types.add(typ[0])
    #print types
    t = unicode(match.group(0))
    #print "<br>%s %s\n" % (t, t in types)
    if t in types and not t.startswith('#'):
        return "<a href='{}/showtype.cgi?typ={}'>{}</a>".format(par['cgidir'], 
                                                                urllib.quote(t,''),
                                                                t)
    else:
        return t


def hlall (typs):
    "hyperlink all types in a description or documentation"
    if typs:
        typs = cgi.escape(typs)
        ### Definition from http://moin.delph-in.net/TdlRfc
        typs=re.sub(r'(#[\w_+*?-]+)', "<span class='coref'>\\1</span>", typs)
        return retyp.sub(hltyp, typs)
    else:
        return '<br>'



###
### Show example sentences:
### * take a dict with sets of (tfrom, tto), show all sentences
### sids = dd(set)
def showsents (c, typ, lexid, limit, biglimit):
    if lexid:
        c.execute("SELECT count(sid) FROM sent WHERE lexid=?", (lexid,))
        results = c.fetchone()
    else:
        c.execute("SELECT freq FROM typfreq WHERE typ=?", (typ,))
        results = c.fetchone()
    if results and results[0] > 0:
        total = results[0]
        sids = dd(set)
        if lexid:
            c.execute("""SELECT sid, wid FROM sent 
                         WHERE lexid=? ORDER BY sid LIMIT ?""", (lexid, limit))
            for (sid, wid) in c:
                sids[sid].add((wid, wid+1))
        else:
            c.execute("""SELECT sid, kara, made FROM typind 
                         WHERE typ=? ORDER BY sid LIMIT ?""", (typ, limit))
            for (sid, kara, made) in c:
                sids[sid].add((kara, made))
        if limit < total and biglimit > limit:
            limtext= "({:,} out of {:,}: <a href='more.cgi?typ={}&lexid={}&limit={}'>more</a>)".format(limit, total,
                                                                                                       urllib.quote(typ,''),
                                                                                                       lexid,
                                                                                                       biglimit)
        elif limit < total:
            limtext= "({:,} out of {:,})".format(limit, total)
        else:
            limtext ='({:,})'.format(total)
        print("""<h2>Corpus Examples %s</h2>""" % limtext)
        c.execute("""SELECT profile, sid, wid, word, lexid FROM SENT 
                        WHERE sid in (%s) order by sid, wid""" % \
                          ','.join('?'*len(sids)), 
                      sids.keys())
        sents = dd(dict)
        profname=dict()
        for (prof, sid, wid, word, lexid) in c:
            sents[sid][wid] = (word, lexid)
            profname[sid]=prof

            
        print("""<ul style="list-style:none;">""")
        for sid in sorted(sids):


            # fetch json for deriv_tree, mrs and dmrs
            c.execute("""SELECT mrs, mrs_json, dmrs_json, deriv_json, sent, comment FROM gold 
                        WHERE sid =  ? """, [sid])
            for (mrs, mrs_json, dmrs_json, deriv_json, sent, comment) in c:
                mrs = mrs
                mrs_json = mrs_json
                dmrs_json = dmrs_json
                deriv_json = deriv_json
                sent=sent
                #comment unused

            for (kara, made) in sorted(sids[sid]):
                print('<li>{}<sub>{}-{}</sub> &nbsp;&nbsp; '.format(sid,kara,made))
                for wid in sents[sid]:
                    if wid >= kara and wid < made:
                        print ("<span class='match'>%s</span>" % \
                                   sents[sid][wid][0])
                    else:
                            print (sents[sid][wid][0])
                print(" (%s)" % (profname[sid]))

            ##############################################################
            # PRINT THE VISUALIZATIONS (only once per sentence)
            ##############################################################
            

            # <b>Show/Hide:</b>
            print("""<span> &nbsp;&nbsp;&nbsp;&nbsp;
            <button id="toggleMRS{0}">MRS</button>
            <button id="toggleTree{0}">Tree</button>
            <button id="toggleDMRS{0}">DMRS</button>
            <button id="toggleTextMRS{0}">Text_MRS</button>
            </span>
            </li>""".format(sid))


            
            print("""
            <script>
            $(document).ready(function(){{
                $("#toggleMRS{0}").click(function(){{
                    $("#mrs{0}").toggle();
                }});
                    //$("#mrs{0}").toggle();
            }});
            </script>
            """.format(sid))

            print("""
            <script>
            $(document).ready(function(){{
                $("#toggleTree{0}").click(function(){{
                    $("#viztree{0}").toggle();
                }});
                    //$("#viztree{0}").toggle();
            }});
            </script>
            """.format(sid))


            print("""
            <script>
            $(document).ready(function(){{
                $("#toggleDMRS{0}").click(function(){{
                    $("#dmrs{0}").toggle();
                }});
                    //$("#dmrs{0}").toggle();
            }});
            </script>
            """.format(sid))

            
            print("""
            <script>
            $(document).ready(function(){{
                $("#toggleTextMRS{0}").click(function(){{
                    $("#textmrs{0}").toggle();
                }});
                    //$("#textmrs{0}").toggle();
            }});
            </script>
            """.format(sid))

            
            # print("""
            #     <div id="tooltip" class="tooltip"></div>
            #     <div id="text-input" style="font-size: 150%%;">%s</div>
            # """)
            

            # $( "#myelement" ).click(function() {     
            #    $('#another-element').toggle("slide", { direction: "right" }, 1000);
            # });

            ####################################################################
            # PRINT DERIVATION TREE FROM JSON
            ####################################################################
            print("""
                <script>
                $( document ).ready(function() {
                                elem = document.getElementById('viztree%s');
                                deriv_json_string = '%s';
                                deriv_json = JSON.parse(deriv_json_string);
                                drawTree(elem, deriv_json);

                                elemChild = document.createElement('span');
                                elemChild.innerHTML = '<br><br>';
                                elem.appendChild(elemChild);
                                });
                </script>
                <div id='viztree%s'><br></div>
            """ % (sid, deriv_json, sid))

            
            ####################################################################
            # PRINT MRS FROM JSON
            ####################################################################
            print("""
                <script>
                $( document ).ready(function() {{
                                elem = document.getElementById('mrs{}');
                                mrs_json_string = '{}';
                                mrs_json = JSON.parse(mrs_json_string);
                                MRS(elem, mrs_json);
                                }});
                </script>
            """.format(sid, mrs_json))
            print("""<div id='mrs{}'><br>""".format(sid))
            print("""<div id="text-input" style="font-size: 150%%;">%s</div><br>""" % (sent))
            print("""</div>""")

            
        

            
            ####################################################################
            # PRINT DMRS FROM JSON
            ####################################################################
            print("""
                <script>
                $( document ).ready(function() {
                                elem = document.getElementById('dmrs%s');
                                dmrs_json_string = '%s';
                                dmrs_json = JSON.parse(dmrs_json_string);
                                DMRS(elem, dmrs_json);
                                });
                </script>
                <div id="tooltip" class="tooltip"></div>
                <div id='dmrs%s'></div>
            """ % (sid, dmrs_json, sid))

            print("<div id='textmrs%s'><br>" % (sid))
            print(mrs)
            print("<br><br></div>")

            # TOGGLE OFF ALL VISUALS
            print("""
            <script>
            $(document).ready(function(){{
                $("#mrs{0}").toggle();
                $("#viztree{0}").toggle();
                $("#dmrs{0}").toggle();
                $("#textmrs{0}").toggle();
            }});
            </script>
            """.format(sid))

        print("</ul>")

        # Make tree nodes clickable
        print("""
        <script>
        $(document).ready(function(){
          $(".ltdb").click(function(event){
  	    var elem = event.target;
	    var title = elem.getAttribute("title");
            window.open("showtype.cgi?typ=" + title);
        });
        });
        </script>
        """)
            
    else:
        print ("<p>No examples found for %s" % typ)
        

def showlexs (c, lextyp, lexid, limit, biglimit):
    if lexid:
        ## You want a specific word
        c.execute("""SELECT count(lexid) FROM lex 
        WHERE lexid=?""", (lexid,))
        results = c.fetchone()
    else:
        ## You want a lexical type
        c.execute("""SELECT count(lexid) FROM lex 
        WHERE typ=?""", (lextyp,))
        results = c.fetchone()
        
    if results and results[0] > 0:
        total = results[0]
        lem = dd(unicode) # lemma

        if lexid:
            ## You want a specific word
            c.execute("""SELECT lex.lexid, orth, freq FROM lex 
            LEFT JOIN lexfreq ON lex.lexid = lexfreq.lexid
            WHERE lex.lexid=?""", (lexid,))
            for (lexid, orth, freq) in c:
                lem[lexid] = cgi.escape(orth, quote=True)
        else:
            ## You want a lexical type
            c.execute("""SELECT lex.lexid, orth, freq FROM lex 
            LEFT JOIN lexfreq ON lex.lexid = lexfreq.lexid
            WHERE typ=? ORDER BY freq DESC LIMIT ?""", (lextyp, 5 * limit))
            for (lxid, orth, freq) in c:
                lem[lxid] = cgi.escape(orth, quote=True)

                
        c.execute("""SELECT lexid,  word, freq
FROM lexfreq WHERE lexid in (%s) ORDER BY lexid, freq DESC""" % \
                      ','.join('?'*len(lem)), 
                  lem.keys())
        lf = dd(int) # frequency
        sf = dd(unicode) # surface forms
        for (lxid, word,freq) in c:
        ### if the word was not in the corpus
            if not word:
                word=orth
            if not freq:
                freq=0
            sf[lxid] += "<span title='freq=%s'>%s</span>  " % (freq, 
                                                                cgi.escape(word, quote=True))
            lf[lxid] +=freq
        #lf=lf[:50]
        #sf=sf[:50]
        if limit < total and biglimit > limit:
            limtext= "({:,} out of {:,}: <a href='more.cgi?lextyp={}&lexid={}&limit={}'>more</a>)".format(limit, total,
                                                                                                         urllib.quote(lextyp, ''),
                                                                                                         lexid,
                                                                                                         biglimit)
        elif limit < total:
            limtext= "({:,} out of {:,})".format(limit, total)
        else:
            limtext ='({:,})'.format(total)
            
        print ("""<h2>Lexical Examples: {:,} {}</h2>""".format(min(len(lf),limit),
                                                               limtext))
        print("""<table><th>lexid</th><th>Lemma</th><th>Surface</th>
<th>Frequency</th></tr>""")  ### FIXME <th>Sentences
        for lxid in sorted(lf.keys()[:min(len(lf),limit)], key = lambda x: lf[x], reverse=True):
            print(u"""<td><a href='showtype.cgi?lexid={}'>{}</a></td>
<td>{}</td>
<td>{}</td>
<td align='right'>{:,d}</td></tr>""".format(lxid,  lxid,
                                            lem[lxid], sf[lxid],
                                            lf[lxid]))
        print("</table>")
#    else:
#        print ("<p>No examples found for %s (not even in the lexicon)" % lextyp)


###
### Header
###

def header():
    return """Content-type: text/html; charset=utf-8\n\n
<html>
  <head>
    <meta http-equiv='Content-Type' content='text/html; charset=utf-8'>
    <title>Linguistic Type Database (%s)</title>
    <link rel="stylesheet" type="text/css" href="%s/ltdb.css"/>

    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.3.1/jquery.min.js"></script>
    <script src="https://d3js.org/d3.v3.js"></script>

    <script src='tree.js' language='javascript'></script>
    <script src='dmrs.js' language='javascript'></script>
    <script src='mrs.js' language='javascript'></script>
    <script src='jquery-ui.js' language='javascript'></script>
    <link rel="stylesheet" type="text/css" href="jquery-ui.css"/>
    <script src='svg.js' language='javascript'></script>
    <link rel="stylesheet" type="text/css" href="delphin-viz.css"/>

    <link rel="icon"  type="image/png"  href="%s/ltdb.png"/>
  </head> 
  <body>
""" % (par['ver'], par['cssdir'], par['cssdir'])

def searchbar():
    return """
<div id="outline">
<div id="header">
<div id="menu">
<a href='%s/index.html'>Home</a>&nbsp;&nbsp;
<a href='%s/ltypes.cgi'>Lex Types</a>&nbsp;&nbsp;
<a href='%s/rules.cgi'>Rules</a>
</div> <!-- end of menu -->
<div id="confusing">  <!-- search for word -->
<div class='form'>
<form name="frm1" action="%s/search.cgi" method="GET">
Lemma:&nbsp;<input type="text" name="lemma" size=15
 placeholder="lemma">
<input type="submit" value="Go" name="submitbtn">
</form>
</div>
<div class='form'>

<form name="frm2" action="%s/search.cgi" method="GET">
Type:&nbsp;<input type="text" name="typ" size=20
 placeholder="lextype, lexid, rule or type">
<input type="submit" value="Go" name="submitbtn">
</form>
</div>
</div> <!-- end of confusing -->
</div> <!-- end of header -->
"""  %  (par['cssdir'], 
                                      par['cgidir'], par['cgidir'], 
                                      par['cgidir'], par['cgidir'])


    
def footer():
    return """</div> <!-- end of outline -->
  <br>
  <address>
  <a href='http://moin.delph-in.net/LkbLtdb'>Linguistic Type Database</a> 
    for the grammar %s; 
  <br>By Chikara Hashimoto, Luis Morgado da Costa and Francis Bond; 
  Maintained by Francis Bond &lt;<a href='mailto:bond@ieee.org'>bond@ieee.org</a>&gt;;
    <br>
    <a href ='https://github.com/fcbond/ltdb'>Source code (GitHub)</a>
  </address>
  </body>
</html>""" % (par['ver'])


def munge_desc(typ,description):
    """parse the description and return: description.rst, examples, names

    <ex>an example
    becomes
    #. an example 
    and the example is ('an example', typ, 1) 
    <nex>bad example
    becomes
    #. ∗ bad example 
    and the example is ('bad example', typ, 0) 
    <mex>bad example that we parse
    becomes
    #. ⊛ bad example that we parse
    and the example is ('bad example that we parse', typ, 1) 

    <name lang='en'>Bare Noun Phrase</name>
    becomes (typ, en, 'Bare Noun Phrase')
    """
    exes = []
    nams = []
    namere=re.compile(r"""<name\s+lang=["'](.*)['"]>(.*)</name>""")
    desc = []
    count = 1
    for l in description.splitlines():
        l = l.strip()
        if l.startswith("<ex>") or l.startswith("<nex>") \
           or l.startswith("<mex>"):
            if l.startswith("<ex>"):
                ex = l[4:].strip()
                exes.append((ex,typ,1))
                desc.append("\n{:d}. {}\n".format(count, ex))
            elif l.startswith("<nex>"):
                ex = l[5:].strip()
                exes.append((ex,typ,0))
                desc.append("\n{:d}. ∗ {}\n".format(count, ex))
            else: # l.startswith("<mex>")
                ex = l[5:].strip()
                exes.append((ex,typ,1))
                desc.append("\n{:d}. ⊛ {}\n".format(count, ex))
            if ex.startswith('*'):
                print("Warning: don't use '*' in examples, just use <nex>:", l,
                      file=sys.stderr)
            count += 1
        else:
            m = namere.search(l)
            if m:
                nams.append((typ,m.group(1),m.group(2)))
            else:
                desc.append(l)
    
    #print("\n".join(desc),exes,nams)
    return "\n".join(desc), exes, nams 


def get_lexinfo (lexid, c):
    c.execute("""SELECT typ, orth from lex 
                 WHERE lexid =? """, (lexid,))
    return c.fetchone()

def get_tdlinfo (typ, c):
    """TDL for a type (extracted by python)"""
    c.execute("""SELECT  src, line, tdl, docstring 
                 FROM tdl WHERE typ=?""", (typ,))
    return c.fetchall()

def get_typsum (typ, c):
    """get lemmas, globbed, ordered by exact match"""
    c.execute("""SELECT types.typ,  lname, status, freq 
    FROM types LEFT JOIN typfreq ON types.typ=typfreq.typ
    WHERE types.typ GLOB ?
    ORDER BY types.typ = ? DESC""", ('*{0}*'.format(typ), typ))
    return c.fetchall()
    
def get_leminfo (lemma,c):
    """get lemmas, globbed, ordered by exact match"""
    c.execute("""SELECT lex.typ, orth,  types.lname, words, lfreq, cfreq, lex.lexid 
                 FROM ltypes LEFT JOIN lex 
                 ON ltypes.typ = lex.typ 
                 LEFT JOIN types ON lex.typ = types.typ
                 WHERE orth GLOB ?
    ORDER BY orth = ? DESC""", ('*{0}*'.format(lemma), lemma))
    return c.fetchall()
