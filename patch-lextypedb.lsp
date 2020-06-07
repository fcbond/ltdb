;;;
;;; Patches for lextypedb
;;;
;;;
;;  (lkb::lkb-load-lisp "/home/bond/delphin/grammars/japanese/lkb/" "patch-lextypedb.lsp")


;;;
;;; Type output
;;;
(in-package :lkb)

;;;
;;; code from Stephan Oepen (thanks!) to find arity and head of rules
;;; mixed in with help from Ann
;;; 
(defun inspect-for-arity-and-head (rule)
  (let* ((id (rule-id rule))
         (dag (tdfs-indef (rule-full-fs rule)))
         (daughters (rest (rule-order rule)))
         (head (existing-dag-at-end-of dag *head-path*))
         (daughter (existing-dag-at-end-of dag *head-daughter-path*))
         (flags (pairlis '(:id :arity) (list id (length daughters)))))
    (loop
        for i from 0
        for path in daughters
        for foo = (existing-dag-at-end-of dag path)
        for bar = (and foo (existing-dag-at-end-of foo *head-path*))
        when (eq foo daughter) do (push (cons :daughter i) flags)
        when (eq head bar) do (push (cons :head i) flags))
    (let ((head (rest (assoc :head flags)))
          (daughter (rest (assoc :daughter flags))))
      (unless (or (null daughter) (= head daughter))
        (format t "inspect(): head uncertainty in `~(~a~)'.~%" id)))
    flags))

; (loop
;     for flags in
;       (loop
;           for rule being each hash-value in *rules*
;           collect (inspect rule))
;     do (format
;         t "~a ~a ~a~%"
;         (rest (assoc :id flags)) (rest (assoc :arity flags))
;         (rest (assoc :head flags))))


;;;
;;; Output information on lexical rules for lexical type DB.
;;;  (lkb::lrules-to-xml :file "/tmp/lrules.xml")

(defun lrules-to-xml  (&key (stream t) file)
  (let ((stream (if file
		    (open file
			  :direction :output :if-exists :supersede
			  :if-does-not-exist :create)
                  stream)))
    (format stream "<types>~%")
    (loop
        for rule being each hash-value in *lexical-rules*
        for id = (rule-id rule)
        for tdfs = (rule-full-fs rule)
        for type = (and tdfs (indef-type-of-tdfs tdfs))
        for inspected-rule = (inspect-for-arity-and-head rule)
        when (and id type) do
          (format
           stream
           "  <type name=\"~(~a~)\" parents=\"~(~a~)\" status=\"~a\" cat=\"~(~a~)\" val=\"~(~a~)\" cont=\"~(~a~)\" arity=\"~(~a~)\" head=\"~(~a~)\"/>~%"
           id type (if (inflectional-rule-p id) "inf-rule" "lex-rule")
	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs) 
					   '(SYNSEM LOCAL CAT HEAD)))
	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs) 
					   '(SYNSEM LOCAL CAT VAL)))
	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs) 
					   '(SYNSEM LOCAL CONT)))
           (rest (assoc :arity inspected-rule))
           (rest (assoc :head inspected-rule))
           ))
    (format stream "</types>~%")
    (when file (close stream))))


(defun rules-to-xml  (&key (stream t) file)
  (let ((stream (if file
		    (open file
			  :direction :output :if-exists :supersede
			  :if-does-not-exist :create)
                  stream)))
    (format stream "<types>~%")
    (loop
     for rule being each hash-value in *rules*
     for id = (rule-id rule)
     for tdfs = (rule-full-fs rule)
     for type = (and tdfs (indef-type-of-tdfs tdfs))
     for inspected-rule = (inspect-for-arity-and-head rule)
     when (and id type) do
          (format
           stream
           "  <type name=\"~(~a~)\" parents=\"~(~a~)\" status=\"rule\" cat=\"~(~a~)\" val=\"~(~a~)\" cont=\"~(~a~)\" arity=\"~(~a~)\" head=\"~(~a~)\"/>~% "
	   id
	   type
	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs) 
					   '(SYNSEM LOCAL CAT HEAD)))
	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs) 
					   '(SYNSEM LOCAL CAT VAL)))
	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs) 
					   '(SYNSEM LOCAL CONT)))
           (rest (assoc :arity inspected-rule))
           (rest (assoc :head inspected-rule))))
    (format stream "</types>~%")
    (when file (close stream))))

(defun roots-to-xml  (&key (stream t) file)
  (let ((stream (if file
		    (open file
			  :direction :output :if-exists :supersede
			  :if-does-not-exist :create)
                  stream)))
   (format stream "<types>~%")
   (loop
    for root in *root-entries*
    for id = (psort-id (rest root))
    when id do
    (format
     stream
     "  <type name=\"~(~a~)\" status=\"root\"/>~%"
     id))
   (format stream "</types>~%")
   (when file (close stream))))



;;;
;;; added xml as a type
;;; (lkb::output-types :xml "/tmp/jp-types.xml")
;;;
(defun output-types (syntax &optional file-name)
  (unless (member syntax '(:tdl :path :lilfes :xml))
    (error "Unsupported syntax specifier ~A" 
           syntax))
  (unless file-name 
    (setf file-name
         (ask-user-for-new-pathname "Output file?")))
  (when file-name 
    (with-open-file 
        (ostream file-name :direction :output :if-exists :supersede)
      (ecase syntax
	(:xml (format ostream "<types>~%")))
      (loop for type-name in *type-names*
;			      py-list
;                          ; remove unaccessed leaf types
;                          (remove-if-not 
;                           #'(lambda (x) (get-type-entry x))
;			   *types*)))
      ;;      (append *ordered-type-list*
      ;;	      *ordered-glbtype-list*))))
	  do
	    (let ((entry (get-type-entry type-name)))                  
             (ecase syntax
               (:tdl (output-type-as-tdl type-name entry
                                         ostream))
               (:path (output-type-as-paths type-name entry
                                         ostream))
               (:lilfes (output-type-as-lilfes type-name entry
                                               ostream))
	       (:xml  
		(output-type-as-xml type-name entry
				    ostream)))))
      (ecase syntax
	(:xml (format ostream "</types>~%"))))))
  

