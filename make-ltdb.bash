#!/bin/bash
#
# ToDo: parametrize special values (HEAD VALENCE CONTENT)
#
unset DISPLAY;
unset LUI;
export PYTHONPATH=~/svn/pydelphin:${PYTHONPATH}

while [ $# -gt 0 -a "${1#-}" != "$1" ]; do
  case ${1} in
    --grmdir)
      grammardir=${2};
      shift 2;
      ;;
  esac
done

source ltdb-conf.bash

#outdir=/tmp/new

echo 
echo "Creating a lextypedb for the grammar stored at: $grammardir"
echo 
echo "Temporary files will be stored in $outdir"
echo

echo
echo "It will be installed into:"
echo "   $HTML_DIR"
echo "   $CGI_DIR"
echo 
echo "Would you like to continue (y/n)?"
read
case $REPLY in
   no|n) exit 0;;
    *) echo "Keeping on" ;;
esac


### make the output directory
echo "Writing output to $outdir"
rm -rf $outdir
mkdir -p $outdir

db=${outdir}/${LTDB_FILE}

### dump  the lex-types
echo "Dumping lex-type definitions and lexicon (slow but steady)" 

{ 
 cat 2>&1 <<- LISP
  ;(load "$lkbdir/src/general/loadup")
  ;(compile-system "lkb" :force t)
  (lkb::read-script-file-aux  "$grammardir/lkb/script")
  (lkb::lkb-load-lisp "." "patch-lextypedb.lsp")
  (lkb::output-types :xml "$outdir/$TYPES_FILE")
  (lkb::lrules-to-xml :file "$outdir/$LRULES_FILE")
  (lkb::rules-to-xml :file "$outdir/$RULES_FILE")
  (lkb::roots-to-xml :file "$outdir/$ROOTS_FILE")
  (lkb::output-lex-summary lkb::*lexicon* "$outdir/$LEXICON_FILE")
  (format t "~%All Done!~%")
  #+allegro        (excl:exit)
  #+sbcl           (sb-ext:quit)
LISP
} | ${LOGONROOT}/bin/logon --binary -I base -locale ja_JP.UTF-8 2>${log} >${log}
#} | cat 

###
### Try to validate the types.xml
###
if which xmlstarlet  &> /dev/null; then
    xmlstarlet val  -e $outdir/$TYPES_FILE
    xmlstarlet val  -e $outdir/$RULES_FILE
    xmlstarlet val  -e $outdir/$LRULES_FILE
    xmlstarlet val  -e $outdir/$ROOTS_FILE
else 
    echo
    echo "   types files not validated, please install xmlstarlet."
    echo "   sudo apt-get install xmlstarlet"
    echo
fi
echo
echo "Dumping type descriptions for " `ls ${grammardir}/*.tdl`
echo
./description2xml.perl ${grammardir}/*.tdl > $outdir/$LINGUISTICS_FILE

xmlstarlet val -e $outdir/$LINGUISTICS_FILE
###
### make the databases
###
echo
echo "Creating the databases ..."
echo

python3 xml2db.py $outdir $db
python3 gold2db.py $grammardir $db

echo
echo Install to $CGI_DIR
echo
mkdir -p $CGI_DIR
mkdir -p $HTML_DIR
cp html/*.cgi html/*.py $CGI_DIR/.

### CGI
cp $outdir/$LTDB_FILE $CGI_DIR/.

### params
dbhost=`hostname -f`
echo "charset=utf-8" > $CGI_DIR/params
echo "dbroot=$CGI_DIR" >> $CGI_DIR/params
echo "db=$CGI_DIR/lt.db" >> $CGI_DIR/params
echo "cssdir=http://$dbhost/~$USER/ltdb/$version" >> $CGI_DIR/params
echo "cgidir=http://$dbhost/~$USER/cgi-bin/$version" >> $CGI_DIR/params
echo "ver=$version" >> $CGI_DIR/params
### trees
mkdir -p $HTML_DIR/trees

### HTML
cp html/*.css $HTML_DIR/.
cp $lkbdir/src/tsdb/css/*.css  $HTML_DIR/.
cp $lkbdir/src/tsdb/js/*.js  $HTML_DIR/.


#
# Make the IndexPage
#

echo "<html><body><h1>Welcome to $version</h1>" > $HTML_DIR/index.html
echo "<head><link rel='stylesheet' type='text/css' href='lextypedb.css'/></head>" >> $HTML_DIR/index.html
echo "<ul>  <li>  <a href='../../cgi-bin/$version/search.cgi'>Lexical Type Database for $version</a> ( <a href='../../cgi-bin/$version/search.cgi'>Search</a>)"  >> $HTML_DIR/index.html

echo "  <li>  <a href='http://wiki.delph-in.net/moin/LkbLtdb'>Lexical Type Database Wiki</a>"   >> $HTML_DIR/index.html

if [ -n "$grammarurl" ]; then
echo "  <li>  <a href='$grammarurl'>Grammar Home Page</a>"  >> $HTML_DIR/index.html
fi

echo "  <li>  <a href='http://www.delph-in.net/'>DELPH-IN Network</a>"  >> $HTML_DIR/index.html

echo "  <li>  <a href='http://wiki.delph-in.net/moin/FrontPage'>DELPH-IN Wiki</a>" >> $HTML_DIR/index.html
echo "</ul>" >> $HTML_DIR/index.html

bash $MAKECAT -w ${grammardir} >> $HTML_DIR/index.html


echo "<p>Created on $now</p>"  >> $HTML_DIR/index.html
echo "</html></body>" >> $HTML_DIR/index.html

### All done
echo
echo "Done: take a look at $HTML_DIR/index.html"
echo
