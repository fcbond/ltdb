##
## takes two paramaters -- tdl grammarfile and database
##
import os
import re
import sys
from collections import defaultdict as dd
from pathlib import Path

from delphin import tdl


def read_cfg(ace_config):
    """
    read the config file, find the grammar, version and path to orthography
    """
    cfg = dict()
    with open(ace_config) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(";"):
                continue
            for attr in ["version", "grammar-top", "orth-path", "generation-roots"]:
                match = re.findall(rf'{attr}\s+:=\s+"?([^"]+)"?.', line)
                if match:
                    cfg[attr] = match[0]
    if "orth-path" in cfg:
        # ACE config paths use whitespace to separate feature path segments
        # (e.g. "MORPH LIST FIRST STEM"), but Conjunction.get() expects
        # dot-separated paths (e.g. "MORPH.LIST.FIRST.STEM")
        cfg["orth-path"] = ".".join(cfg["orth-path"].split())
    cfg["grammar_file"] = os.path.normpath(
        os.path.join(os.path.dirname(ace_config), cfg["grammar-top"])
    )
    with open(os.path.join(os.path.dirname(ace_config), cfg["version"])) as fh:
        for line in fh:
            match = re.findall(r'\*grammar-version\*\s+"([^"]+)"', line.strip())
            if match:
                cfg["ver"] = match[0]
                break
    if "ver" not in cfg:
        sys.exit(
            f"Could not find *grammar-version* in {cfg['version']}; "
            "check your ACE config file"
        )
    return cfg


def read_grm(cfg, log):
    tdls = []
    types = dd(list)
    les = {}
    hierarchy = []
    grammarfile = cfg["grammar_file"]
    path = Path(grammarfile)
    base = path.parent
    # a bare top-level ":include" (not wrapped in a :begin/:end block)
    # implicitly belongs to the "type" environment per the TDL spec
    return process_type(cfg, str(base), str(path), "type", tdls, types, hierarchy, les, log)


def _safe_format(obj, path, log):
    try:
        return tdl.format(obj)
    except Exception as e:
        print(f"Warning: could not format {obj.identifier} in {path}: {e}", file=log)
        return ""


def _safe_get(conjunction, key, default=None):
    """Like Conjunction.get, but tolerates paths that bottom out early.

    Conjunction.get() only catches KeyError; if an intermediate feature
    holds a leaf value (e.g. a grammar where KEYREL is itself the pred
    string, rather than an AVM with a PRED sub-feature, as in GG) trying
    to descend further raises TypeError instead. Treat that the same as
    "not found".
    """
    try:
        return conjunction.get(key, default=default)
    except TypeError:
        return default


