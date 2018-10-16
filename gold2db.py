#export PYTHONPATH=~/svn/pydelphin
# python3 gold2db.py
##
## takes two paramaters -- directory with the xml and database
##
## Actually does the lexicon too :-)
##
import sqlite3, sys, re, os
from collections import defaultdict as dd
from delphin import itsdb
import delphin.mrs
import delphin.derivation
import delphin.mrs.xmrs
import delphin.mrs.simplemrs
import json

if (len(sys.argv) < 3):
    # prints standard error msg (stderr)
    print('You need to give two arguments, ' \
              'grammar directory and LTDB', file=sys.stderr)
    sys.exit(1)
else:
    (script, grmdir, dbfile) = sys.argv

conn = sqlite3.connect(dbfile)    # loads dbfile as con
c = conn.cursor()    # creates a cursor object that can perform SQL commands with c.execute("...")

ltypes =dd(str)
lorth =dd(str)
lfreq=dd(int)
lex=dd(set)
c.execute("select lexid, typ, orth FROM lex")
for (lexid, typ, orth) in c:
    ltypes[lexid] = typ
    lorth[lexid]= orth
    lfreq[typ] +=1
    lex[typ].add(lexid)

mroot=re.compile(r'^\(([-a-zA-z0-9_+]+?)\s+\(')
mrule=re.compile(r'\([0-9]+ ([^ ]+) [-0-9.]+ ([0-9]+) ([0-9]+) ')
mlex=re.compile(r'\([0-9]+ ([^ ]+) [-0-9.]+ [0-9]+ [0-9]+ \("(.*?)" ')

golddir = '%s/tsdb/gold' % grmdir
typefreq=dd(int)                  # typefreq[type] = freq
lexfreq=dd(lambda: dd(int))       # lexfreq[lexid][surf] = freq
lxidfreq=dd(lambda: dd(int))      # lxidfreq[typ][lexid] = freq
typind=dd(lambda: dd(set))        # typind[type][sid]((frm, to), ...)
sent=dd(list)                     # sent[sid][(surf, lexid)]
pname=dict()                      # pname[sid]=profile 
roots=dd(lambda: 'rootless')
allroots=set()
for root, dirs, files in os.walk(golddir):
    ### find valid profiles
    if 'result' in files or 'result.gz' in files:
        # if 'mrs' not in root: ## debug
        #     continue
        print("Processing %s" % root, file=sys.stderr)
        profile = itsdb.ItsdbProfile(root)
        head, profname = os.path.split(root)
        for row in profile.read_table('result'):
            pid = row['parse-id']
            pname[pid] = profname
            deriv = row['derivation']  # DERIVATION TREE
            deriv_json = delphin.derivation.Derivation.from_string(deriv).to_dict(fields=['id','entity','score','form','tokens'])            
            mrs_string = row['mrs']
            try:
                mrs_obj = delphin.mrs.simplemrs.loads(mrs_string, single=True, version=1.1, strict=False, errors='warn')
                # mrs_obj = delphin.mrs.simplemrs.loads(row['mrs'], single=True, version=1.1, strict=False, errors='warn')
                # mrs_string = row['mrs']  # CHANGING
                mrs_json = delphin.mrs.xmrs.Mrs.to_dict(mrs_obj)
                dmrs_json = delphin.mrs.xmrs.Dmrs.to_dict(mrs_obj)
            except:
                sys.stderr.write("\n\nMRS failed to convert in pydelphin:\n")
                sys.stderr.write(str(mrs_string))
                sys.stderr.write("\n\n")
                mrs_json = dict()
                dmrs_json = dict()
            
            # STORE gold info IN DB
            c.execute("""INSERT INTO gold (sid, deriv, deriv_json, pst, mrs, mrs_json, dmrs_json, flags) 
                         VALUES (?,?,?,?,?,?,?,?)""", (pid, deriv, json.dumps(deriv_json), None, mrs_string, json.dumps(mrs_json), json.dumps(dmrs_json), None))


            ##print(pid, '\t', deriv)
            ##print('\n\n')
            ### Leaves (store as both type and token)
            ### lexemes, lexical types
            m = re.findall(mlex,deriv)
            lexids=set()
            if m:
                #print('leaves')
                #print(m)
                wid =0
                for (lexid, surf) in m:
                    lexids.add(lexid)
                    lexfreq[lexid][surf] +=1
                    sent[pid].append((surf, lexid))
                    if ltypes[lexid]:
                        typefreq[ltypes[lexid]]  += 1
                        lxidfreq[ltypes[lexid]][lexid]   += 1
                        typind[ltypes[lexid]][pid].add((wid, wid+1))
                    wid+=1
            ### rules (store as type)
            m = re.findall(mrule,deriv)
            if m:
                for (typ, frm, to) in m:
                    if typ not in lexids: ## counted these!
                        typefreq[typ]  += 1
                        typind[typ][pid].add((frm, to))
                #print('rule')
                #print(m)
            ### Root (treat as another type)
            m = re.search(mroot,deriv)
            if m:
                #print('root {}'.format(root))
                #print(m.groups()[0])
                #print(deriv)
                #print()
                roots[pid] = m.groups()[0]

            ##print('\n\n\n')


