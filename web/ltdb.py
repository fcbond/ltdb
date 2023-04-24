import docutils.core
import re

### ToDo move this to the processing, save the munged description
def munge_desc(typ,description):
    """parse the description and return: description.rst, examples, names

    <ex>an example
    becomes
    #. an example 
    and the example is ('an example', typ, 1) 
    <nex>bad example
    becomes
    #. ∗ bad example 
    and the example is ('bad example', typ, 0) 
    <mex>bad example that we parse
    becomes
    #. ⊛ bad example that we parse
    and the example is ('bad example that we parse', typ, 1) 

    <name lang='en'>Bare Noun Phrase</name>
    becomes (typ, en, 'Bare Noun Phrase')
    """
    exes = []
    nams = []
    namere=re.compile(r"""<name\s+lang=["'](.*)['"]>(.*)</name>""")
    desc = []
    count = 1
    for l in description.splitlines():
        l = l.strip()
        if l.startswith("<ex>") or l.startswith("<nex>") \
           or l.startswith("<mex>"):
            if l.startswith("<ex>"):
                ex = l[4:].strip()
                exes.append((ex,typ,1))
                desc.append("\n{:d}. *{}*\n".format(count, ex))
            elif l.startswith("<nex>"):
                ex = l[5:].strip()
                exes.append((ex,typ,0))
                desc.append("\n{:d}. ∗ *{}*\n".format(count, ex))
            else: # l.startswith("<mex>")
                ex = l[5:].strip()
                exes.append((ex,typ,1))
                desc.append("\n{:d}. ⊛ *{}*\n".format(count, ex))
            if ex.startswith('*'):
                print("Warning: don't use '*' in examples, just use <nex>:", l,
                      file=sys.stderr)
            count += 1
        else:
            m = namere.search(l)
            if m:
                nams.append((typ,m.group(1),m.group(2)))
            else:
                desc.append(l)
    
    #print("\n".join(desc),exes,nams)
    return "\n".join(desc), exes, nams 


def rst2html(typ, docstring):
    """Convert the print out the linguistic description in the doscstring
       use the value from the LKB if possible, if not then from pydelphin"""
    

    if docstring:
        description, examples, names=  munge_desc(typ,docstring)
        return docutils.core.publish_parts("\n"+ description +"\n",
                                           writer_name='html',
                                           settings_overrides= {'table_style':'colwidths-auto',
                                                                'initial_header_level':'3'})['body']
    else:
        return ''
