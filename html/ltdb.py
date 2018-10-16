###
### shared code for the ltdb
###
import sqlite3, collections, cgi, re, urllib
from collections import defaultdict as dd
import json

def getpar (params):
    par=dict()
    f = open(params)
    for l in f:
        (ft,vl)=l.strip().split('=')
        par[ft]=vl
    # par['css']='http://ronf/~bond/ltdb/Jacy_1301'
    # par['cgi']='http://ronf/~bond/cgi-bin/Jacy_1301'
    # par['db']='/home/bond/public_html/cgi-bin/Jacy_1301/lt.db'
    # par['ver']='Jacy_1301'
    return par

par=getpar('params')

def hlt (typs):
    "hyperlink a list of space seperated types"
    l = unicode()
    if typs:
        for t in typs.split():
            l += "<a href='%s/showtype.cgi?typ=%s'>%s " % (par['cgidir'], 
                                                           urllib.quote(t, ''),
                                                           t)
            return l
    else:
        return '<br'



retyp=re.compile(r"\b([-A-Za-z_+*0-9]+)\b")

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
    if t in types:
        return "<a href='{}/showtype.cgi?typ={}'>{}</a>".format(par['cgidir'], 
                                                                urllib.quote(t,''),
                                                                t)
    else:
        return t


def hlall (typs):
    "hyperlink all types in a description or documentation"
    if typs:
        typs=re.sub(r'(#[0-9][a-z][A-Z]+)', r"<span class='coref'>\1</span>", typs)
        return retyp.sub(hltyp, typs)
    else:
        return '<br>'



###
### Show example sentences:
### * take a dict with sets of (tfrom, tto), show all sentences
### sids = dd(set)
def showsents (c, typ, limit, biglimit):
    c.execute("SELECT freq FROM typfreq WHERE typ=?", (typ,))
    results = c.fetchone()
    if results and results[0] > 0:
        total = results[0]
        c.execute("""SELECT sid, kara, made FROM typind 
                 WHERE typ=? ORDER BY sid LIMIT ?""", (typ, limit))
        sids = dd(set)
        for (sid, kara, made) in c:
            sids[sid].add((kara, made))
        if limit < total and biglimit > limit:
            limtext= "({:,} out of {:,}: <a href='more.cgi?typ={}&limit={}'>more</a>)".format(limit, total, urllib.quote(typ,''), biglimit)
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
            c.execute("""SELECT mrs, mrs_json, dmrs_json, deriv_json FROM gold 
                        WHERE sid =  ? """, [sid])
            for (mrs, mrs_json, dmrs_json, deriv_json) in c:
                mrs = mrs
                mrs_json = mrs_json
                dmrs_json = dmrs_json
                deriv_json = deriv_json

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
            
            sent_text = ""
            for wid in sents[sid]:
                sent_text += sents[sid][wid][0] + " "

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
            print("""<div id="text-input" style="font-size: 150%%;">%s</div><br>""" % (sent_text))
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
            
    else:
        print ("<p>No examples found for %s" % typ)
        

def showlexs (c, lextyp, limit, biglimit):
    c.execute("""SELECT count(lexid) FROM lex 
WHERE typ=?""", (lextyp,))
    results = c.fetchone()
    if results and results[0] > 0:
        total = results[0]
        c.execute("""SELECT lex.lexid, orth, freq FROM lex 
LEFT JOIN lexfreq ON lex.lexid = lexfreq.lexid
WHERE typ=? ORDER BY freq DESC LIMIT ?""", (lextyp, 5 * limit))
        lem = dd(unicode) # lemma
        for (lexid, orth, freq) in c:
            lem[lexid] = cgi.escape(orth, quote=True)
        c.execute("""SELECT lexid,  word, freq
FROM lexfreq WHERE lexid in (%s) ORDER BY lexid, freq DESC""" % \
                      ','.join('?'*len(lem)), 
                  lem.keys())
        lf = dd(int) # frequency
        sf = dd(unicode) # surface forms
        for (lexid, word,freq) in c:
        ### if the word was not in the corpus
            if not word:
                word=orth
            if not freq:
                freq=0
            sf[lexid] += "<span title='freq=%s'>%s</span>, " % (freq, 
                                                                cgi.escape(word, quote=True))
            lf[lexid] +=freq
        #lf=lf[:50]
        #sf=sf[:50]
        if limit < total and biglimit > limit:
            limtext= "({:,} out of {:,}: <a href='more.cgi?lextyp={}&limit={}'>more</a>)".format(limit, total, urllib.quote(lextyp, ''), biglimit)
        elif limit < total:
            limtext= "({:,} out of {:,})".format(limit, total)
        else:
            limtext ='({:,})'.format(total)
        print ("""<h2>Lexical Examples: {:,} {}</h2>""".format(min(len(lf),limit), limtext))
        print("""<table><th>lexid</th><th>Lemma</th><th>Surface</th>
<th>Frequency</th></tr>""")  ### FIXME <th>Sentences
        for lexid in sorted(lf.keys()[:min(len(lf),limit)], key = lambda x: lf[x], reverse=True):
            print(u"""<td>{}</td><td>{}</td><td>{}</td>
<td align='right'>{:,}</td></tr>""".format(lexid, lem[lexid], sf[lexid], lf[lexid]))
## <td><a href='more.cgi?lextyp=%s'>more</a></td>                 lextyp))
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
  </head>
  <body>
""" % (par['ver'], par['cssdir'])

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
Type:&nbsp;<input type="text" name="typ" size=15
 placeholder="lextype, rule or type">
<input type="submit" value="Go" name="submitbtn">
</form>
</div>
</div> <!-- end of confusing -->
</div> <!-- end of header -->"""  %  (par['cssdir'], 
                                      par['cgidir'], par['cgidir'], 
                                      par['cgidir'], par['cgidir'])

    
def footer():
    return """</div> <!-- end of outline -->
  <br>
  <address>
  <a href='http://moin.delph-in.net/LkbLtdb'>Linguistic Type Database</a> for %s; 
  By Chikara Hashimoto and Francis Bond; 
  Maintained by Francis Bond &lt;<a href='mailto:bond@ieee.org'>bond@ieee.org</a>&gt;
  </address>
  </body>
</html>""" % (par['ver'])
