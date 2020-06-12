#!/bin/bash
#
# ToDo: parametrize special values (HEAD VALENCE CONTENT)
#
echo
echo  Welcome to the Linguistic Type Database
echo

usage="""You need to give a grammar directory or script file (or both)
    --script path/to/lkb/script
    --grmtdl path/to/grammar.tdl

You can add some lisp before we load the script
    --lisp (push :mal *features*)  

You can not add information from the gold trees
    --nogold 
"""


###
### get the grammar directory
###
gold='true'
while [ $# -gt 0 -a "${1#-}" != "$1" ]; do
  case ${1} in
      --script)
	  lkbscript=${2};
	  shift 2;
	  ;;
      --grmtdl)
	  grammartdl=${2};
	  shift 2;
	  ;;
      --lisp)
	  lisp=${2};
	  shift 2;
	  ;;
      --nogold)
	  gold='false'
	  shift 1;
	  ;;
      *)
	  echo "${usage}"
	  exit 0	
  esac
done


if [ ${lkbscript} ]
then
    echo "LKB script file is" ${lkbscript}
    grammardir=`dirname ${lkbscript}`
    grammardir=`dirname ${grammardir}`
    echo "Grammar directory is " ${grammardir}
elif [ ${grammartdl} ]
then
    echo "Grammar file is " ${grammartdl}
    grammardir=`dirname ${grammartdl}`
    echo "Grammar directory is " ${grammardir}
else
    echo "${usage}"
    exit 0
fi


# If you want to use LKB_FOS you must set this variable
# unset LKBFOS
LKBFOS=~/delphin/lkb_fos/lkb.linux_x86_64

if [[ -n ${LKBFOS} && -e ${LKBFOS} ]]; then
    LISPCOMMAND="${LKBFOS}"
    echo We will use ${LISPCOMMAND}
elif [[ -n $LOGONROOT && -e "${LOGONROOT}/bin/logon" ]]; then
    LISPCOMMAND="${LOGONROOT}/bin/logon --binary -I base -locale ja_JP.UTF-8"
    echo We will use ${LISPCOMMAND}
else
    echo we found no suitable LKB
fi
    


###
### set things up
###

now=`date --rfc-3339=date`


### Constants
LTDB_FILE="lt.db"                     # database
LINGUISTICS_FILE="linguistics.xml"    # docstrings and more
TYPES_FILE="types.xml"                # types
RULES_FILE="rules.xml"                # rules
ROOTS_FILE="roots.xml"                # roots 
LRULES_FILE="lrules.xml"              # lexical tules
LEXICON_FILE="lex.tab"                # lexicon

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
### write the temporary files to here
outdir=${LOGONTMP}/${version}

log=${outdir}/lkb.log
echo Log file at ${log}

### write the html here
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
echo "Would you like to continue (Y/n)?"
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

if [[ ${lkbscript} && ${LISPCOMMAND} ]]
then
    ### dump  the lex-types
    echo "Dumping lex-type definitions and lexicon using the LKB (slow but steady)" 
    
    
    unset DISPLAY;
    unset LUI;
    
{ 
 cat 2>&1 <<- LISP
  (format t "~%Read Grammar~%")
  (lkb::read-script-file-aux  "${lkbscript}")
  (lkb::lkb-load-lisp "." "patch-lextypedb.lsp")
  (format t "~%Output types~%")
  (lkb::output-types :xml "${outdir}/${TYPES_FILE}")
  (format t "~%Output lrules, rules and roots ~%")
  (lkb::lrules-to-xml :file "${outdir}/${LRULES_FILE}")
  (lkb::rules-to-xml :file "${outdir}/${RULES_FILE}")
  (lkb::roots-to-xml :file "${outdir}/${ROOTS_FILE}")
  (lkb::output-lex-summary lkb::*lexicon* "${outdir}/${LEXICON_FILE}")
  (format t "~%All Done!~%")
  #+allegro        (excl:exit)
  #+sbcl           (sb-ext:quit)
LISP
} | ${LISPCOMMAND}   2>${log} >${log}
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
fi
###
### make the databases
###
echo
echo "Creating the databases ..."
echo

sqlite3 ${db} < tables.sql

###
if [[ ${lkbscript} && ${LISPCOMMAND} ]]
then
    echo "Adding in the info from the lisp"
    echo
    python3 xml2db.py ${outdir} ${db}
fi

if [ ${grammartdl} ]
then
    echo "Adding in the info from the tdl with pydelphin"
    echo
    python3 tdl2db.py ${grammartdl} ${db}   ### add tdl and comments
fi

#echo "Adding in the info from the gold trees"
#echo
if [ ${gold} == 'true' ]
then
    python3 gold2db.py ${grammardir} ${db}
fi

echo
echo Install to ${CGI_DIR}
echo
mkdir -p ${CGI_DIR}
mkdir -p ${HTML_DIR}

###  copy cgi, javascript and css to cgi-bin
cp html/*.cgi html/*.py html/*.js html/*.css  ${CGI_DIR}/.   

### copy database to cgi-bin
cp ${outdir}/${LTDB_FILE} ${CGI_DIR}/.


### params
dbhost=`hostname -f`
echo "charset=utf-8" > ${CGI_DIR}/params
echo "dbroot=$CGI_DIR" >> ${CGI_DIR}/params
echo "db=$CGI_DIR/lt.db" >> ${CGI_DIR}/params
echo "cssdir=http://$dbhost/~$USER/ltdb/$version" >> ${CGI_DIR}/params
echo "cgidir=http://$dbhost/~$USER/cgi-bin/$version" >> ${CGI_DIR}/params
echo "ver=$version" >> ${CGI_DIR}/params

### HTML and logs
cp doc/lt-diagram.png html/*.js html/*.css html/ltdb.png ${HTML_DIR}/.
cp ${outdir}/*.log ${HTML_DIR}

python3 makehome.py ${version}  ${grammardir} > ${HTML_DIR}/index.html


### All done
URL=http://localhost/~${USER}/ltdb/${version}/
echo
echo
echo
echo "Almost done!  Take a look at " ${URL}
echo
echo
echo
echo "Still compressing the db for download" 
7z a ${HTML_DIR}/${LTDB_FILE}.7z ${CGI_DIR}/${LTDB_FILE}
echo "Really Done"
