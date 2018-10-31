##
## takes two paramaters -- directory with the xml and database
##
## Actually does the lexicon too :-)
##
##  Creates the database
##  Reads in the lexicon
##  Add the types: rules, lrules, general, roots
##

import sqlite3, sys
from lxml import etree
from collections import defaultdict as dd
# import docutils
import docutils.core

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
            descript = child.text


            # descript = descript.replace("\n","<br>") # THIS IS NOT WORKING,
            # the CGI is probably messing it up at a later stage
            # sys.stderr.write(child.text + 'spam\n') #TEST#

    # Convert the comment from RST to HTML
    # descript_html = docutils.core.publish_parts(descript,writer_name='html',
    #                 settings_overrides= {'table_style':'colwidths-auto'})['body']
            
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


### Description
try:
    t = etree.parse('%s/linguistics.xml' % xmldir,
                    parser=etree.XMLParser(remove_comments=True))
    print("Parsed %s/linguistics.xml" % xmldir, file=sys.stderr)
except:
    print("Couldn't parse %s/linguistics.xml" % xmldir, file=sys.stderr)

for typ in t.getroot():
    #print(etree.tostring(typ, pretty_print=True))
    lname = None
    for el in typ.iter('name'):
        lname = el.text
    description=None
    for el in typ.iter('description'):
        description = el.text
    todo=None
    for el in typ.iter('todo'):
        todo = el.text
    exes = list()
    for el in typ.iter('ex'):
        if el.text:
            exes.append('ex\t%s' % el.text)
    for el in typ.iter('nex'):
        if el.text:
            exes.append('nex\t%s' % el.text)
    criteria = '\n'.join(exes)
    typname = typ.get('val')
    if typname not in alltypes:
        print('ERROR:  unknown type (%s) in linguistics.xml' % \
                      typname)
    ##print (typname, lname, description, criteria)
    if typname:
        try:
            c.execute("""UPDATE types SET
           lname =?, description =?, criteria =?,
		   reference =?, todo =?
           WHERE typ=?""" , (lname,
                             description,
                             criteria,
                             None,
                             todo,
                             typname))
        except sqlite3.Error as e:
            print('ERROR:   (%s) of type (%s), type: %s' % \
                      (e, type(e).__name__, typ.get("name")))
print("Descriptions (%s/linguistics.xml) entered into the DB (%s)\n" % (xmldir, dbfile), 
      file=sys.stderr)

        
conn.commit()
