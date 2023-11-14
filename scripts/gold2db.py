import sqlite3, sys, re, os
from collections import defaultdict as dd
from delphin import itsdb, derivation, dmrs, tsdb
from delphin.codecs import simplemrs, dmrsjson, mrsjson
import json

import warnings

def extract_span(terminal):
    str_tok = terminal.tokens[0][1]
    from_match = re.search(r'\+FROM\s+\\"(\d+)\\"', str_tok)
    to_match = re.search(r'\+TO\s+\\"(\d+)\\"', str_tok)

    if from_match and to_match:
        from_value = int(from_match.group(1))
        to_value = int(to_match.group(1))
        return from_value, to_value
    else:
        return None

def get_surface_form(terminal, item):
    span = extract_span(terminal)
    if span:
        return item['i-input'][span[0]:span[1]]
    else:
        return terminal.form

def ver_match(ver, profile, log):
    """ 
    returns True iff the version matches the runs
    """
    grms = set(tsdb.split(l)[7] for l in tsdb.open(profile, 'run'))
    if len(grms) == 1:
        if grms.pop() == ver:
            return True
        else:
            return False            
    elif len(grms) > 1:
        print(f"Warning: "
              "two different grammars used in this profile {profile}",
              file=sys.stderr)
        return False
    elif len(grms) == 0:
        print(f"Warning: "
              "no grammar indicated in this profile {root}",
              file=sys.stderr)
        return False

def process_results(root,log):
    lexind=dd(lambda: dd(set))        # lexind[type][(profile, sid)]((frm, to), ...)
    typind=dd(lambda: dd(set))        # typind[type][(profile, sid)]((frm, to), ...)
    sent=dd(list)                     # sent[(profile, sid)][(surf, lexid)]
    gold = list()
    
    ts = itsdb.TestSuite(root)
    for response in ts.processed_items():
        sid=response['i-id']
        profile = ts.path.name 
        if response['results']:
            first_result=response.result(0)
            # replace instances of numbers with commas "0,0000" with "0.0000":
            deriv = first_result.derivation()
            tree = first_result.get('tree', '')
            deriv_str = deriv.to_udf(indent=None)
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
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
                except Exception as e:
                    log.write("\n\nMRS failed to convert to DMRS:\n")
                    log.write(f"{root}: {profile} {sid} {e}\n")
                    log.write(response['i-input']) ### FIXME
                    log.write("\n\n")
                    log.write(repr(e))
                    if hasattr(e, 'message'):
                        log.write(e.message)
                        log.write("\n\n")
                    if mrs_str:
                        log.write(mrs_str)
                    dmrs_obj = None  
                try:
                    if dmrs_obj:
                        dmrs_json = dmrsjson.encode(dmrs_obj)
                    else:
                        dmrs_json = '{}'
                except Exception as e:
                    log.write("\n\nDMRS failed to serialize to JSON:\n")
                    log.write(f"{root}: {profile} {sid} {e}\n")
                    log.write(response['i-input']) ### FIXME
                    log.write("\n\n")
                    log.write(repr(e))
                    if hasattr(e, 'message'):
                        log.write(e.message)
                        log.write("\n\n")
                    if mrs_str:
                        log.write(mrs_str)
                    dmrs_json = '{}'
            for warn in caught_warnings:
            # STORE gfor warn in caught_warnings:
                log.write(f"\n\nWarning: {warn.message}\n")
                log.write(f"{root}: {profile} {sid}\n")
            gold.append((profile,
                         sid,
                         response['i-input'],
                         response['i-comment'],
                         deriv_str,
                         deriv_json,
                         tree,
                         mrs_str,
                         mrs_json,
                         dmrs_json))
            ### get the nodes
            if deriv:
                for  (preterminal, terminal) in zip(deriv.preterminals(),
                                                    deriv.terminals()):
                    lexid=preterminal.entity
                    if response['p-tokens']:
                        surf = get_surface_form(terminal, response)
                    else:
                        surf=terminal.form
                    start=preterminal.start
                    end=preterminal.end
                    ### get cfrom cto
                    sent[(profile, sid)].append((surf, lexid))
                    lexind[lexid][(profile, sid)].add((start, end))
                ### internal node (store as type)
                for node in deriv.internals():
                    typ =  node.entity
                    start= node.start
                    end=   node.end
                    typind[typ][(profile, sid)].add((start, end))       
    return gold, sent, lexind, typind

def gold2db(conn, gold, log):
    c = conn.cursor()
    #c.execute("""INSERT INTO tdl (typ) VALUES ('typical')""")
    for g in gold:
        try:
            c.execute("""INSERT INTO gold (profile, sid, sent, comment, 
            deriv, deriv_json, pst, 
            mrs, mrs_json, dmrs_json) 
            VALUES (?,?,?,?,?,?,?,?,?,?)""", g)
        except sqlite3.Error as e:
            log.write(f'ERROR:   ({e}) of type ({type(e).__name__}), {g[0]} {g[1]}\n')
    conn.commit()

def sent2db(conn, sent, log):
    c = conn.cursor()
    for p,s in sent:
        for i, (w, l) in enumerate(sent[(p,s)]):
            try:
                c.execute("""INSERT INTO sent (profile, sid, wid, word, lexid) 
                VALUES (?,?,?,?,?)""", (p, s, i, w, l))
            except sqlite3.Error as e:
                log.write(f'ERROR:   ({e}) of type ({type(e).__name__}), {p} {s}\n')
    conn.commit()

def nodes2db(conn, lexind, typind, log):
    c = conn.cursor()
                    
    for l in  lexind:
        for p,s in lexind[l]:
            for (k, m) in lexind[l][(p, s)]:
                try:
                    c.execute("""INSERT INTO lexind (lexid, profile, sid, kara, made) 
                    VALUES (?,?,?,?,?)""", (l, p, s, k, m))
                except sqlite3.Error as e:
                    log.write(f'ERROR:   ({e}) of type ({type(e).__name__}), {p} {s}\n')

    for t in  typind:
        for p,s in typind[t]:
            for (k, m) in typind[t][(p, s)]:
                try:
                    c.execute("""INSERT INTO typind (typ, profile, sid, kara, made) 
                    VALUES (?,?,?,?,?)""", (t, p, s, k, m))
                except sqlite3.Error as e:
                    log.write(f'ERROR:   ({e}) of type ({type(e).__name__}), {p} {s}\n')
                    
    conn.commit()

    
def process_tsdb(conn, ver, golddir, log):
    """
    look at all the trees in the golddir
    process those with the same version cfg['ver']
    """
    for root, dirs, files in os.walk(golddir):
        if ('result' in files or 'result.gz' in files):
            if ver_match(ver, root, log):
                print(f"Processing {root}", file=sys.stderr)
                gold, sent, lexind, typind = process_results(root, log)
                #print(gold[0], gold[-1])
                gold2db(conn, gold, log)
                sent2db(conn, sent, log)
                nodes2db(conn, lexind, typind, log)

#process_tsdb('ERG-dict (2020)', '/home/bond/tmp/2020-for-ltdb/tsdb/gold/omw', log)
#process_tsdb('ERG-dict (2020)', '/home/bond/tmp/2020-for-ltdb/tsdb/gold/ntucle', log)
#process_tsdb('ERG-dict (2020)', '/home/bond/tmp/2020-for-ltdb/tsdb/gold/sh-spec', log)
