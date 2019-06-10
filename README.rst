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

--------------

Usage
-----

1. Run ``./make-ltdb.bash --grmdir /path/to/grammar``

.. code:: bash

    ./make-ltdb.bash --grmdir ~/logon/dfki/jacy

Everything is installed to ``~/public_html/``

Installation
------------

Requirements
~~~~~~~~~~~~

::

      * python 2.7, python 3, pydelphin, docutils, lxml
      * Perl
      * SQLite3
      * Apache
      * LKB/Lisp        for db dump
      * xmlstarlet      for validating lisp

We prefer that Sentence IDs are unique, if we see two sentences in the
gold treebank with the same ID, we only store the first one.

Install dependencies (in ubuntu):

.. code:: bash

    sudo apt-get install apache2 xmlstarlet
    sudo apt-get install python-docutils python3-docutils python3-lxml

    sudo pip install pydelphin --upgrade
    sudo pip3 install pydelphin --upgrade

Enable local directories in Apache2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This may be different on different operating systems

.. code:: bash

    sudo a2enmod userdir
    sudo a2enmod cgi

Put this in ``/etc/apache2/sites-available/000-default.conf``

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

Todo
----

-  check I am getting lrule/irule right

--------------

Types, instances in the same table, distinguished by status.


+----------+------------------------------------+-------------------+------+
|status    |thing                               | source            |  end |
+==========+====================================+===================+======+
|type      |normal type                         |                   |      |
+----------+------------------------------------+-------------------+------+
|ltype     |lexical type                        |type + in lexicon  | _lt  |
+----------+------------------------------------+-------------------+------+
|lex-entry |lexical entry                       |                   | _le  |   
+----------+------------------------------------+-------------------+------+
|rule      |syntactic construction/grammar rule | LKB:\*RULES       | _c   |
+----------+------------------------------------+-------------------+------+
|lrule	   |lexical rule                        | LKB:\*LRULES      | lr   |
+----------+------------------------------------+-------------------+------+
|irule	   |inflectional rule                   | LKB:\*LRULES +    | ilr  | 
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


FIXME: add IDIOMS as a different table
