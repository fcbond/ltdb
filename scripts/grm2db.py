###
### Make a database for a grammar, based on the METADATA file
###
import sys, os
import argparse
import tempfile
import sqlite3
import toml
import json
from pathlib import Path

from tdl2db import read_cfg, read_grm, intodb
from gold2db import process_tsdb

### check we have a new enough version
if not sys.version_info > (3, 8):
    print(f"you must use Python newer than 3.7 not {sys.version}")


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




if __name__ == '__main__':

    parser = argparse.ArgumentParser(
                    prog = 'grm2db',
                    description = 'Take a delphin grammar and make a db from it and its corpora',
                    epilog = 'Text at the bottom of help')
    parser.add_argument('--checkgrm',  action='store_true',
                        help='Check the grammar version in the treebank')
    parser.add_argument('--outdir', type=Path,
                        help="Output directory for the database")
    parser.add_argument('metadata', type=Path,
                        help="METADATA file for the grammar")

    args = parser.parse_args()

    
    ###
    ### Read Metadata
    ###
    md = read_metadata(args.metadata)
    print(md)
    if not md:
        sys.exit("No usable metadata, giving up"),

    out_dir = args.outdir or tempfile.mkdtemp()
    os.makedirs(out_dir, exist_ok=True)

    nam = md['SHORT_GRAMMAR_NAME'] or 'unknown'
    
    print(f"Making the db for {nam} in {out_dir}")
    
    cfg = read_cfg(os.path.join(os.path.dirname(args.metadata),
                                md['ACE_CONFIG_FILE']))

    md['Version'] = cfg['ver'] 

    log = open(os.path.join(out_dir, f"{md['Version']}-tdl.log"), 'w')
    ###
    ### read the info from the tdl
    ###
    tdls, types, hierarchy, les = read_grm(cfg, log)

    #print(tdls, types, hierarchy, les)
    ###
    ### make the db
    ###
    dbname=f"{cfg['ver'].replace(' ', '_')}.db"
    conn = make_db(out_dir, dbname)

    ## add the information to the database
    
    meta_to_db(conn, md)
   
    intodb(conn, tdls, types, hierarchy, les)

    ###
    ### add the info from gold
    ###


    tsdb_roots = md.get('TSDB_ROOTS',  [ 'tsdb/gold/' ])
    profiles = md.get('PROFILES',  None)
    for root in tsdb_roots:
        golddir =  os.path.normpath(os.path.join(os.path.dirname(args.metadata),
                                                 root))
        print(f'Processing profiles under {golddir}')
        if profiles is not None:
            print(f'If they are in {profiles}')
        if os.path.isdir(golddir):
            process_tsdb(conn, cfg['ver'], args.checkgrm,
                         golddir, log, profiles)


    post_process_corpus(conn)

    log.close()

    print(f"Made {out_dir}/{dbname} for {md['SHORT_GRAMMAR_NAME']}")