;;;#+:tsdb
(defun output-type-as-xml (name type-struct stream)
 (let* ((def (ltype-local-constraint type-struct))
        (parents (ltype-parents type-struct))
	(children (ltype-daughters type-struct))
	(comment (ltype-comment type-struct))
	(tdfs (ltype-tdfs type-struct))
	(synsem (mrs::path-value 
	      (tdfs-indef tdfs) '(SYNSEM)))
	(cat (mrs::path-value 
	      (tdfs-indef tdfs) '(SYNSEM LOCAL CAT HEAD)))
	(kkey (mrs::path-value 
	      (tdfs-indef tdfs) '(SYNSEM LOCAL CAT HEAD KEYS KEY)))
	(val (mrs::path-value 
	      (tdfs-indef tdfs) '(SYNSEM LOCAL CAT VAL)))
	(cont (mrs::path-value 
	      (tdfs-indef tdfs) '(SYNSEM LOCAL CONT))))
;        (status  (if (lexical-type-p name) "ltype" "type")))
   (format stream "~%<type name=\"~(~a~)\" "  name)
   (format stream "~%      parents=\"")
   (loop for parent in parents
	 for i from 1
	 when (> i 1)
	 do 
	 (format stream " "); separate with spaces
	 do
	 (format stream "~(~a~)" parent))
   (format stream "\"")
   (if children 
       (progn
	 (format stream "~%      children=\"")
	 (loop for child in children
	       for i from 1
	       when (> i 1)
	       do 
	       (format stream " "); separate with spaces
	       do
	       (format stream "~(~a~)" child))
	 (format stream "\"")))
   (if synsem 
       (format stream "~%      synsem=\"~(~a~)\"" (lkb::dag-type synsem)))
   (if kkey 
       (format stream "~%      keys.key=\"~(~a~)\"" (lkb::dag-type kkey)))
   (if cat 
       (format stream "~%      cat=\"~(~a~)\"" (lkb::dag-type cat)))
  (if val 
       (format stream "~%      val=\"~(~a~)\"" (lkb::dag-type val)))
  (if cont 
   (format stream "~%      cont=\"~(~a~)\"" (lkb::dag-type cont)))
  ; (if status 
  ;  (format stream "~%      status=\"~(~a~)\"" status))

					;   (format stream "~%          val=\"~(~a~)\"" 
;	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs)
;					   '(SYNSEM LOCAL CAT VAL))))
;   (format stream "~%          cont=\"~(~a~)\"" 
;	   (lkb::dag-type (mrs::path-value (tdfs-indef tdfs)
;					   '(SYNSEM LOCAL CONT))))
   (format stream ">")
   ;;; print escaped TDL
;;    (format stream (lkb::xml-escape 
;; 		   (with-output-to-string (plain-tdl)
   ;; 		     (output-type-as-tdl name type-struct plain-tdl))))
   ;;; print comment
   (if comment
       (format stream "~%<comment>~%~a~%</comment>"
	       (lkb::xml-escape comment)))
   ;;; print  TDL as CDATA
   (format stream "~%<![CDATA[")
   (output-type-as-tdl name type-struct stream)
   (format stream "~%]]>")
   ;; close XML
   (format stream "~%</type>~%")))


;;; Lexical Information
;;;(lkb::output-lex-summary lkb::*lexicon* "/tmp/lex.tab")
;;;
;;; don't use lexdb because not all grammars have it
;;;
;; 

(defun output-lex-summary (lexicon &optional file-name)
  (unless file-name 
    (setf file-name
      (ask-user-for-new-pathname "Output file?")))
  (when file-name 
    (with-open-file 
        (ostream file-name :direction :output :if-exists :supersede)
      (lex-summary  (collect-psort-ids *lexicon*) ostream))))

;;; how do I define TAB in format?
(defun lex-summary (lex-entries stream)
  (loop for word-entry in lex-entries
	for lex-entry =  (get-lex-entry-from-id word-entry :cache nil)
	for lex-tdfs = (tdfs-indef (psort-full-fs lex-entry))
	do
	(format stream "~A	~A	~{~A~^ ~}	~A	~A~%"
		;; lex-id
		(string-downcase word-entry)
		;; Lexical Type
		(string-downcase (lkb::dag-type lex-tdfs))
		;; ORTH
		(lex-entry-orth lex-entry)
		;; Predicate
		(string-downcase (if (mrs::path-value 
				      lex-tdfs '(SYNSEM LKEYS KEYREL PRED))
				     (lkb::dag-type 
				      (mrs::path-value 
				       lex-tdfs '(SYNSEM LKEYS KEYREL PRED)))))
	       ;; ALTKEY
		(string-downcase (if (mrs::path-value 
				      lex-tdfs '(SYNSEM LKEYS ALTKEYREL PRED))
				     (lkb::dag-type 
				      (mrs::path-value 
				       lex-tdfs '(SYNSEM LKEYS ALTKEYREL PRED))))))))
;               ;; KEYTAG
;            (lkb::dag-type (mrs::path-value lex-tdfs
;                                              '(SYNSEM LKEYS KEYREL CARG)))
;              ;; PTYPE
;             (lkb::dag-type (mrs::path-value lex-tdfs
;                                              '(SYNSEM LOCAL CAT HEAD PTYPE)))
