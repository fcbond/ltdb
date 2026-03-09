import sys
import re
from markdown_it import MarkdownIt

_md = MarkdownIt()

_namere = re.compile(r"""<name\s+lang=["'](.*)['"]>(.*)</name>""")


def munge_desc(typ, description):
    """Parse a TDL docstring; return (markdown_text, examples, names).

    Custom tags:
      <ex>text   → numbered example (grammatical)
      <nex>text  → numbered example (ungrammatical, prefixed ∗)
      <mex>text  → numbered example (marginal, prefixed ⊛)
      <name lang='xx'>Name</name>  → collected into names list
    """
    exes = []
    nams = []
    desc = []
    count = 1
    for line in description.splitlines():
        line = line.strip()
        if line.startswith(("<ex>", "<nex>", "<mex>")):
            if line.startswith("<ex>"):
                ex = line[4:].strip()
                exes.append((ex, typ, 1))
                desc.append(f"\n{count}. *{ex}*\n")
            elif line.startswith("<nex>"):
                ex = line[5:].strip()
                exes.append((ex, typ, 0))
                desc.append(f"\n{count}. ∗ *{ex}*\n")
            else:
                ex = line[5:].strip()
                exes.append((ex, typ, 1))
                desc.append(f"\n{count}. ⊛ *{ex}*\n")
            if ex.startswith('*'):
                print(f"Warning: don't use '*' in examples, use <nex>: {line}",
                      file=sys.stderr)
            count += 1
        else:
            m = _namere.search(line)
            if m:
                nams.append((typ, m.group(1), m.group(2)))
            else:
                desc.append(line)
    return "\n".join(desc), exes, nams


def rst2html(typ, docstring):
    """Render a TDL docstring to HTML via Markdown."""
    if not docstring:
        return ''
    description, _examples, _names = munge_desc(typ, docstring)
    return _md.render(description)
