###
### Make a database for a grammar, based on the METADATA file
###
import sys, os
import re
import shutil
import argparse
import tempfile
import sqlite3
import toml
import json
from pathlib import Path

from tdl2db import read_cfg, read_grm, intodb
from gold2db import process_tsdb

if sys.version_info < (3, 8):
    sys.exit(f"Python 3.8+ required, got {sys.version}")


def read_metadata(metadata_path):
    md = dict()
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            md = toml.load(f)
    except FileNotFoundError:
        print(f"METADATA not found at {metadata_path}", file=sys.stderr)
    return md

def make_db (dbdir, db):
    conn = sqlite3.connect(os.path.join(dbdir, db))    # loads dbfile as con
    c = conn.cursor()
    
    # Get the script directory to find tables.sql
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_path = os.path.join(script_dir, 'tables.sql')
    
    with open(sql_path, 'r') as sql_file:
        sql_script = sql_file.read()
    c.executescript(sql_script)
    conn.commit()
    return conn

def meta_to_db(conn, md):
    c = conn.cursor()
    for att, val in md.items():
        if isinstance(val, list):
            # Wrap the list in a dictionary with a standard key
            # as TOML requires key-value pairs at the top level
            val = json.dumps(val)
        if att and val:
            c.execute("""
            INSERT INTO meta (att, val)
            VALUES (?, ?)""", (att, val)) 
    conn.commit()     


def post_process_corpus(conn):
    print("Post-processing database", file=sys.stderr)
    c = conn.cursor()

    ### index lexical types
    c.execute("""
INSERT INTO typind (typ, profile, sid, kara, made) 
  SELECT typ, profile, sid, kara, made 
  FROM lex JOIN lexind ON lex.lexid = lexind.lexid""")

    ### store lexid frequencies
    c.execute("""
INSERT INTO lexfreq (lexid, word, freq)  
  SELECT lexid, word, count(lexid)     
  FROM sent GROUP BY lexid, word""")

    ### store type frequencies
    c.execute("""
INSERT INTO typfreq (typ, freq)  
  SELECT typ, count(typ)     
  FROM typind GROUP BY typ""")

    
    conn.commit()




def find_ace(ace_bin=None):
    """Locate the ACE binary.

    Checks, in order: the supplied path, the system PATH, then any
    ace-* subdirectory inside the 'etc/' folder next to this script.

    Args:
        ace_bin: Explicit path supplied by the user, or None.

    Returns:
        Path to a usable ACE binary.

    Raises:
        FileNotFoundError: If no ACE binary can be found.
    """
    if ace_bin:
        p = Path(ace_bin)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        raise FileNotFoundError(f"ACE binary not found or not executable: {ace_bin}")

    # Try system PATH first
    found = shutil.which("ace")
    if found:
        return found

    # Fall back to etc/ace-*/ beside the scripts directory
    etc_dir = Path(__file__).parent.parent / "etc"
    for candidate in sorted(etc_dir.glob("ace-*/ace"), reverse=True):
        if os.access(candidate, os.X_OK):
            return str(candidate)

    raise FileNotFoundError(
        "ACE binary not found. Install it and put it on PATH, or pass --ace-bin."
    )


_ANSI_ESCAPE = re.compile(r'\x1B\[[0-9;]*m')


def compile_ace(cfg_path, out_path, log_path, ace_bin=None):
    """Compile a grammar with ACE, writing output to a .dat file.

    Args:
        cfg_path: Path to the ACE config (.tdl) file.
        out_path: Destination path for the compiled grammar (.dat).
        log_path: Path for the compilation log.
        ace_bin: Path to the ACE binary, or None to auto-discover.
    """
    from delphin import ace

    binary = find_ace(ace_bin)
    print(f"Compiling ACE grammar: {cfg_path} -> {out_path}", file=sys.stderr)
    print(f"Using ACE binary: {binary}", file=sys.stderr)

    with open(log_path, 'w') as log:
        log.write(f"# ace -g {cfg_path} -G {out_path}\n\n")

    try:
        # stderr must be a real file with a fileno(); strip ANSI codes after
        with open(log_path, 'ab') as raw:
            ace.compile(cfg_path, out_path, executable=binary, stderr=raw)

        # Post-process: strip ANSI escape codes in place
        text = Path(log_path).read_text(errors='replace')
        Path(log_path).write_text(_ANSI_ESCAPE.sub('', text))

        with open(log_path, 'a') as log:
            log.write("\n# Compilation successful\n")
        print(f"ACE compilation succeeded: {out_path}", file=sys.stderr)
    except Exception as e:
        with open(log_path, 'a') as log:
            log.write(f"\n# Compilation failed: {e}\n")
        print(f"ACE compilation failed: {e}", file=sys.stderr)
        raise


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
                    prog = 'grm2db',
                    description = 'Take a delphin grammar and make a db from it and its corpora',
                    epilog = 'Text at the bottom of help')
    parser.add_argument('--checkgrm', action='store_true',
                        help='Check the grammar version in the treebank')
    parser.add_argument('--outdir', type=Path,
                        help="Output directory for the database")
    parser.add_argument('--ace', action='store_true',
                        help="Compile the grammar with ACE, producing a .dat file")
    parser.add_argument('--ace-bin', type=Path, metavar='PATH',
                        help="Path to the ACE binary (default: search PATH then etc/ace-*/ace)")
    parser.add_argument('metadata', type=Path,
                        help="METADATA file for the grammar")

    args = parser.parse_args()

    
    ###
    ### Read Metadata
    ###
    md = read_metadata(args.metadata)
    if not md:
        sys.exit("No usable metadata, giving up")

    out_dir = args.outdir or tempfile.mkdtemp()
    os.makedirs(out_dir, exist_ok=True)

    nam = md.get('SHORT_GRAMMAR_NAME', 'unknown')
    
    print(f"Making the db for {nam} in {out_dir}")
    
    cfg = read_cfg(os.path.join(os.path.dirname(args.metadata),
                                md['ACE_CONFIG_FILE']))

    md['Version'] = cfg['ver'] 

    dbname = f"{cfg['ver'].replace(' ', '_')}.db"
    conn = make_db(out_dir, dbname)
    meta_to_db(conn, md)

    log_path = os.path.join(out_dir, f"{md['Version']}-tdl.log")
    with open(log_path, 'w') as log:
        tdls, types, hierarchy, les = read_grm(cfg, log)
        intodb(conn, tdls, types, hierarchy, les)

        tsdb_roots = md.get('TSDB_ROOTS', ['tsdb/gold/'])
        profiles = md.get('PROFILES', None)
        for root in tsdb_roots:
            golddir = os.path.normpath(
                os.path.join(os.path.dirname(args.metadata), root))
            print(f'Processing profiles under {golddir}')
            if profiles is not None:
                print(f'If they are in {profiles}')
            if os.path.isdir(golddir):
                process_tsdb(conn, cfg['ver'], args.checkgrm,
                             golddir, log, profiles)

    post_process_corpus(conn)

    print(f"Made {out_dir}/{dbname} for {nam}")

    if args.ace:
        stem = dbname[:-3]
        dat_path = os.path.join(out_dir, stem + '.dat')
        ace_log_path = os.path.join(out_dir, stem + '-ace.log')
        cfg_path = os.path.join(os.path.dirname(args.metadata), md['ACE_CONFIG_FILE'])
        compile_ace(cfg_path, dat_path, ace_log_path, ace_bin=args.ace_bin)
        print(f"Made {dat_path} for {nam}")
