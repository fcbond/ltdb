"""Generate grew-match ERS snippets from the ESD phenomena.

Regenerates etc/grew_snippets/ers/*.req (one grew-query snippet per
ESD phenomenon) and the auto-generated <li> list inside the ERS tab of
etc/grew_snippets/_default.html, from phenomena.toml -- the same
source check_phenomena.py counts matches against. Run after adding,
removing, or editing a phenomenon in phenomena.toml:

    python doc/esd-phenomena/gen_snippets.py
"""

import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_phenomena import load_phenomena  # noqa: E402

SNIPPETS_DIR = Path(__file__).resolve().parents[2] / "etc" / "grew_snippets"
ERS_DIR = SNIPPETS_DIR / "ers"
DEFAULT_HTML = SNIPPETS_DIR / "_default.html"

BEGIN = "<!-- BEGIN GENERATED: doc/esd-phenomena/gen_snippets.py -->"
END = "<!-- END GENERATED -->"


def write_req(name, entry):
    """Write one phenomenon's grew-query as a commented .req snippet."""
    lines = [f"% {line}" for line in textwrap.wrap(entry["description"], 76)]
    lines.append("%")
    lines.append(f"% ERS fingerprint ({entry['url']}):")
    for fp_line in entry["fingerprint"].strip("\n").splitlines():
        lines.append(f"%   {fp_line}")
    lines.append("")
    lines.append(entry["grew-query"])
    ERS_DIR.mkdir(parents=True, exist_ok=True)
    (ERS_DIR / f"{name}.req").write_text("\n".join(lines) + "\n")


def snippet_list_html(phenomena):
    """Return the <li> list of ERS snippet links, sorted by name."""
    items = []
    for name in sorted(phenomena):
        label = name.replace("-", " ")
        items.append(
            f'      <li><a href="#" snippet-file="ers/{name}.req" '
            f'class="inter">{label}</a></li>'
        )
    return "\n".join(items)


def main():
    """Regenerate the ERS snippet files and _default.html's ERS tab."""
    phenomena = load_phenomena()
    for name, entry in phenomena.items():
        write_req(name, entry)

    html = DEFAULT_HTML.read_text()
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(html):
        sys.exit(
            f"No {BEGIN} ... {END} markers found in {DEFAULT_HTML}; "
            "add the ERS tab markup first"
        )
    replacement = f"{BEGIN}\n{snippet_list_html(phenomena)}\n      {END}"
    DEFAULT_HTML.write_text(pattern.sub(replacement, html))
    print(f"Wrote {len(phenomena)} snippets to {ERS_DIR}")
    print(f"Updated {DEFAULT_HTML}")


if __name__ == "__main__":
    main()
