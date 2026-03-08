# Linguistic Type Data-Base (ltdb)

The Linguistic Type Database (LTDB, née Lextype DB), describes types and
rules of a DELPH-IN grammar with frequency information from the
treebank. Lexical types can be seen as detailed parts-of-speech.
Information about the types are constructed from the linguists
documentation in the grammar, a kind of literate programming.

## Quick Start

A separate database is made for each grammar.  The description for the grammar is read from the METADATA, a single project may have multiple grammars.

Compile a database with:

```
$ python scripts/grm2db.py path/to/METADATA
```

--checkgrm only includes treebanks made by the same version
--outdir specifies the output directory 
         a temporary directory will be made otherwise

If all goes well, copy the database to web/db/.

The grammars are read by a web application written using Flask.
See [Install.md](Install.md) for deployment instructions.

There is `more documentation <http://moin.delph-in.net/LkbLtdb>`__ at
the DELPH-IN Wiki.

Types, instances in the same table, distinguished by status.


+----------+------------------------------------+-------------------+------+
|status    |thing                               | source            |  end |
+==========+====================================+===================+======+
|type      |normal type                         |                   |      |
+----------+------------------------------------+-------------------+------+
|lex-type  |lexical type                        |type + in lexicon  | _lt  |
+----------+------------------------------------+-------------------+------+
|lex-entry |lexical entry                       |                   | _le  |   
+----------+------------------------------------+-------------------+------+
|rule      |syntactic construction/grammar rule | LKB:\*RULES       | _c   |
+----------+------------------------------------+-------------------+------+
|lex-rule  | lexical rule                       | LKB:\*LRULES      | lr   |
+----------+------------------------------------+-------------------+------+
|inf-rule  |inflectional rule                   | LKB:\*LRULES +    | ilr  | 
+----------+------------------------------------+-------------------+------+
|          |            (inflectional-rule-pid )|                   |      |
+----------+------------------------------------+-------------------+------+
|          |orth-invariant inflectional rule    |                   | _ilr |
+----------+------------------------------------+-------------------+------+
|          |orth-changing inflectional rule     |                   | _olr |
+----------+------------------------------------+-------------------+------+
|          |orth-invariant derivational rule    |                   | _dlr | 
+----------+------------------------------------+-------------------+------+
|          |orth-changing derivation rule       |                   |_odlr |
+----------+------------------------------------+-------------------+------+
|          |punctuation affixation rule         |                   | _plr |
+----------+------------------------------------+-------------------+------+
|root      |root                                |                   |      |
+----------+------------------------------------+-------------------+------+


+--------+--------------------------------------+
| Symbol | Explanation                          |
+========+======================================+
|  ▲     | Unary, Headed                        |
+--------+--------------------------------------+
|  △	 | Unary, Non-Headed                    |
+--------+--------------------------------------+
|  ◭    | Binary, Left-Headed                  |
+--------+--------------------------------------+
|  ◮    | Binary, Right-Headed                 |
+--------+--------------------------------------+
|  ◬    | Binary, Non-Headed                   |
+--------+--------------------------------------+
