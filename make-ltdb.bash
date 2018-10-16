#!/bin/bash
#
# ToDo: parametrize special values (HEAD VALENCE CONTENT)
#

# If you want to use LKB_FOS you must set this variable
# unsetenv LKBFOS
LKBFOS=~/bin/lkb_fos/lkb.linux_x86_64

if [ ${LKBFOS} ]
then
    LISPCOMMAND="${LKBFOS}  2>${log} >${log}"
else
    LISPCOMMAND="${LOGONROOT}/bin/logon --binary -I base -locale ja_JP.UTF-8 2>${log} >${log}"    
fi
    

###
### Change this
###
MAKECAT=`locate -b "\create-catalogue-entry.sh"`
if [ ${MAKECAT} ]
then
    echo "Found Grammar Catalogue Creator: " ${MAKECAT}
else
    printf "\033[1;31m Couldn't find Grammar Catalogue Creator \033[0m \n" #RED
    printf "\033[1;31m Install from https://github.com/delph-in/grammar-catalogue.git \033[0m \n" #RED
fi

###
### get the grammar directory
###

while [ $# -gt 0 -a "${1#-}" != "$1" ]; do
  case ${1} in
    --grmdir)
      grammardir=${2};
      shift 2;
      ;;
  esac
done

echo "Grammar directory is " ${grammardir}

###
### set things up
###

treebanks=`ls -d ${grammardir}/tsdb/gold/*`
now=`date --rfc-3339=date`


### Constants
LTDB_FILE="lt.db"
LINGUISTICS_FILE="linguistics.xml"
TYPES_FILE="types.xml"
RULES_FILE="rules.xml"
ROOTS_FILE="roots.xml"
LRULES_FILE="lrules.xml"
LEXICON_FILE="lex.tab"
TB_FILE="result"

### I really don't want to do this!
if [ -f  ${grammardir}/Version.lsp ]; then
    versionfile=${grammardir}/Version.lsp
else
    versionfile=${grammardir}/Version.lisp
fi

version=`perl -ne 'if (/^\(defparameter\s+\*grammar-version\*\s+\"(.*)\s+\((.*)\)\"/) {print "$1_$2"}' $versionfile`
if [ -z "$version" ]; then
    echo "Don't know the version, will use 'something'"
    version=something
fi

version=${version// /_}

if [ -z "${LOGONTMP}" ]; then
  export LOGONTMP=/tmp
fi
outdir=${LOGONTMP}/${version}

log=${outdir}/log
echo ${log}

HTML_DIR=${HOME}/public_html/ltdb/${version}
CGI_DIR=${HOME}/public_html/cgi-bin/${version}

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
case ${REPLY} in
   no|n) exit 0;;
    *) echo "Keeping on" ;;
esac


### make the output directory
echo "Writing output to $outdir"
rm -rf "${outdir}"
mkdir -p "${outdir}"

db=${outdir}/${LTDB_FILE}

### dump  the lex-types
echo "Dumping lex-type definitions and lexicon (slow but steady)" 


unset DISPLAY;
unset LUI;

{ 
 cat 2>&1 <<- LISP
  (lkb::read-script-file-aux  "${grammardir}/lkb/script")
  (lkb::lkb-load-lisp "." "patch-lextypedb.lsp")
  (lkb::output-types :xml "${outdir}/${TYPES_FILE}")
  (lkb::lrules-to-xml :file "${outdir}/${LRULES_FILE}")
  (lkb::rules-to-xml :file "${outdir}/${RULES_FILE}")
  (lkb::roots-to-xml :file "${outdir}/${ROOTS_FILE}")
  (lkb::output-lex-summary lkb::*lexicon* "${outdir}/${LEXICON_FILE}")
  (format t "~%All Done!~%")
  #+allegro        (excl:exit)
  #+sbcl           (sb-ext:quit)
LISP
} | ${LISPCOMMAND}
# } | cat 

