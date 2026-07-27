import multiprocessing as mp
import os
import re
import sqlite3
import sys
from collections import defaultdict as dd

from delphin import itsdb, tsdb
from delphin.codecs import simplemrs


def cpu_jobs():
    """Return a job count sized to available CPUs.

    Unlike ACE parsing (default_jobs() in parse_examples.py), this work
    is pure Python with no per-worker external-process memory to budget
    for, so plain CPU count is the only input.
    """
    return max(1, os.cpu_count() or 1)


def extract_span(terminal):
    """
    Try to get the start and end of the construction.

    A terminal's tokens span the whole surface expression, which may
    cover more than one input token for a multiword lexical entry (e.g.
    "or what"); take the earliest FROM and latest TO across all of them
    rather than just the first token's span.
    """
    if not terminal.tokens:
        return None
    from_value = to_value = None
    for _, str_tok in terminal.tokens:
        from_match = re.search(r'\+FROM\s+\\"(\d+)\\"', str_tok)
        to_match = re.search(r'\+TO\s+\\"(\d+)\\"', str_tok)
        if from_match:
            v = int(from_match.group(1))
            from_value = v if from_value is None else min(from_value, v)
        if to_match:
            v = int(to_match.group(1))
            to_value = v if to_value is None else max(to_value, v)

    if from_value is not None and to_value is not None:
        return from_value, to_value
    else:
        return None


def get_surface_form(terminal, surf_str):
    span = extract_span(terminal)
    if span:
        return surf_str[span[0] : span[1]]
    else:
        return terminal.form


def align_span(surf, sentence, cursor):
    """Find `surf` in `sentence` at or after `cursor`, for grammars whose
    tokens carry no +FROM/+TO (extract_span returns None) -- e.g. older
    LKB-sourced grammars, which have no character-offset data at all.

    A plain, monotonic left-to-right search: since words are processed
    in sentence order, advancing the cursor past each match (rather
    than searching from 0 every time) is what correctly finds the
    *next* occurrence of a repeated word instead of always the first.
    Tries an exact match first, falling back to case-insensitive (a
    terminal's surface form is sometimes citation-cased, e.g.
    lowercased, differently than how it appears in the raw sentence).

    Returns (cfrom, cto, new_cursor), or None if `surf` isn't found
    from `cursor` onward at all -- a mismatch between the tokenization
    and the raw sentence text, in which case the caller should treat
    the span as unavailable for this word, same as extract_span's own
    None.
    """
    idx = sentence.find(surf, cursor)
    if idx == -1:
        idx = sentence.lower().find(surf.lower(), cursor)
    if idx == -1:
        return None
    end = idx + len(surf)
    return idx, end, end


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


def process_results(root):
    """Process one treebank profile, returning its rows and any log lines.

    Runs standalone (no shared file handle) so it can be dispatched to a
    worker process by process_tsdb(); the caller is responsible for
    writing the returned log_lines to the shared log afterwards.  The
    returned lexind/typind/sent are converted to plain dict/list
    structures (rather than defaultdicts with lambda factories) because
    lambdas cannot be pickled across a process boundary.
    """
    lexind = dd(lambda: dd(set))  # lexind[type][(profile, sid)]((frm, to), ...)
    typind = dd(lambda: dd(set))  # typind[type][(profile, sid)]((frm, to), ...)
    sent = dd(list)  # sent[(profile, sid)][(surf, lexid, cfrom, cto)]
    gold = list()
    log_lines = []

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
                log_lines.append("\n\nMRS couldn't be retrieved in pydelphin:\n")
                log_lines.append(f"{root}: {profile} {sid} {e}\n")
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
                # cursor: rightmost char position matched so far in this
                # sentence, so align_span's fallback finds the *next*
                # occurrence of a repeated word rather than always the first
                cursor = 0
                for preterminal, terminal in zip(
                    deriv.preterminals(), deriv.terminals()
                ):
                    lexid = preterminal.entity
                    surf = get_surface_form(terminal, response["i-input"])
                    start = preterminal.start
                    end = preterminal.end
                    span = extract_span(terminal)
                    if span:
                        cfrom, cto = span
                        cursor = max(cursor, cto)
                    else:
                        aligned = align_span(surf, response["i-input"], cursor)
                        if aligned:
                            cfrom, cto, cursor = aligned
                        else:
                            cfrom = cto = None
                    sent[(profile, sid)].append((surf, lexid, cfrom, cto))
                    lexind[lexid][(profile, sid)].add((start, end))
                ### internal node (store as type)
                for node in deriv.internals():
                    typ = node.entity
                    start = node.start
                    end = node.end
                    typind[typ][(profile, sid)].add((start, end))
    lexind = {lexid: dict(spans) for lexid, spans in lexind.items()}
    typind = {typ: dict(spans) for typ, spans in typind.items()}
    return gold, dict(sent), lexind, typind, log_lines


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
        for i, (w, lexid, cfrom, cto) in enumerate(sent[(p, s)]):
            try:
                c.execute(
                    """INSERT INTO sent (profile, sid, wid, word, lexid, cfrom, cto)
                VALUES (?,?,?,?,?,?,?)""",
                    (p, s, i, w, lexid, cfrom, cto),
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


def process_tsdb(conn, ver, checkgrm, golddir, log, profiles, jobs=1):
    """
    look at all the trees in the golddir
    process those with the same version cfg['ver']

    Profiles are independent treebank directories, so once the eligible
    ones are found (a cheap scan), process_results() over each can run
    in a worker pool; the sqlite writes stay on the main process
    afterwards, since a single Connection cannot be shared across
    processes.
    """
    roots = []
    for root, dirs, files in os.walk(golddir):
        if "result" in files or "result.gz" in files:
            if profiles is not None:
                profile = root.split("/")[-1]
                if profile not in profiles:
                    continue

            ##print (root, dirs, files)
            if (not checkgrm) or ver_match(ver, root, log):
                roots.append(root)

    n_workers = min(jobs, len(roots)) if roots else 1
    if n_workers > 1:
        print(
            f"Processing {len(roots)} profiles with {n_workers} processes",
            file=sys.stderr,
        )
        with mp.Pool(n_workers) as pool:
            results = pool.map(process_results, roots)
    else:
        results = []
        for root in roots:
            print(f"Processing {root}", file=sys.stderr)
            results.append(process_results(root))

    for gold, sent, lexind, typind, log_lines in results:
        log.writelines(log_lines)
        gold2db(conn, gold, log)
        sent2db(conn, sent, log)
        nodes2db(conn, lexind, typind, log)