def process_type(cfg, base, path, status, tdls, types, hierarchy, les, log, seen=None):
    """Recursively process a TDL file and any files it :include's.

    ``status`` is the environment status (e.g. "type", "instance",
    "lex-entry") in effect for ``path`` itself; a nested :include found
    inside an explicit :begin/:end block uses that block's own status,
    while a bare :include outside any block inherits ``status`` from its
    enclosing file.
    """
    if seen is None:
        seen = set()
    real_path = os.path.realpath(path)
    if real_path in seen:
        return tdls, types, hierarchy, les
    seen.add(real_path)

    filename = os.path.basename(path)
    if "root" in filename:
        status = "root"
    elif "parse-nodes" in filename:
        status = "labels"

    def include(entry, inc_status):
        nonlocal tdls, types, hierarchy, les
        inc_path = entry.path.with_suffix(".tdl")
        if inc_path.is_file():
            try:
                tdls, types, hierarchy, les = process_type(
                    cfg,
                    base,
                    str(inc_path),
                    inc_status,
                    tdls,
                    types,
                    hierarchy,
                    les,
                    log,
                    seen,
                )
            except ValueError as e:
                print(f"Skipping {inc_path}: {e}", file=log)
                print(f"Skipping {inc_path}: {e}", file=sys.stderr)
        else:
            print("INCLUDED FILE NOT FOUND: {!s}".format(inc_path))

    print(f"Processing types in {path} as {status}", file=sys.stderr)
    try:
        current_token_lineno = None  # To track the current token's line number
        env_depth = 0  # nesting depth of :begin/:end environments
        for event, obj, lineno in tdl.iterparse(path):  # assume utf-8
            current_token_lineno = lineno  # Store the current line number
            if event == "BeginEnvironment":
                env_depth += 1
            elif event == "EndEnvironment":
                env_depth -= 1
                entry_status = getattr(obj, "status", "type")
                for entry in obj.entries:
                    if isinstance(entry, tdl.FileInclude):
                        include(entry, entry_status)
                    # other entry kinds (type/instance definitions, nested
                    # environments) are already recorded via their own
                    # inline TypeDefinition/TypeAddendum/... events fired
                    # earlier in this same iterparse pass
            elif event == "FileInclude":
                # a bare :include not inside any :begin/:end block; one
                # nested inside a block is handled above, via obj.entries
                # on that block's EndEnvironment
                if env_depth == 0:
                    include(obj, status)
            elif event in ["TypeDefinition", "TypeAddendum", "LexicalRuleDefinition"]:
                parents = [c for c in obj.conjunction.types()]
                if status == "lex-entry":
                    if len(parents) != 1:
                        print("LE has non unique parent", obj.identifier, parents)
                    else:
                        ORTH = cfg.get("orth-path", "STEM")
                        orths = obj.conjunction.get(ORTH, default=None)
                        try:
                            orth = " ".join([str(s) for s in orths.values()])
                        except Exception:
                            orth = ""
                            print("No Orthography", obj.identifier, sep="\t", file=log)
                        pred = _safe_get(obj.conjunction, "SYNSEM.LKEYS.KEYREL.PRED")
                        altpred = _safe_get(
                            obj.conjunction, "SYNSEM.LKEYS.ALTKEYREL.PRED"
                        )
                        carg = _safe_get(obj.conjunction, "SYNSEM.LKEYS.KEYREL.CARG")
                        altcarg = _safe_get(
                            obj.conjunction, "SYNSEM.LKEYS.ALTKEYREL.CARG"
                        )
                        les[obj.identifier] = (
                            str(parents[0]),
                            orth,
                            pred,
                            altpred,
                            carg,
                            altcarg,
                            obj.documentation(),
                        )
                        tdls.append(
                            (
                                obj.identifier,
                                path[len(base) :],
                                lineno,
                                event,
                                _safe_format(obj, path, log),
                                obj.documentation(),
                            )
                        )
                else:  # not a lexical entry
                    tdls.append(
                        (
                            obj.identifier,
                            path[len(base) :],
                            lineno,
                            event,
                            _safe_format(obj, path, log),
                            obj.documentation(),
                        )
                    )
                for c in parents:
                    hierarchy.append((obj.identifier, str(c)))
                if event != "TypeAddendum":
                    types[obj.identifier].append(status)
            elif event not in ["LineComment", "BlockComment"]:
                ## ToDo log properly
                print("Unknown Event", event, obj, path, lineno, sep="\t", file=log)
    except Exception as e:
        error_msg = f"Error at line {current_token_lineno} in {path}: {str(e)}"
        print(error_msg, file=sys.stderr)
        print(error_msg, file=log)
        # Optionally, re-raise the exception with the enhanced error message
        raise ValueError(error_msg) from e

    return tdls, types, hierarchy, les

    return tdls, types, hierarchy, les


def intodb(conn, tdls, types, hierarchy, les):
    c = conn.cursor()
    c.executemany(
        """INSERT INTO tdl (typ, src, line, kind, tdl, docstring)
    VALUES (?, ?, ?, ?, ?, ?)""",
        tdls,
    )

    c.executemany(
        """INSERT INTO hie (child, parent)
    VALUES (?,?)""",
        hierarchy,
    )

    parents = dd(set)
    children = dd(set)
    for ch, pa in hierarchy:
        parents[ch].add(pa)
        children[pa].add(ch)

    typs = []
    for t, s in types.items():
        typs.append((t, s[0], " ".join(parents[t]), " ".join(children[t])))

    c.executemany(
        """INSERT OR IGNORE INTO types (typ, status, parents, children)
    VALUES (?,?,?,?) """,
        typs,
    )

    ### lexical items
    litems = []
    for t in les:
        litems.append((t,) + les[t])
    c.executemany(
        """INSERT OR IGNORE INTO lex
    (lexid, typ, orth, pred, altpred, carg, altcarg, docstring)
    VALUES (?,?,?,?,?,?,?,?) """,
        litems,
    )

    ### make immediate hypernyms of lexical entries 'lex-type'
    c.execute("""UPDATE types SET status='lex-type' 
    WHERE typ IN (SELECT typ FROM lex)""")

    conn.commit()
    print("Added types to database")