###
### Try to validate the types.xml
###
if which xmlstarlet  &> /dev/null; then
    xmlstarlet val  -e ${outdir}/${TYPES_FILE}
    xmlstarlet val  -e ${outdir}/${RULES_FILE}
    xmlstarlet val  -e ${outdir}/${LRULES_FILE}
    xmlstarlet val  -e ${outdir}/${ROOTS_FILE}
else 
    echo
    echo "   types files not validated, please install xmlstarlet."
    echo "   sudo apt-get install xmlstarlet"
    echo
fi
echo
echo "Dumping type descriptions for " `ls ${grammardir}/*.tdl`
echo
./description2xml.perl ${grammardir}/*.tdl > ${outdir}/${LINGUISTICS_FILE}

xmlstarlet val -e ${outdir}/${LINGUISTICS_FILE}
###
### make the databases
###
echo
echo "Creating the databases ..."
echo

python3 xml2db.py ${outdir} ${db}
python3 gold2db.py ${grammardir} ${db}

echo
echo Install to ${CGI_DIR}
echo
mkdir -p ${CGI_DIR}
mkdir -p ${HTML_DIR}
cp html/*.cgi html/*.py html/*.js html/*.css  ${CGI_DIR}/.   # we must copy javascript and css to cgi-bin too

### CGI
cp ${outdir}/${LTDB_FILE} ${CGI_DIR}/.

### params
dbhost=`hostname -f`
echo "charset=utf-8" > ${CGI_DIR}/params
echo "dbroot=$CGI_DIR" >> ${CGI_DIR}/params
echo "db=$CGI_DIR/lt.db" >> ${CGI_DIR}/params
echo "cssdir=http://$dbhost/~$USER/ltdb/$version" >> ${CGI_DIR}/params
echo "cgidir=http://$dbhost/~$USER/cgi-bin/$version" >> ${CGI_DIR}/params
echo "ver=$version" >> ${CGI_DIR}/params
### trees
mkdir -p ${HTML_DIR}/trees

### HTML
cp html/*.js html/*.css ${HTML_DIR}/.
# cp ${lkbdir}/src/tsdb/css/*.css  ${HTML_DIR}/.
# cp ${lkbdir}/src/tsdb/js/*.js  ${HTML_DIR}/.


#
# Make the IndexPage
#

echo "<html><body><h1>Welcome to $version</h1>" > ${HTML_DIR}/index.html
echo "<head><link rel='stylesheet' type='text/css' href='lextypedb.css'/></head>" >> ${HTML_DIR}/index.html
echo "<ul>  <li>  <a href='../../cgi-bin/$version/search.cgi'>Lexical Type Database for $version</a> ( <a href='../../cgi-bin/$version/search.cgi'>Search</a>)"  >> ${HTML_DIR}/index.html

echo "  <li>  <a href='http://wiki.delph-in.net/moin/LkbLtdb'>Lexical Type Database Wiki</a>"   >> ${HTML_DIR}/index.html

if [ -n "$grammarurl" ]; then
echo "  <li>  <a href='$grammarurl'>Grammar Home Page</a>"  >> ${HTML_DIR}/index.html
fi

echo "  <li>  <a href='http://www.delph-in.net/'>DELPH-IN Network</a>"  >> ${HTML_DIR}/index.html

echo "  <li>  <a href='http://wiki.delph-in.net/moin/FrontPage'>DELPH-IN Wiki</a>" >> ${HTML_DIR}/index.html
echo "</ul>" >> ${HTML_DIR}/index.html



if [ ${MAKECAT} ]
then
    bash ${MAKECAT} -w ${grammardir} >> ${HTML_DIR}/index.html
fi



echo "<p>Created on $now</p>"  >> ${HTML_DIR}/index.html
echo "</html></body>" >> ${HTML_DIR}/index.html

### All done
echo
echo "Done: take a look at $HTML_DIR/index.html"
echo
