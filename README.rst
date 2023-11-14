ltdb
====

Linguistic Type Data-Base

The Linguistic Type Database (LTDB, née Lextype DB), describes types and
rules of a DELPH-IN grammar with frequency information from the
treebank. Lexical types can be seen as detailed parts-of-speech.
Information about the types are constructed from the linguists
documentation in the grammar, a kind of literate programming.

There is `more documentation <http://moin.delph-in.net/LkbLtdb>`__ at
the DELPH-IN Wiki.


LTDB assumes that the grammar follows the usual DELPH-IN conventions,
in particular that there is a grammar directory with sub directories
for ace and lkb config files.  

``
grammar/ace/config.tdl
grammar/lkb/script
``

If your `orth-path` is not `STEM` then you must have it defined in the
**top** ace config file, we do not follow includes for config files (yet). 

--------------

Usage
-----

0. Prepare the local environment
   ``
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install --upgrade pip
   pip install -r requirements.txt
   ``

1. Run ``./make-ltdb.bash --script /path/to/grammar/lkb/script``

or (somewhat experimental but gets more docstrings)

2. Run ``./make-ltdb.bash --acecfg /path/to/ace/config.tdl``
   
3. Add extra lisp to call before the script
   ``./make-ltdb.bash   --lisp '(push :mal *features*)' --script /path/to/grammar/lkb/script``

4. You can tell it to just read the grammar, not gold (mainly useful for debugging)
   ``./make-ltdb.bash --acecfg /path/to/ace/config.tdl --nogold``

You can load from lisp and ace versions of the grammar, it will try to merge information from both.

.. code:: bash

    ./make-ltdb.bash --script ~/logon/dfki/jacy/lkb/script
    ./make-ltdb.bash --acecfg ~/logon/dfki/jacy/ace/config.tdl

Everything is installed to ``~/public_html/``

Installation
------------

Requirements
~~~~~~~~~~~~

::

      * python 3, pydelphin, docutils, lxml
      * Perl
      * SQLite3
      * Apache
      * LKB/Lisp        for db dump
      * xmlstarlet      for validating lisp

We store items as (profile, item-id) pairs, so Sentence IDs do not
need to be unique.

Only the new LKB-FOS (http://moin.delph-in.net/LkbFos) supports the new docstring comments.  We assume it is installed in
``LKBFOS=~/delphin/lkb_fos/lkb.linux_x86_64``.

Install dependencies (in ubuntu):

.. code:: bash

    sudo apt-get install apache2 xmlstarlet p7zip sqlite3
    sudo apt-get install python3-docutils python3-lxml

    pip install pydelphin --upgrade

Enable local directories in Apache2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This may be different on different operating systems

.. code:: bash

    sudo a2enmod userdir
    sudo a2enmod cgi

Put this at the end of ``/etc/apache2/sites-available/000-default.conf``

.. code:: xml

    <Directory /home/*/public_html/cgi-bin/>
       Options +ExecCGI
       AddHandler cgi-script .cgi
    </Directory>

And then restart Apache2

.. code:: bash

    sudo service apache2 restart

You may have to change the path to the LKB inside ``make-ltdb.bash``

.. code:: bash

    LKBFOS=~/delphin/lkb_fos/lkb.linux_x86_64

Trouble Shooting
~~~~~~~~~~~~~~~~

If the LKB complains

::

    error finding frame source: Bogus form-number: ....

it probably means you have a docstring in an instance file, or an old
version of the LKB. Make sure you only document types for now.

If you are having trouble with apache encodings, set the following in ``/etc/apache2/apache2.conf``

::

   SetEnv PYTHONIOENCODING utf8

To make debugging 

On Ubuntu 18.04, to get python3 modwsgi working if you have updated from an earlier version (so your python defaults to 2.7) do this

.. code:: bash

    sudo apt-get install libapache2-mod-wsgi-py3 
    sudo update-alternatives --install /usr/bin/python python /usr/bin/python2.7 1 
    sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.6 2 

Links go to the wrong place
---------------------------

ltdb assumes that the code is being served from a machine whose name
is  ``hostname -f`` using ``http`` in your ``public_html``.  If that is not true, e.g. you
want to change the host, or port or use https, then please change the
appropriate parts of ``params``. 

.. code:: bash

    charset=utf-8
    dbroot=/home/bond/public_html/cgi-bin/ERG_mal_mo
    db=/home/bond/public_html/cgi-bin/ERG_mal_mo/lt.db
    cssdir=http://mori/~bond/ltdb/ERG_mal_mo
    cgidir=http://mori/~bond/cgi-bin/ERG_mal_mo
    ver=ERG_mal_mo


    
Todo
----

--------------

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
