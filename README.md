# ltdb
Linguistic Type Data-Base

The Linguistic Type Database (LTDB, née Lextype DB), describes types
and rules of a DELPH-IN grammar with frequency information from the
treebank. Lexical types can be seen as detailed parts-of-speech.
Information about the types are constructed from the linguists
documentation in the grammar, a kind of literate programming.

There is [more documentation](http://moin.delph-in.net/LkbLtdb) at the DELPH-IN Wiki.


---

## Usage

1. Run `./make-ltdb.bash --grmdir /path/to/grammar`

```bash
./make-ltdb.bash --grmdir ~/logon/dfki/jacy
```

Everything is installed to `~/public_html/`

## Installation

### Requirements
```
  * Perl
  * SQLite3
  * Apache
  * LKB/Lisp		for db dump
  * xmlstarlet		for validating lisp
  * python 2.7, python 3, pydelphin, docutils

  * jquery, jquery tablesorter (patched)
``` 

We prefer that Sentence IDs are unique, if we see two sentences in the
gold treebank with the same ID, we only store the first one.


Install dependencies (in ubuntu):
```bash
sudo apt-get install apache2 xmlstarlet

sudo pip install pydelphin
sudo pip install docutils
```


### Enable local directories in Apache2:


```bash
sudo a2enmod userdir
sudo a2enmod cgi
```




Put this in /etc/apache2/sites-available/000-default.conf
```xml
<Directory /home/*/public_html/cgi-bin/>
   Options +ExecCGI
   AddHandler cgi-script .cgi
</Directory>
```

And then restart Apache2
```bash
sudo service apache2 restart
```

## Todo

 * check I am getting lrule/irule right


-----

Types, instances in the same table, distinguished by status.

|status	|thing     | source      | ending      |
|-------|----------|-------------|-------------|
|type	|normal type  |                        |     |
|ltype	|lexical type |  (type and in lexicon) | _lt |
|lex-entry      |lexical entry|                        | _le |
|rule	|syntactic construction/grammar rule |  (LKB::\*RULES)           | _c |
|lrule	|lexical rule |  (LKB::\*LRULES)          |   |
|irule	|inflectional rule | (LKB::\*LRULES and (inflectional-rule-p
|id))| lr |
|       |orth-invariant inflectional rule | _ilr |
|       |orth-changing inflectional rule  | _olr |
|       |orth-invariant derivational rule | _dlr | 
|       |orth-changing derivation rule    | _odlr|
|       |punctuation affixation rule      | _plr |


FIXME: add IDIOMS as a different table

