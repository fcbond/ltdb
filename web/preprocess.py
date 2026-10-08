"""Optional per-grammar input preprocessing (morphological analysis / segmentation).

Some DELPH-IN grammars delegate tokenization or morphology to an external
analyzer and cannot parse raw orthographic text in the demo:

* Jacy (Japanese, ISO ``jpn``): word segmentation via MeCab.
* Zhong (Chinese, ISO ``cmn``): word segmentation via jieba.
* SRG (Spanish, ISO ``spa``): morphology + POS tags via FreeLing, fed to ACE as
  a YY token lattice (``-y --yy-rules``).
* kal-hpsg (Kalaallisut, ISO ``kal``): morpheme segmentation via the in-process
  KARMA package.

This module is a small pluggable registry.  :func:`preprocess_for` looks up an
analyzer for a grammar (by ISO code, falling back to its short name), runs it
when its backing tool is available, and otherwise returns the input unchanged so
the demo degrades gracefully.  Analyzers that emit a YY token lattice also return
the extra ACE flags needed to consume it.

Everything here is OPTIONAL.  Grammars such as the ERG, whose tokenization is
compiled into the ``.dat``, never hit an analyzer and are unaffected.  Backends
are configured with environment variables (see each class); set ``LTDB_ANALYZERS``
to a comma-separated list of ISO codes to restrict which analyzers are active.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Map alternative / 2-letter ISO codes onto the canonical key used in REGISTRY.
_ISO_ALIASES = {
    "ja": "jpn",
    "jp": "jpn",
    "zh": "cmn",
    "zho": "cmn",
    "es": "spa",
    "kl": "kal",
}

# Fallback: match on SHORT_GRAMMAR_NAME when ISO_CODE is absent/unknown.
_SHORTNAME_ISO = {
    "jacy": "jpn",
    "zhong-zhs": "cmn",
    "zhong-zht": "cmn",
    "zhong": "cmn",
    "srg": "spa",
    "kal-hpsg": "kal",
}

_ANALYZER_TIMEOUT = 20


@dataclass
class PreprocessResult:
    """The outcome of preprocessing one input string for ACE.

    Attributes:
        ace_input: The string to actually send to ACE (raw text, space-separated
            tokens, or a YY token lattice).
        yy: True if *ace_input* is a YY token lattice.
        extra_cmdargs: Extra ACE command-line flags (e.g. ``["-y", "--yy-rules"]``).
        tokens: Segmented tokens, for display in the UI (None if not segmented).
        analyzer: Name of the analyzer used, or None if the input was untouched.
        note: A user-facing hint (e.g. that an analyzer is not installed).
    """

    ace_input: str
    yy: bool = False
    extra_cmdargs: list[str] = field(default_factory=list)
    tokens: list[str] | None = None
    analyzer: str | None = None
    note: str | None = None


@runtime_checkable
class Analyzer(Protocol):
    """A morphological analyzer / segmenter backend."""

    name: str
    description: str

    def available(self) -> bool:
        """Return True if the backing tool is installed and usable."""
        ...

    def run(self, text: str) -> PreprocessResult:
        """Analyze *text* and return a :class:`PreprocessResult`."""
        ...


class MeCabAnalyzer:
    """Japanese word segmentation via MeCab's ``-O wakati`` mode.

    The MeCab binary is taken from ``$MECAB_BIN`` (default ``mecab``).  Output is
    space-separated tokens, which is exactly what Jacy expects; ACE's compiled-in
    REPP handles the rest, so no YY lattice is needed.
    """

    name = "MeCab"
    description = "Segments Japanese input into words with MeCab before parsing."

    def __init__(self) -> None:
        self._bin = os.environ.get("MECAB_BIN", "mecab")

    def available(self) -> bool:
        """Return True if the MeCab binary is on PATH."""
        return shutil.which(self._bin) is not None

    def run(self, text: str) -> PreprocessResult:
        """Segment *text* into space-separated tokens with MeCab."""
        proc = subprocess.run(
            [self._bin, "-O", "wakati"],
            input=text,
            capture_output=True,
            text=True,
            timeout=_ANALYZER_TIMEOUT,
            check=True,
        )
        tokens = proc.stdout.split()
        return PreprocessResult(
            ace_input=" ".join(tokens), tokens=tokens, analyzer=self.name
        )


class JiebaAnalyzer:
    """Chinese word segmentation via the pure-Python ``jieba`` package.

    Output is space-separated tokens; Zhong's REPP applies secondary
    segmentation fixes, so a plain segmentation is sufficient.
    """

    name = "jieba"
    description = "Segments Chinese input into words with jieba before parsing."

    def available(self) -> bool:
        """Return True if the jieba package is importable."""
        return importlib.util.find_spec("jieba") is not None

    def run(self, text: str) -> PreprocessResult:
        """Segment *text* into space-separated tokens with jieba."""
        import jieba

        tokens = [tok for tok in jieba.cut(text, cut_all=False) if tok.strip()]
        return PreprocessResult(
            ace_input=" ".join(tokens), tokens=tokens, analyzer=self.name
        )


class CommandAnalyzer:
    """Run an external command that turns raw text into ACE input.

    This covers analyzers that are not Python libraries — notably FreeLing for
    Spanish and KARMA for Kalaallisut.  The command is configured by environment
    variable so the deployment, not the grammar database, owns the tool path.

    The command receives the raw sentence on stdin and must print the ACE input
    on stdout: either a YY token lattice (``mode="yy"``) or space-separated
    tokens (``mode="segment"``).  In YY mode the result carries the ``-y`` flag
    (and ``--yy-rules`` when *yy_rules* is set) so the route passes them to ACE.

    Args:
        name: Human-readable analyzer name (shown in the UI).
        description: One-line, user-facing summary of what it does.
        env_cmd: Environment variable holding the command to run. The value is
            split on whitespace; the sentence is piped to the command's stdin.
        mode: ``"yy"`` for a YY lattice, ``"segment"`` for spaced tokens.
        yy_rules: Add ``--yy-rules`` when in YY mode.
    """

    def __init__(
        self,
        name: str,
        description: str,
        env_cmd: str,
        mode: str = "yy",
        yy_rules: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self._env_cmd = env_cmd
        self._mode = mode
        self._yy_rules = yy_rules

    def _command(self) -> list[str]:
        """Return the configured command as an argv list, or [] if unset.

        Parsed with :func:`shlex.split` so quoted arguments and paths
        containing spaces survive.
        """
        raw = os.environ.get(self._env_cmd, "").strip()
        return shlex.split(raw) if raw else []

    def available(self) -> bool:
        """Return True if the command is configured and its program exists."""
        cmd = self._command()
        return bool(cmd) and shutil.which(cmd[0]) is not None

    def run(self, text: str) -> PreprocessResult:
        """Run the external command over *text* and wrap its output for ACE."""
        proc = subprocess.run(
            self._command(),
            input=text,
            capture_output=True,
            text=True,
            timeout=_ANALYZER_TIMEOUT,
            check=True,
        )
        out = proc.stdout.strip()
        if not out:
            # Exit 0 but no output: don't hand ACE an empty sentence (with YY
            # flags still set). Raise so preprocess_for() falls back to raw.
            raise ValueError(f"{self.name} produced no output")
        if self._mode == "yy":
            extra = ["-y"] + (["--yy-rules"] if self._yy_rules else [])
            return PreprocessResult(
                ace_input=out, yy=True, extra_cmdargs=extra, analyzer=self.name
            )
        tokens = out.split()
        return PreprocessResult(
            ace_input=" ".join(tokens), tokens=tokens, analyzer=self.name
        )


class KarmaAnalyzer:
    """Kalaallisut morpheme segmentation via the in-process KARMA package.

    KARMA (https://github.com/alexhsu-nlp/karma) is a pure-Python rule-based
    morphological analyzer, imported and called directly — there is no CLI.  For
    each word it may offer several analyses; we take the first (preferred) one.

    Its output keeps morpheme boundaries as ``-`` (and ``=`` for enclitics)
    *within* a word and separates words by spaces, which is exactly what the
    kal-hpsg grammar's morphological rules expect (its REPP splits on space/tab/
    ``=`` but not ``-``), and it also normalises orthography to the grammar's
    underlying forms (e.g. ``illu`` → ``iglu``).  So the result is plain
    segmented text, not a YY lattice.
    """

    name = "KARMA"
    description = (
        "Segments Kalaallisut input into morphemes with KARMA before parsing, "
        "and normalises orthography to the grammar's underlying forms."
    )

    def available(self) -> bool:
        """Return True if the karma package is importable."""
        return importlib.util.find_spec("karma") is not None

    def run(self, text: str) -> PreprocessResult:
        """Segment *text* into the grammar's morpheme-boundary notation."""
        from karma.encode_decode import parse_sentence

        parsed = parse_sentence(text.lower())
        segs: list[str] = []
        multiple = False
        unanalyzed = False
        for analyses in parsed.result:
            if not analyses:  # a word KARMA could not analyze
                unanalyzed = True
                break
            if len(analyses) > 1:
                multiple = True
            segs.append(str(analyses[0]))
        if unanalyzed or not segs:
            # Dropping a word would leave a shorter sentence that could parse
            # and look misleadingly successful; fall back to the raw input.
            return PreprocessResult(
                ace_input=text,
                analyzer=self.name,
                note="KARMA could not segment every word; parsing the raw input.",
            )
        note = (
            "KARMA found multiple analyses; using the first for each word."
            if multiple
            else None
        )
        return PreprocessResult(
            ace_input=" ".join(segs), tokens=segs, analyzer=self.name, note=note
        )


