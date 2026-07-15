import os
import re
import sqlite3
import sys
from collections import defaultdict as dd

from delphin import itsdb, tsdb
from delphin.codecs import simplemrs


def extract_span(terminal):
    """
    Try to get the start and end of the construction
    """
    if not terminal.tokens:
        return None
    str_tok = terminal.tokens[0][1]
    from_match = re.search(r'\+FROM\s+\\"(\d+)\\"', str_tok)
    to_match = re.search(r'\+TO\s+\\"(\d+)\\"', str_tok)

    if from_match and to_match:
        from_value = int(from_match.group(1))
        to_value = int(to_match.group(1))
        return from_value, to_value
    else:
        return None


def get_surface_form(terminal, surf_str):
    span = extract_span(terminal)
    if span:
        return surf_str[span[0] : span[1]]
    else:
        return terminal.form


def ver_match(ver, profile, log):
    """
    returns True iff the version matches the runs
    """
    grms = set(tsdb.split(line)[7] for line in tsdb.open(profile, "run"))
    if len(grms) == 1:
        rungrm = grms.pop()
        if rungrm == ver:
            return True
        else:
            print(f"Grammar in treebank '{rungrm}' != '{ver}'", file=log)
            return False

    elif len(grms) > 1:
        print(
            f"Warning: two different grammars used in this profile {profile}",
            file=sys.stderr,
        )
        return False
    elif len(grms) == 0:
        print(
            f"Warning: no grammar indicated in this profile {profile}", file=sys.stderr
        )
        return False


def process_results(root, log):
    lexind = dd(lambda: dd(set))  # lexind[type][(profile, sid)]((frm, to), ...)
    typind = dd(lambda: dd(set))  # typind[type][(profile, sid)]((frm, to), ...)
    sent = dd(list)  # sent[(profile, sid)][(surf, lexid)]
    gold = list()

    ts = itsdb.TestSuite(root)
    for response in ts.processed_items():
        sid = response["i-id"]
        profile = ts.path.name
        if response["results"]:
            first_result = response.result(0)
            deriv = first_result.derivation()
            tree = first_result.get("tree", "")
            deriv_str = deriv.to_udf(indent=None)
            try:
                mrs_obj = first_result.mrs()
                mrs_str = simplemrs.encode(mrs_obj, indent=True)
            except Exception as e:
                log.write("\n\nMRS couldn't be retrieved in pydelphin:\n")
                log.write(f"{root}: {profile} {sid} {e}\n")
                mrs_str = ""
            gold.append(
                (
                    profile,
                    sid,
                    response["i-input"],
                    response["i-comment"],
                    deriv_str,
                    tree,
                    mrs_str,
                )
            )
            ### get the nodes
            if deriv:
                for preterminal, terminal in zip(
                    deriv.preterminals(), deriv.terminals()
                ):
                    lexid = preterminal.entity
                    surf = get_surface_form(terminal, response["i-input"])
                    start = preterminal.start
                    end = preterminal.end
                    ### get cfrom cto
                    sent[(profile, sid)].append((surf, lexid))
                    lexind[lexid][(profile, sid)].add((start, end))
                ### internal node (store as type)
                for node in deriv.internals():
                    typ = node.entity
                    start = node.start
                    end = node.end
                    typind[typ][(profile, sid)].add((start, end))
    return gold, sent, lexind, typind


def gold2db(conn, gold, log):
    c = conn.cursor()
    for g in gold:
        try:
            c.execute(
                """INSERT INTO gold (profile, sid, sent, comment, deriv, pst, mrs)
            VALUES (?,?,?,?,?,?,?)""",
                g,
            )
        except sqlite3.Error as e:
            log.write(f"ERROR:   ({e}) of type ({type(e).__name__}), {g[0]} {g[1]}\n")
    conn.commit()


def sent2db(conn, sent, log):
    c = conn.cursor()
    for p, s in sent:
        for i, (w, lexid) in enumerate(sent[(p, s)]):
            try:
                c.execute(
                    """INSERT INTO sent (profile, sid, wid, word, lexid)
                VALUES (?,?,?,?,?)""",
                    (p, s, i, w, lexid),
                )
            except sqlite3.Error as e:
                log.write(f"ERROR:   ({e}) of type ({type(e).__name__}), {p} {s}\n")
    conn.commit()


def nodes2db(conn, lexind, typind, log):
    c = conn.cursor()

    for lexid in lexind:
        for p, s in lexind[lexid]:
            for k, m in lexind[lexid][(p, s)]:
                try:
                    c.execute(
                        """INSERT INTO lexind (lexid, profile, sid, kara, made)
                    VALUES (?,?,?,?,?)""",
                        (lexid, p, s, k, m),
                    )
                except sqlite3.Error as e:
                    log.write(f"ERROR:   ({e}) of type ({type(e).__name__}), {p} {s}\n")

    for t in typind:
        for p, s in typind[t]:
            for k, m in typind[t][(p, s)]:
                try:
                    c.execute(
                        """INSERT INTO typind (typ, profile, sid, kara, made) 
                    VALUES (?,?,?,?,?)""",
                        (t, p, s, k, m),
                    )
                except sqlite3.Error as e:
                    log.write(f"ERROR:   ({e}) of type ({type(e).__name__}), {p} {s}\n")

    conn.commit()


def process_tsdb(conn, ver, checkgrm, golddir, log, profiles):
    """
    look at all the trees in the golddir
    process those with the same version cfg['ver']
    """
    for root, dirs, files in os.walk(golddir):
        if "result" in files or "result.gz" in files:
            if profiles is not None:
                profile = root.split("/")[-1]
                if profile not in profiles:
                    continue

            ##print (root, dirs, files)
            if (not checkgrm) or ver_match(ver, root, log):
                print(f"Processing {root}", file=sys.stderr)
                gold, sent, lexind, typind = process_results(root, log)
                # print(gold[0], gold[-1])
                gold2db(conn, gold, log)
                sent2db(conn, sent, log)
                nodes2db(conn, lexind, typind, log)
