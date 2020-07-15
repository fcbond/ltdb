##
## takes two paramaters -- tdl grammarfile and database
##
from collections import defaultdict as dd
from pathlib import Path

from delphin import tdl

import sqlite3, sys, os
import re

###  ToDo
# identify lextypes
# get orth
# 
if (len(sys.argv) < 3):
    # prints standard error msg (stderr)
    print('''You need to give two arguments, 
 ace config file and LTDB''', file=sys.stderr)
    sys.exit(1)
else:
    (script, config, dbfile) = sys.argv
    print("Adding files from %s to %s" % (config, dbfile), file=sys.stderr)


## make a log in the same directory as the database
log = open(os.path.join(os.path.dirname(dbfile),"tdl.log"), 'w')
ver = open(os.path.join(os.path.dirname(dbfile),"tdl_ver"), 'w')
    
#grammar = '/home/bond/svn/mo/ace/config-mal.tdl'
tdls = []
hierarchy = []  #(child, parent)
types = dd(list)
les = {}


def read_cfg (config, ver):
    """
    read the config file, find the grammar and version
    """
    for l in open(config):
        grmmatch =  re.findall(r'grammar-top\s+:=\s+"([^"]+)".', l.strip())
        if grmmatch:
            grammar = grmmatch[0]
        vermatch =  re.findall(r'version\s+:=\s+"([^"]+)".', l.strip())
        if vermatch:
            version = vermatch[0]
    version_file = os.path.join(os.path.dirname(config), version)
    grammar_file = os.path.join(os.path.dirname(config), grammar)
    print(version_file, file=ver)
    return grammar_file, version_file


def read_grm (grammarfile, tdls, types, hierarchy, les):
    print("FILE", grammarfile)
    path = Path(grammarfile)
    base = path.parent
    for event, obj, lineno in tdl.iterparse(grammarfile):
        if  event == "LineComment":
            continue
        #print (event, obj, lineno)
        # if event == "BeginEnvironment":
        #     status = getattr(obj, 'status', 'type')
        #     print ("Environment is", status)
        if event == "EndEnvironment":
            status = getattr(obj, 'status', 'type')
            for entry in obj.entries:
                #print('ENTRY', entry, status)
                if isinstance(entry,tdl.FileInclude):
                    path = Path(base, entry.path).with_suffix('.tdl')
                    if path.is_file():
                        process_type(str(base), str(path), status, tdls, hierarchy, les)
                    else:
                        print('INCLUDED FILE NOT FOUND: {!s}'.format(path))
                else:
                    print('what to do with', entry.status, file=log)