def _build_registry() -> dict[str, Analyzer]:
    """Construct the default ISO-code → analyzer registry."""
    return {
        "jpn": MeCabAnalyzer(),
        "cmn": JiebaAnalyzer(),
        "spa": CommandAnalyzer(
            "FreeLing",
            "Analyzes Spanish input with FreeLing (morphology + POS tags) "
            "before parsing.",
            "SRG_YY_CMD",
            mode="yy",
            yy_rules=True,
        ),
        "kal": KarmaAnalyzer(),
    }


# Module-level registry; tests may monkeypatch individual entries.
REGISTRY: dict[str, Analyzer] = _build_registry()


def _enabled_isos() -> set[str] | None:
    """Return the set of ISO codes enabled via ``$LTDB_ANALYZERS``, or None (all)."""
    raw = os.environ.get("LTDB_ANALYZERS", "").strip()
    if not raw:
        return None
    return {code.strip().lower() for code in raw.split(",") if code.strip()}


def iso_for(md: dict) -> str | None:
    """Resolve a grammar's analyzer ISO key from its metadata dict.

    Uses ``ISO_CODE`` (normalised through :data:`_ISO_ALIASES`) and falls back to
    ``SHORT_GRAMMAR_NAME``.  Returns None if nothing matches a registered analyzer.
    """
    iso = (md.get("ISO_CODE") or "").strip().lower()
    iso = _ISO_ALIASES.get(iso, iso)
    if iso in REGISTRY:
        return iso
    short = (md.get("SHORT_GRAMMAR_NAME") or "").strip().lower()
    return _SHORTNAME_ISO.get(short)


