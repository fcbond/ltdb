#export PYTHONPATH=~/svn/pydelphin
# python3 tdl2db.py
##
## takes two paramaters -- directory with the tdl and database
##
## FIXME --- 
##
import sqlite3, sys, os
from delphin import tdl
import delphin
#from collections import defaultdict as dd
#from delphin import itsdb

if (len(sys.argv) < 3):
    # prints standard error msg (stderr)
    print('''You need to give two arguments, 
 tdl directory and LTDB''', file=sys.stderr)
    sys.exit(1)
else:
    (script, grmdir, dbfile) = sys.argv
    print("Adding files from %s to %s" % (grmdir, dbfile), file=sys.stderr)

conn = sqlite3.connect(dbfile)    # loads dbfile as con
c = conn.cursor()    # creates a cursor object that can perform SQL commands with c.execute("...")

### [(typ, file, lineno, tdl, docstring), ...
tdls = list()


for root, dirs, files in os.walk(grmdir):
    ### find valid profiles
    for f in files:
        if f.endswith('.tdl'):
            if 'pet' in f or 'qc' in f or 'config' in f:
                continue
            print("Processing %s" % f, file=sys.stderr)
            try:
                for event, obj, lineno in delphin.tdl.iterparse(os.path.join(root, f)): # assume utf-8
                #print(lineno, event, sep = '\t')
                    if event in ['TypeDefinition',  'TypeAddendum',
                                 'LexicalRuleDefinition']:
                        tdls.append((obj.identifier,
                                     f, lineno,
                                     tdl.format(obj),
                                     obj.docstring))
                    elif event not in ['LineComment', 'BlockComment']:
                        ## ToDo log properly
                        print('Unknown Event', event, obj, fl, lineno,
                              sep = '\t',
                        file=sys.stderr)
            except Exception as e:
                print("Unable to parse tdl for {}".format(os.path.join(root, f)),
                      file=sys.stderr)
                if hasattr(e, 'message'):
                    print(e.message)
                else:
                    print(str(e))

                
if tdls:                        
    c.executemany("""INSERT INTO tdl
                     VALUES (?,?,?,?,?)""", tdls)
    conn.commit()
