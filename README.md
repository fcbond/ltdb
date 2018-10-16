# ltdb
Linguistic Type Data-Base

The Linguistic Type Database (LTDB, née Lextype DB), describes types
and rules of a DELPH-IN grammar with frequency information from the
treebank. Lexical types can be seen as detailed parts-of-speech and
are the essence for the two important points just
mentioned. Information about a lexical type that the LTDB provides
includes its linguistic characteristics; and examples of usage from a
treebank; the way it is implemented in a grammar. It consists of a
database management system and a web-based interface, and is
constructed semi-automatically.

There is [more documentation](http://moin.delph-in.net/LkbLtdb) at the DELPH-IN Wiki.

The code is in a state of flux at the moment.


---

## Usage

1. Run `./make-ltdb.bash --grmdir /path/to/grammar`

```bash
./make-ltdb.bash --grmdir ~/logon/dfki/jacy
```

2. If you have any gold treebanks run 
```bash
./make-trees.bash --grmdir  /path/to/grammar
```
 (slow if you have a lot of trees, needs a fair bit of memory)

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
  * grammar-catalogue

  * jquery, jquery tablesorter (patched)
``` 
We assume that Sentence IDs are unique



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
|ltype	|lexical type |  (type and in lexicon) | lt |
|rule	|grammar rule |  (LKB::\*RULES)           | c |
|lrule	|lexical rule |  (LKB::\*LRULES)          |   |
|irule	|inflectional rule | (LKB::\*LRULES and (inflectional-rule-p id))| |


FIXME: add conventional ending in various grammars, maybe even check

FIXME: add IDIOMS as a different table

