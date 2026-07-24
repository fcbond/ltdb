import json
import logging
import re
import sys

from delphin import derivation as _derivation
from delphin import dmrs as _dmrs
from delphin.codecs import dmrsjson, mrsjson, simplemrs
from markdown_it import MarkdownIt

def sanitize_grm(grm: str) -> str | None:
    """Return a safe grammar filename, or None if the name is invalid.

    Rejects path traversal (``/``, ``\\``, ``..``), null bytes, and
    whitespace-only names.  Any other character the OS permits in a filename
    is allowed so that grammar names with parentheses, colons, or timestamps
    are not rejected.  Appends '.db' if absent.
    """
    if not grm or not grm.strip():
        return None
    grm = grm.strip()
    # Block path separators and null bytes
    if "/" in grm or "\\" in grm or "\x00" in grm:
        return None
    # Block traversal components
    if grm.startswith(".") or ".." in grm:
        return None
    if not grm.endswith(".db"):
        grm += ".db"
    return grm

_log = logging.getLogger(__name__)

_md = MarkdownIt("commonmark", {"html": False})

_namere = re.compile(r"""<name\s+lang=["'](.*)['"]>(.*)</name>""")
_section_tags = {
    "description": "Description",
    "features": "Features",
    "history": "History",
    "notes": "Notes",
    "todo": "Todo",
}
_section_tag_re = re.compile(
    r"""^<({})>\s*(.*)$""".format("|".join(_section_tags)),
    re.IGNORECASE,
)


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
            if ex.startswith("*"):
                print(
                    f"Warning: don't use '*' in examples, use <nex>: {line}",
                    file=sys.stderr,
                )
            count += 1
        else:
            m = _namere.search(line)
            if m:
                nams.append((typ, m.group(1), m.group(2)))
            else:
                m = _section_tag_re.match(line)
                if m:
                    title = _section_tags[m.group(1).lower()]
                    rest = m.group(2).strip()
                    desc.append(f"\n### {title}\n")
                    if rest:
                        desc.append(rest)
                else:
                    desc.append(line)
    return "\n".join(desc), exes, nams


def deriv_to_dict(deriv_str):
    """Convert a UDF derivation string to a dict for delphin-viz.

    Returns None on parse failure (logged as a warning); callers should
    treat None as "no derivation available" and skip rendering.
    """
    if not deriv_str:
        return None
    try:
        d = _derivation.from_string(deriv_str)
        return d.to_dict(fields=["id", "entity", "score", "form", "tokens"])
    except Exception as e:
        _log.warning("deriv parse failed: %s", e)
        return None


def mrs_to_dicts(mrs_str):
    """Convert a simplemrs string to (mrs_dict, dmrs_dict).

    Returns (None, None) if MRS cannot be parsed (logged as a warning).
    If DMRS conversion fails, returns (mrs_dict, None).
    """
    if not mrs_str:
        return None, None
    try:
        mrs_obj = simplemrs.decode(mrs_str)
        mrs_d = json.loads(mrsjson.encode(mrs_obj))
    except Exception as e:
        _log.warning("MRS parse failed: %s", e)
        return None, None
    try:
        dmrs_d = json.loads(dmrsjson.encode(_dmrs.from_mrs(mrs_obj)))
    except Exception as e:
        _log.warning("DMRS conversion failed: %s", e)
        dmrs_d = None
    return mrs_d, dmrs_d


def docstring2html(typ, docstring):
    """Render a TDL docstring to HTML via Markdown."""
    if not docstring:
        return ""
    description, _examples, _names = munge_desc(typ, docstring)
    return _md.render(description)


def render_markdown(text):
    """Render arbitrary Markdown (e.g. a deployment's home-page blurb) to HTML."""
    return _md.render(text)
