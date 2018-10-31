#
# Make the IndexPage
#
# ToDo
#  * add error logs
#  * calculate metadata
#  * link license file
#
import sys, os
import datetime
from collections import OrderedDict
#import html/ltdb

(script, version, grmdir) = sys.argv

print("""
<html>
<head>
  <title>{0} ltdb</title>
  <link rel='stylesheet' type='text/css' href='lextypedb.css'/>
</head>
<body>
<h1>Welcome to {0}</h1>
<ul>  
  <li>  <a href='../../cgi-bin/{0}/search.cgi'>Lexical Type Database for {0}</a> ( <a href='../../cgi-bin/{0}/search.cgi'>Search</a>)
  <li>  <a href='http://wiki.delph-in.net/moin/LkbLtdb'>Lexical Type Database Wiki</a>
  <li>  <a href='http://wiki.delph-in.net/moin/FrontPage'>DELPH-IN Wiki</a>
</ul>
""".format(version))

# if [ -n "$grammarurl" ]; then
# echo "  <li>  <a href='$grammarurl'>Grammar Home Page</a>"  >> ${HTML_DIR}/index.html
# fi
MF = os.path.join(grmdir, 'METADATA')
LF = os.path.join(grmdir, 'LICENSE')
md = OrderedDict()
try:
    fh = open(MF, 'r')
    # Store configuration file values
    for l in fh:
        if l.strip() and l[0].isupper():
            (att,val) = l.strip().split('=')
            val=val.strip('"')
            if val:
                md[att]=val
except FileNotFoundError:
    print("METADATA not found at {}".format(MF),file=sys.stderr)

try:
    fh = open(LF, 'r') 
except FileNotFoundError:
    print("LICENSE not found at {}".format(LF),file=sys.stderr)

###
### print metadata
###
#required external resources	
#associated resources	
#FIXME: calculate numbers from LTDB
#lexical items	
#lexical rules	
#grammar rules	
#features	
#types (with glb)	

print("<table>")
print("  <caption>Metadata for {}<caption>".format(version))
for a,v in md.items():
    a=a.replace('_',' ')
    if a not in 'VCS BCP_47':
        a=a.title()
    if v.startswith('http'):
        print("<tr><td>{0}</td><td><a href='{1}'>{1}</a></td></tr>".format(a,v))
    elif a.endswith('Email'):
        print("<tr><td>{0}</td><td><a href='mailto:{1}?subject={2}'>{1}</a></td></tr>".format(a,v,version))
    else:
        print("<tr><td>{}</td><td>{}</td></tr>".format(a,v))
print("</table>")

print("""
<h3>Logs</h3>
<ul>
   <li><a href='lkb.log'>LKB conversion log</a>
   <li><a href='tdl.log'>TDL conversion log</a>
   <li><a href='gold.log'>Gold profiles conversion log</a>
</ul>
""")

    
print("""  <p>Created on {}</p>
  </html>
</body>""".format(datetime.datetime.now()))
