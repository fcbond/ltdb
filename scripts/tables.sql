-- Information about the types (from the .tdl and docstring)
CREATE TABLE types (typ TEXT primary key,
		   parents TEXT,
		   children TEXT, 
		   cat TEXT,
		   val TEXT,
		   cont TEXT,
		   definition TEXT,
                   status TEXT,
		   arity INTEGER,
		   head INTEGER,
		   -- from the docstring
                   lname TEXT,
		   description TEXT,
		   criteria TEXT,
		   reference TEXT,
		   todo TEXT);
-- Information about the lexicon
CREATE TABLE lex (lexid TEXT primary key,
		  typ TEXT,
		  orth TEXT,
		  pred TEXT,
		  altpred TEXT,
		  carg TEXT,
		  altcarg TEXT,
		  docstring TEXT);
-- words in the database (assumes unique profile+sid+wid)
-- each sentence has words and their lexical ids, ordered by wid
CREATE TABLE sent (sid INTEGER,
                   profile TEXT,
		   wid INTEGER,
		   word TEXT,
		   lexid TEXT,
		   UNIQUE(profile, sid, wid) );
-- Information from the gold profiles; JSON is built on the fly from deriv/mrs
CREATE TABLE gold (sid INTEGER,
       	     	   profile TEXT,
       	     	   sent TEXT,
		   comment TEXT,
		   deriv TEXT,
		   pst TEXT,
		   mrs TEXT,
		   flags TEXT,
		   UNIQUE(profile, sid) );
CREATE TABLE typind (typ TEXT,
       	     	     profile TEXT,	    
                     sid INTEGER,
		     kara INTEGER,
                     made INTEGER);
CREATE TABLE lexind (lexid TEXT,
       	     	     profile TEXT,	    
                     sid INTEGER,
		     kara INTEGER,
                     made INTEGER);
CREATE TABLE typfreq(typ TEXT, 
                     freq INTEGER DEFAULT 0);
CREATE TABLE lexfreq(lexid TEXT, 
                     word TEXT, 
                     freq INTEGER DEFAULT 0);
-- TDL extracted by PyDelphin
CREATE TABLE tdl (typ TEXT,
       	     	  src TEXT,
		  line INTEGER,
		  kind TEXT,
                  tdl TEXT,
		  docstring TEXT);
-- Hierarchy extracted by PyDelphin		 
CREATE TABLE hie (child TEXT,
                  parent TEXT);
-- Metadata (from METADATA
CREATE TABLE meta (att TEXT,
                   val TEXT);
-- Docstring example test results (populated by parse_examples.py)
-- One row per (type, sentence) pair.
CREATE TABLE doctest (
    typ     TEXT NOT NULL,    -- type whose docstring contains this example
    sent    TEXT NOT NULL,    -- example sentence text
    kind    TEXT NOT NULL,    -- 'ex' | 'nex' | 'mex'
    wf      INTEGER NOT NULL, -- 1=grammatical/marginal, 0=ungrammatical (i-wf)
    n_parses   INTEGER,       -- number of ACE parse results (NULL = not yet run)
    type_found INTEGER,       -- 1=type appeared in any derivation, 0=did not
    pass    INTEGER NOT NULL, -- 1=PASS, 0=FAIL
    verdict TEXT NOT NULL     -- 'PASS' | 'FAIL-no-parse' | 'FAIL-type-absent' | 'FAIL-type-in-tree'
);
CREATE INDEX idx_lex_typ ON lex(typ);
CREATE INDEX idx_sent_lexid ON sent(lexid);
CREATE INDEX idx_typind_typ ON typind(typ);
CREATE INDEX idx_lexind_lexid ON lexind(lexid);
CREATE INDEX idx_doctest_typ ON doctest(typ);
