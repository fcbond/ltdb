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
-- preprocess this
CREATE TABLE ltypes (typ TEXT primary key,
		     words TEXT,
		     lfreq INTEGER default 0,
		     cfreq INTEGER DEFAULT 0);
-- sentences in the database (assumes unique profile+sid)
CREATE TABLE sent (sid INTEGER,
                   profile TEXT,
		   wid INTEGER,
		   word TEXT,
		   lexid TEXT);
-- Information from the gold profiles
CREATE TABLE gold (sid INTEGER primary key,
       	     	   profile TEXT,				
       	     	   sent TEXT,
		   comment TEXT,
		   deriv TEXT,
		   deriv_json TEXT,
		   pst TEXT,
		   mrs TEXT,
		   mrs_json TEXT,
		   dmrs_json TEXT,
		   flags TEXT);
CREATE TABLE typind (typ TEXT,
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
