#export PYTHONPATH=~/svn/pydelphin
# python3 tdl2db.py
##
## takes two paramaters -- directory with the tdl and database
##
## currently just does the provenance
##
import sqlite3, sys, re, os
from collections import defaultdict as dd
#from delphin import itsdb

if (len(sys.argv) < 3):
    # prints standard error msg (stderr)
    print('''You need to give two arguments, 
tdl directory and LTDB''', file=sys.stderr)
    sys.exit(1)
else:
    (script, grmdir, dbfile) = sys.argv

conn = sqlite3.connect(dbfile)    # loads dbfile as con
c = conn.cursor()    # creates a cursor object that can perform SQL commands with c.execute("...")


# ltypes =dd(str)
# lorth =dd(str)
# lfreq=dd(int)
# lex=dd(set)
# c.execute("select lexid, typ, orth FROM lex")
# for (lexid, typ, orth) in c:
#     ltypes[lexid] = typ
#     lorth[lexid]= orth
#     lfreq[typ] +=1
#     lex[typ].add(lexid)

mprov=re.compile(r'(;?)\s*([-_a-zA-Z0-9.]+)\s*(:=|:\+|:<|:-)')
# mrule=re.compile(r'\([0-9]+ ([^ ]+) [-0-9.]+ ([0-9]+) ([0-9]+) ')
# mlex=re.compile(r'\([0-9]+ ([^ ]+) [-0-9.]+ [0-9]+ [0-9]+ \("(.*?)" ')

prov=dd(lambda: dd(set))      # prov[type][mod] = ((file, lineno),())


for root, dirs, files in os.walk(grmdir):
    ### find valid profiles
    for f in files:
        if f.endswith('.tdl'):
            print("Processing %s" % f, file=sys.stderr)
            fh = open('%s/%s' % (grmdir, f), encoding='utf-8')
            for i,l in enumerate(fh):
                m = re.findall(mprov,l)
                for (com, typ, mod) in m:
                    if com !=';':  ### I don't check for /* */: my bad :-)
                        print(f, i, com, typ, mod)
#         profile = itsdb.TsdbProfile(root)
#         for row in profile.get_table('result').rows():
#             pid = row['parse-id']
#             deriv = row['derivation']
#             ##print(pid, '\t', deriv)
#             ##print('\n\n')
#             ### Leaves (store as both type and token)
#             ### lexemes, lexical types
#             m = re.findall(mlex,deriv)
#             lexids=set()
#             if m:
#                 #print('leaves')
#                 #print(m)
#                 wid =0
#                 for (lexid, surf) in m:
#                     lexids.add(lexid)
#                     lexfreq[lexid][surf] +=1
#                     sent[pid].append((surf, lexid))
#                     if ltypes[lexid]:
#                         typefreq[ltypes[lexid]]  += 1
#                         lxidfreq[ltypes[lexid]][lexid]   += 1
#                         typind[ltypes[lexid]][pid].add((wid, wid+1))
#                     wid+=1
#             ### rules (store as type)
#             m = re.findall(mrule,deriv)
#             if m:
#                 for (typ, frm, to) in m:
#                     if typ not in lexids: ## counted these!
#                         typefreq[typ]  += 1
#                         typind[typ][pid].add((frm, to))
#                 #print('rule')
#                 #print(m)
#             ### Root (treat as another type)
#             m = re.search(mroot,deriv)
#             if m:
#                 #print('root')
#                 #print(m.groups()[0])
#                 typefreq[m.groups()[0]] += 1
#                 typind[m.groups()[0]][pid].add((0, len(sent[pid])))


#             ##print('\n\n\n')

# ### calculate the lexical type frequencies
# for typ in lxidfreq:
#     words=list()  ## get three most frequent words in corpus
#     for lexid in sorted(lxidfreq[typ], 
#                         key=lambda x:lxidfreq[typ][x],
#                         reverse=True):  
#         if lorth[lexid]:
#             ### lexid<TAB>freq<TAB>orthography
#             words.append(lexid)
#         if len(words) > 2:
#             break
#     if len(words) < 3:  ### if less than three examples in the corpus
#                         ### add more from the lexicon
#         for lexid in lex[typ]:
#             if lorth[lexid] and (lexid not in words):
#                 words.append(lexid)
#             if len(words) > 2:
#                 break
#     wrds='\n'.join("%s\t%d\t%s" % (lexid,  
#                                    lxidfreq[typ][lexid],
#                                    lorth[lexid]) 
#                    for lexid in words) 
#     print (typ, wrds)
#     c.execute("""INSERT INTO ltypes
#   (typ, words, lfreq, cfreq) 
#   VALUES (?,?,?,?)""", (typ, wrds, 
#                         lfreq[typ],
#                         typefreq[typ]))

# ### Wack these into a database
# for typ in typefreq:
#     #print("%d\t%s" % (typefreq[typ], typ))
#     c.execute("""INSERT INTO typfreq (typ, freq) 
#                  VALUES (?,?)""", (typ, typefreq[typ]))
# for l in lexfreq:
#     for w in lexfreq[l]:
#         #print("%d\t%s\t%s" % (lexfreq[l][w], l, w))
#         c.execute("""INSERT INTO lexfreq (lexid, word, freq) 
#                  VALUES (?,?,?)""", (l, w, lexfreq[l][w]))

# for s in sent:
#     ##print(s, " ".join([surf for (surf, lexid) in sent[s]]))
#     for i, (w, l) in enumerate(sent[s]):
#         c.execute("""INSERT INTO sent (sid, wid, word, lexid) 
#                  VALUES (?,?,?,?)""", (s, i, w, l))
# for t in typind:
#     for s in typind[t]:
#         ##print("%s\t%s\t%s" % (t, s, typind[t][s]))
#         for (k, m) in typind[t][s]:
#             c.execute("""INSERT INTO typind (typ, sid, kara, made) 
#                  VALUES (?,?,?,?)""", (t, s, k, m))



        
# conn.commit()
