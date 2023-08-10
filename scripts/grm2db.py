###
### Make a database for a grammar, based on the METADATA file
###
import sys, os
import argparse
import tempfile
import sqlite3

from pathlib import Path

from tdl2db import read_cfg, read_grm, intodb
from gold2db import process_tsdb

### check we have a new enough version
if not sys.version_info > (3, 8):
    print(f"you must use Python newer than 3.7 not {sys.version}")


def read_metadata(metadata_path):
    md = dict()
    try:
        fh = open(metadata_path, 'r')
    # Store configuration file values
        for l in fh:  
            if l.strip() and l[0].isupper():
                (att,val) = l.strip().split('=')
                val=val.strip('"')
                if val:
                    md[att]=val
    except FileNotFoundError:
        print("METADATA not found at {}".format(MF),file=sys.stderr)
    return md

def make_db (dbdir, db):
    conn = sqlite3.connect(os.path.join(dbdir, db))    # loads dbfile as con
    c = conn.cursor()
    with open('tables.sql', 'r') as sql_file:
        sql_script = sql_file.read()
    c.executescript(sql_script)
    conn.commit()
    return conn

def meta_to_db(conn, md):
    c = conn.cursor()
    for att, val in md.items():
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
    parser.add_argument('metadata', type=Path,
                        help="METADATA file for the grammar")

    args = parser.parse_args()

    ###
    ### Read Metadata
    ###

    md = read_metadata(args.metadata)
    #print(md)

    temp_dir = tempfile.mkdtemp()
    
    print(f"Making the db for {md['SHORT_GRAMMAR_NAME']} in {temp_dir}")

    log = open(os.path.join(temp_dir, "tdl.log"), 'w')
    
    cfg = read_cfg(os.path.join(os.path.dirname(args.metadata),
                                md['ACE_CONFIG_FILE']))

    md['Version'] = cfg['ver'] 
    ###
    ### read the info from the tdl
    ###
    tdls, types, hierarchy, les = read_grm(cfg, log)

    #print(tdls, types, hierarchy, les)
    ###
    ### make the db
    ###
    dbname=f"{cfg['ver'].replace(' ', '_')}.db"
    conn = make_db(temp_dir, dbname)

    ## add the information to the database
    
    meta_to_db(conn, md)
   
    intodb(conn, tdls, types, hierarchy, les)

    ###
    ### add the info from gold
    ###
    
    golddir =  os.path.normpath(os.path.join(os.path.dirname(cfg['grammar_file']),
                                             'tsdb/gold/'))
    if os.path.isdir(golddir):
        process_tsdb(conn, cfg['ver'], golddir, log)


    post_process_corpus(conn)

    log.close()

    print(f"Made {temp_dir}/{dbname} for {md['SHORT_GRAMMAR_NAME']}")
