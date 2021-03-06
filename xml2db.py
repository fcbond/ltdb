##
## takes two paramaters -- directory with the xml and database
##
## Actually does the lexicon too :-)
##
##  Creates the database
##  Reads in the lexicon
##  Add the types: rules, lrules, general, roots
##
## Fixme --- make a single routine for all the files
## Fixme --- read the names and use them
##
import sqlite3, sys, os
from lxml import etree
from collections import defaultdict as dd
import datetime
# import docutils
import docutils.core
cwd = os.getcwd()
### get some local utilities
sys.path.append(cwd + '/html')
import ltdb

if (len(sys.argv) < 3):
    # prints standard error msg (stderr)
    sys.stderr.write('You need to give two arguments, ' \
                         'xml directory and LTDB')
    sys.exit(1)
else:
    (script, xmldir, dbfile) = sys.argv

    
conn = sqlite3.connect(dbfile)    # loads dbfile as con
c = conn.cursor()    # creates a cursor object that can perform SQL commands with c.execute("...")

f=open('tables.sql')

###
### Make tables
### 
try:
    c.executescript(f.read())
    sys.stderr.write('Creating tables for ltdb\n')
except:
    pass # handle the error
conn.commit()

###
### Remember the examples
###
### example[typ] = { (sent, wf) } 
###
example = dd(set)


### 
### Start with the lexicon as we need it to tell the lexical types
### 
ltypes=set()
alltypes=set()
f = open('%s/lex.tab' % xmldir, encoding='utf-8')
for l in f:
    (lexid, ltype, orth, pred, altpred) = l.strip().split('\t')
    ltypes.add(ltype)
    try:
        c.execute("""INSERT INTO lex 
           (lexid, typ, orth, pred, altpred) 
           VALUES (?,?,?,?,?)""", 
                  (lexid, ltype, orth, pred, altpred))
    except sqlite3.Error as e:
        print('ERROR:   (%s) of type (%s), lexid: %s' % \
                  (e, type(e).__name__, lexid))

                                                             
print("Lexicon (%s/lex.tab) entered into the DB (%s)\n" % (xmldir, dbfile), 
      file=sys.stderr)


###
### Add the types: rules, lrules, general
###

kids = dd(set)

### Rules
try:
    t = etree.parse('%s/rules.xml' % xmldir)
    print("Parsed %s/rules.xml" % xmldir, file=sys.stderr)
except:
    print("Couldn't parse %s/rules.xml" % xmldir, file=sys.stderr)

for typ in t.getroot():
    for p in typ.get("parents").split():
        kids[p].add(typ.get("name"))
    alltypes.add(typ.get("name"))
    try:
        c.execute("""INSERT INTO types 
           (typ, parents, children, status,
           cat, val, cont, definition, arity, head) 
           VALUES (?,?,?,?, ?,?,?,?, ?,?)""", (typ.get("name"),
                                               typ.get("parents"),
                                               typ.get("children"),
                                               typ.get("status"),
                                               typ.get("cat"),
                                               typ.get("val"),
                                               typ.get("cont"),
                                               typ.text,
                                               typ.get("arity"),
                                               typ.get("head")))
    except sqlite3.Error as e:
        print('ERROR:   (%s) of type (%s), type: %s' % \
                  (e, type(e).__name__, typ.get("name")))
print("Rules (%s/rules.xml) entered into the DB (%s)\n" % (xmldir, dbfile), 
      file=sys.stderr)

### Lexical Rules
try:
    t = etree.parse('%s/lrules.xml' % xmldir)
    print("Parsed %s/lrules.xml" % xmldir, file=sys.stderr)
except:
    print("Couldn't parse %s/lrules.xml" % xmldir, file=sys.stderr)

for typ in t.getroot():
    for p in typ.get("parents").split():
        kids[p].add(typ.get("name"))
    alltypes.add(typ.get("name"))
    try:
        c.execute("""INSERT INTO types 
           (typ, parents, children, status,
           cat, val, cont, definition, arity, head) 
           VALUES (?,?,?,?, ?,?,?,?, ?,?)""", (typ.get("name"),
                                               typ.get("parents"),
                                               typ.get("children"),
                                               typ.get("status"),
                                               typ.get("cat"),
                                               typ.get("val"),
                                               typ.get("cont"),
                                               typ.text,
                                               typ.get("arity"),
                                               typ.get("head")))
    except sqlite3.Error as e:
        print('ERROR:   (%s) of type (%s), type: %s' % \
                  (e, type(e).__name__, typ.get("name")))
print("Lexical Rules (%s/lrules.xml) entered into the DB (%s)\n" % (xmldir, dbfile), 
      file=sys.stderr)


#### Types
try:
    t = etree.parse('%s/types.xml' % xmldir)
    print("Parsed %s/types.xml" % xmldir, file=sys.stderr)
except:
    print("Couldn't parse %s/types.xml" % xmldir, file=sys.stderr)


for typ in t.getroot():
    alltypes.add(typ.get("name"))
    if typ.get("children") or kids[typ.get("name")]:
        if typ.get("children"):
            for child in typ.get("children").split():
                kids[typ.get("name")].add(child)
        children = " ".join(kids[typ.get("name")])
    else:
        children=None
    if typ.get("name") in ltypes:
        status = 'ltype'
    else:
        status = 'type'


    descript = ""     # Let's assume empty comment to start
    for child in typ: # For now, only comments are expected, but we never know
        if child.tag == "comment":
            descript,exes,nams= ltdb.munge_desc(typ.get("name"),child.text)
            for (s,t,wf) in exes:
                example[t].add((s, wf))
                
    try:
        c.execute("""INSERT INTO types 
                 (typ, parents, children, status,
                  cat, val, cont, definition, description) 
                 VALUES (?,?,?,?, ?,?,?,?,?)""", (typ.get("name"),
                                                  typ.get("parents"),
                                                  children,
                                                  status,
                                                  typ.get("cat"),
                                                  typ.get("val"),
                                                  typ.get("cont"),
                                                  typ.text,
                                                  descript))
    except sqlite3.Error as e:
        print('ERROR:   (%s) of type (%s), type: %s' % \
                  (e, type(e).__name__, typ.get("name")))
print("Types (%s/types.xml) entered into the DB (%s)\n" % (xmldir, dbfile), 
      file=sys.stderr)

#### Roots
try:
    t = etree.parse('%s/roots.xml' % xmldir)
    print("Parsed %s/roots.xml" % xmldir, file=sys.stderr)
except:
    print("Couldn't parse %s/roots.xml" % xmldir, file=sys.stderr)

for typ in t.getroot():
    alltypes.add(typ.get("name"))
    children=None
    try:
        c.execute("""INSERT INTO types 
                 (typ, status) 
                 VALUES (?,?)""", 
                  (typ.get("name"), typ.get("status")))
    except sqlite3.Error as e:
        print('ERROR:   (%s) of type (%s), type: %s' % \
                  (e, type(e).__name__, typ.get("name")))
print("Types (%s/roots.xml) entered into the DB (%s)\n" % (xmldir, dbfile), 
      file=sys.stderr)


item = open(os.path.join(os.path.dirname(dbfile),"item"), 'w')
iid = 1
now = datetime.datetime.isoformat(datetime.datetime.now())
for t in example:
    ### FIXME escape the examples or use PyDelphin
    for s, w in example[t]:
        print(str(iid), '', '', '', '', 
              t, s, '', '', '',
              str(w), '', '', 'ltdb', now,
              file = item, sep='@')
        iid += 1


        
conn.commit()