def  process_type(base, path, status, tdls, hierachy, les):
    if 'root' in path:
        status = 'root'
    elif 'parse-nodes' in path:
        status = 'labels'

    print(f"Processing types in {path} as {status}")
    for event, obj, lineno in tdl.iterparse(path): # assume utf-8
        #print(lineno, event, sep = '\t')
        if event in ['TypeDefinition',  'TypeAddendum',
                     'LexicalRuleDefinition']:
            # if obj.documentation(): ### The tdl has a docstring
            #     descript,exes,nams= ltdb.munge_desc(obj.identifier,obj.documentation())
            #     obj.docstring=None
            # else:
            # get the parents
            parents = [c for c in obj.conjunction.types()]
            if status == 'lex-entry':
                if len(parents) != 1:
                    print ("LE has non unique parent", obj.identifier, parents)
                else:
                    ### (lex-type, docstring)
                    ### fixme get orth, pred, altpred
                    orths = obj.conjunction.get('ORTH', default=None)
                    try:
                        orth=' '.join([str(s) for s in orths.values()])
                    except:
                        orth = ''
                        print('No Orthography', obj.identifier,
                              sep = '\t', file=log) 
                    pred=obj.conjunction.get('SYNSEM.LKEYS.KEYREL.PRED', default=None)
                    altpred=obj.conjunction.get('SYNSEM.LKEYS.ALTKEYREL.PRED', default=None)
                    carg=obj.conjunction.get('SYNSEM.LKEYS.KEYREL.CARG', default=None)
                    altcarg=obj.conjunction.get('SYNSEM.LKEYS.ALTKEYREL.CARG', default=None)
                    les[obj.identifier] = (str(parents[0]), orth, pred, altpred, carg, altcarg, obj.documentation())
            else: # not a lexical entry
                tdls.append((obj.identifier,
                         path[len(base):], lineno,
                         event,
                         tdl.format(obj),
                         obj.documentation()))
            for c in parents:
                hierarchy.append((obj.identifier, str(c)))
            if event != 'TypeAddendum':
                types[obj.identifier].append(status)
        elif event not in ['LineComment', 'BlockComment',
                           'BeginEnvironment', 'EndEnvironment',
                           'FileInclude' ]:
            ## ToDo log properly
            print('Unknown Event', event, obj, path, lineno,
                  sep = '\t',
                  file=log)
    # except Exception as e:
    #     print("Unable to parse tdl for {}, see log for details".format(path),
    #           file=sys.stderr)
    #     print("Unable to parse tdl for {}".format(path),
    #           file=log)
    #     if hasattr(e, 'message'):
    #         print(e.message, file=log)
    #     else:
    #         print(str(e), file=log)


def intodb(dbfile, tdls, hierarchy, types,les):
    conn = sqlite3.connect(dbfile)    # loads dbfile as con
    c = conn.cursor()    # creates a cursor object that can perform SQL commands with c.execute("...")
    c.executemany("""INSERT INTO tdl (typ, src, line, kind, tdl, docstring)
    VALUES (?, ?, ?, ?, ?, ?)""", tdls)

    c.executemany("""INSERT INTO hie (child, parent)
    VALUES (?,?)""", hierarchy)

    parents = dd(set)
    children = dd(set)
    for (ch,pa) in hierarchy:
        parents[ch].add(pa)
        children[pa].add(ch)
        
    typs = []
    for t,s in types.items():
        typs.append((t, s[0], ' '.join(parents[t]), ' '.join(children[t])))
        
    c.executemany("""INSERT OR IGNORE INTO types (typ, status, parents, children)
    VALUES (?,?,?,?) """, typs)

    # too slow
    # c.execute("""CREATE TEMPORARY TABLE subs 
    #            AS  SELECT parent, group_concat(child, ' ') as kids
    #            FROM hie GROUP BY parent""")
    # c.execute("""UPDATE types 
    # SET children = (SELECT kids FROM subs 
    # WHERE types.typ = subs.parent AND types.children is NULL)""")
    # c.execute("""drop table subs""")

    # c.execute("""CREATE TEMPORARY TABLE sups 
    #            AS  SELECT child, group_concat(parent, ' ') as olds
    #            FROM hie GROUP BY child""")
    # c.execute("""UPDATE types 
    # SET parents = (SELECT olds FROM sups 
    # WHERE types.typ = sups.child AND types.parents is NULL)""")
    # c.execute("""drop table sups""")

    ### lexical items
    litems = []
    for t in les:
        litems.append((t,)+les[t])  
    c.executemany("""INSERT OR IGNORE INTO lex (lexid, typ, orth, pred, altpred, carg, altcarg, docstring)
    VALUES (?,?,?,?,?,?,?,?) """, litems)

    ### make immediate hypernyms of lexical entries 'lex-type'
    c.execute("""UPDATE types SET status='lex-type' 
    WHERE typ IN (SELECT typ FROM lex)""")
    
    conn.commit()

grammar, version = read_cfg(config,ver)
print(grammar, version)
read_grm(grammar,tdls,hierarchy, types, les)
intodb(dbfile, tdls, hierarchy, types, les)

# for thing in tdls:
#     print(thing)
# for thing in hierarchy:
#     print(thing)