### each sentence should have a root
for s in sent:
    allroots.add(roots[s])
    typind[roots[s]][s].add((0, len(sent[s])))
    typefreq[roots[s]] += 1

### calculate the lexical type frequencies
for typ in lxidfreq:
    words=list()  ## get three most frequent words in corpus
    for lexid in sorted(lxidfreq[typ], 
                        key=lambda x:lxidfreq[typ][x],
                        reverse=True):  
        if lorth[lexid]:
            ### lexid<TAB>freq<TAB>orthography
            words.append(lexid)
        if len(words) > 2:
            break
    if len(words) < 3:  ### if less than three examples in the corpus
                        ### add more from the lexicon
        for lexid in lex[typ]:
            if lorth[lexid] and (lexid not in words):
                words.append(lexid)
            if len(words) > 2:
                break
    wrds='\n'.join("%s\t%d\t%s" % (lexid,  
                                   lxidfreq[typ][lexid],
                                   lorth[lexid]) 
                   for lexid in words) 
    ##print (typ, wrds)
    c.execute("""INSERT INTO ltypes
  (typ, words, lfreq, cfreq) 
  VALUES (?,?,?,?)""", (typ, wrds, 
                        lfreq[typ],
                        typefreq[typ]))

### Wack these into a database
for typ in typefreq:
    #print("%d\t%s" % (typefreq[typ], typ))
    c.execute("""INSERT INTO typfreq (typ, freq) 
                 VALUES (?,?)""", (typ, typefreq[typ]))
for l in lexfreq:
    for w in lexfreq[l]:
        #print("%d\t%s\t%s" % (lexfreq[l][w], l, w))
        c.execute("""INSERT INTO lexfreq (lexid, word, freq) 
                 VALUES (?,?,?)""", (l, w, lexfreq[l][w]))

for s in sent:
    ##print(s, " ".join([surf for (surf, lexid) in sent[s]]))
    for i, (w, l) in enumerate(sent[s]):
        c.execute("""INSERT INTO sent (profile, sid, wid, word, lexid) 
                 VALUES (?,?,?,?,?)""", (pname[s], s, i, w, l))

 

for t in typind:
    for s in typind[t]:
        ##print("%s\t%s\t%s" % (t, s, typind[t][s]))
        for (k, m) in typind[t][s]:
            c.execute("""INSERT INTO typind (typ, sid, kara, made) 
                 VALUES (?,?,?,?)""", (t, s, k, m))

### bit of a hack, but my lisp foo is weak
# for r in allroots:
#     c.execute("""INSERT INTO types (typ, status) 
#                  VALUES (?,?)""", (r, 'root'))

   

    
conn.commit()