def analyzer_for(md: dict) -> Analyzer | None:
    """Return the registered analyzer for *md*'s grammar, or None.

    Looks up an analyzer by ISO code / short name and checks it is not disabled
    via ``$LTDB_ANALYZERS``. Does not check :meth:`Analyzer.available` -- callers
    that need to know whether the backing tool is actually usable should call
    that themselves.

    Args:
        md: Grammar metadata dict (as returned by ``web.db.get_md``).

    Returns:
        The matching :class:`Analyzer`, or None if none applies.
    """
    iso = iso_for(md)
    if iso is None:
        return None
    enabled = _enabled_isos()
    if enabled is not None and iso not in enabled:
        return None
    return REGISTRY[iso]


def preprocess_for(md: dict, text: str) -> PreprocessResult:
    """Preprocess *text* for the grammar described by *md*.

    Looks up an analyzer by ISO code / short name.  Returns a pass-through result
    (raw text, no extra flags) when there is no analyzer, it is disabled via
    ``$LTDB_ANALYZERS``, its tool is unavailable, or it errors — so the caller can
    always fall back to parsing the text as given.

    Args:
        md: Grammar metadata dict (as returned by ``web.db.get_md``).
        text: The raw user input.

    Returns:
        A :class:`PreprocessResult`.
    """
    analyzer = analyzer_for(md)
    if analyzer is None:
        return PreprocessResult(ace_input=text)

    # Availability discovery (e.g. shutil.which, imports) can itself raise, so
    # it is inside the guard — any failure degrades to the raw input rather than
    # surfacing a 500. Notes are kept generic; details (which may include tool
    # paths or configured arguments) are logged server-side, not sent to the client.
    try:
        if not analyzer.available():
            return PreprocessResult(
                ace_input=text,
                analyzer=analyzer.name,
                note=(
                    f"{analyzer.name} is not installed on the server; "
                    "enter already-segmented input, or install the analyzer."
                ),
            )
        return analyzer.run(text)
    except Exception:  # noqa: BLE001 - any tool failure degrades gracefully
        logger.exception("analyzer %s failed; falling back to raw input", analyzer.name)
        return PreprocessResult(
            ace_input=text,
            analyzer=analyzer.name,
            note=f"{analyzer.name} could not analyze the input; parsing it as given.",
        )
