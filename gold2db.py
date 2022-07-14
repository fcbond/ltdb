#export PYTHONPATH=~/svn/pydelphin
# python3 gold2db.py
##
## takes two paramaters -- directory with the grammar and database
##
## Actually does the lexicon too :-)
##
## ToDo:
##   * add mrs in error log
##
import sqlite3, sys, re, os
from collections import defaultdict as dd
from delphin import itsdb, derivation, dmrs
from delphin.codecs import simplemrs, dmrsjson, mrsjson
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
#mlex=re.compile(r'\([0-9]+ ([^ ]+) [-0-9.]+ [0-9]+ [0-9]+ \("(.*?)" ')

### make a log in the same directory as the database
log = open(os.path.join(os.path.dirname(dbfile),"gold.log"), 'w')

golddir = '%s/tsdb/gold' % grmdir
typefreq=dd(int)                  # typefreq[type] = freq
lexfreq=dd(lambda: dd(int))       # lexfreq[lexid][surf] = freq
lxidfreq=dd(lambda: dd(int))      # lxidfreq[typ][lexid] = freq
typind=dd(lambda: dd(set))        # typind[type][(profile, sid)]((frm, to), ...)
sent=dd(list)                     # sent[(profile, sid)][(surf, lexid)]
roots=dd(lambda: 'rootless')
allroots=set()
for root, dirs, files in os.walk(golddir):
    #if not root.endswith('e'): for debugging, don't load everything
    #    continue
    ### find valid profiles
    if 'result' in files or 'result.gz' in files:
        # if 'mrs' not in root: ## debug
        #     continue
        print("Processing %s" % root, file=sys.stderr)
        ts = itsdb.TestSuite(root)
        for response in ts.processed_items():
            sid=response['i-id']
            profile = ts.path.name 
            if response['results']:
                first_result=response.result(0)
                deriv = first_result.derivation()
                tree = first_result.get('tree', '')
                deriv_str = deriv.to_udf(indent=None)
                try:
                    deriv_json = json.dumps(deriv.to_dict(fields=['id','entity','score','form','tokens']))
                except Exception as e:
                    log.write("\n\ncouldn't convert deriv to json:\n")
                    log.write(f"{root}: {profile} {sid} {e}\n")
                    deriv_json = '{}'
                try:
                    mrs_obj = first_result.mrs()
                    mrs_str = simplemrs.encode(mrs_obj,indent=True)
                    mrs_json = mrsjson.encode(mrs_obj)
                except Exception as e:
                    log.write("\n\nMRS couldn't be retrieved in pydelphin:\n")
                    log.write(f"{root}: {profile} {sid} {e}\n")
                    mrs_obj = None
                    mrs_str = ''
                    mrs_json = '{}'
                try:
                    dmrs_obj=dmrs.from_mrs(mrs_obj)
                    dmrs_json = dmrsjson.encode(dmrs_obj)
                except Exception as e:
                    log.write("\n\nMRS failed to convert in pydelphin:\n")
                    log.write(f"{root}: {profile} {sid} {e}\n")
                    log.write(response['i-input']) ### FIXME
                    log.write("\n\n")
                    log.write(repr(e))
                    if hasattr(e, 'message'):
                        log.write(e.message)
                        log.write("\n\n")
                    if mrs_str:
                        log.write(mrs_str))
                    dmrs_str = '{}'  
                    dmrs_json = '{}'
                # STORE gold info IN DB
                try:
                    c.execute("""INSERT INTO gold (profile, sid, sent, comment, 
                    deriv, deriv_json, pst, 
                    mrs, mrs_json, dmrs_json, flags) 
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                              (profile,
                               sid,
                               response['i-input'],
                               response['i-comment'],
                               deriv_str,
                               deriv_json,
                               tree,
                               mrs_str,
                               mrs_json,
                               dmrs_json,
                               None))
                except sqlite3.Error as e:
                    log.write('ERROR:   ({}) of type ({}), {}: {} {}\n'.format(e, type(e).__name__,
                                                                               root, profile, sid))

                ##leaves
                if deriv:
                    for (preterminal, terminal) in zip(deriv.preterminals(),deriv.terminals()):
                        lexid=preterminal.entity
                        surf=terminal.form
                        start=preterminal.start
                        end=preterminal.end
                        lexfreq[lexid][surf] +=1
                        sent[(profile, sid)].append((surf, lexid))
                        if ltypes[lexid]:
                            typefreq[ltypes[lexid]]  += 1
                            lxidfreq[ltypes[lexid]][lexid]   += 1
                            typind[ltypes[lexid]][(profile, sid)].add((start, end))
                    ### internal node (store as type)
                    for node in deriv.internals():
                        typ =  node.entity
                        start= node.start
                        end=   node.end
                        typefreq[typ]  += 1
                        typind[typ][(profile, sid)].add((start, end))

# ### each sentence should have a root
# for s in sent:
#     allroots.add(roots[s])
#     typind[roots[s]][s].add((0, len(sent[s])))
#     typefreq[roots[s]] += 1

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

for p,s in sent:
    ##print(s, " ".join([surf for (surf, lexid) in sent[s]]))
    try:
        for i, (w, l) in enumerate(sent[(p,s)]):
            c.execute("""INSERT INTO sent (profile, sid, wid, word, lexid) 
            VALUES (?,?,?,?,?)""", (p, s, i, w, l))
    except sqlite3.Error as e:
        log.write('ERROR:   ({}) of type ({}), {}: {} {}\n'.format(e, type(e).__name__,
                                                                   root, profile, sid))

for t in typind:
    for p,s in typind[t]:
        ##print("%s\t%s\t%s" % (t, s, typind[t][s]))
        for (k, m) in typind[t][(p, s)]:
            c.execute("""INSERT INTO typind (typ, profile, sid, kara, made) 
                 VALUES (?,?,?,?,?)""", (t, p, s, k, m))

   

    
conn.commit()
