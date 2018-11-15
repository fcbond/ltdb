

Make the SQL graph like this:

::
   sqlt-graph -c --natural-join --from=SQLite -t svg -o lt-graph.svg tables.sql
   sqlt-diagram --natural-join --color --from=SQLite -i png -o lt-diagram.png tables.sql 

See https://metacpan.org/pod/distribution/SQL-Translator/script/sqlt-diagram

Maybe also try: https://pypi.org/project/ERAlchemy/
