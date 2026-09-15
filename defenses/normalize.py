# defenses/normalize.py — defeat obfuscation before any filter runs.
#
# Attack family: OBFUSCATION. A keyword filter blocks "system prompt" but sees
# nothing in "c3lzdGVtIHByb21wdA==", "flfgrz cebzcg" (rot13), or "s y s t e m".
# So we normalise + decode the message into a set of plausible plaintext
# variants and let input_rails screen ALL of them. This raises the bar; it is
# not absolute (attackers can nest encodings), which is why an LLM intent
# classifier and the tool/output boundaries sit behind it.

import base64
import binascii
import codecs
import re
import unicodedata

# A small homoglyph map (Cyrillic/Greek look-alikes → ASCII). Not exhaustive;
# NFKC handles most compatibility forms, this catches common visual spoofs.
_HOMOGLYPHS = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "к": "k", "м": "m", "н": "h", "т": "t", "в": "b", "і": "i", "ѕ": "s",
    "ԁ": "d", "ɡ": "g", "Ⅼ": "l", "ο": "o", "α": "a", "ρ": "p", "ѐ": "e",
}

_LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
    "@": "a", "$": "s", "!": "i",
})

_B64_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_HEX_RE = re.compile(r"(?:[0-9a-fA-F]{2}[\s:]?){8,}")


def _fold_homoglyphs(text: str) -> str:
    return "".join(_HOMOGLYPHS.get(ch, ch) for ch in text)


def _strip_intra_word_spacing(text: str) -> str:
    """Collapse single-letter runs without merging adjacent encoded words.

    Punctuation runs are collapsed before space runs, so
    ``s.y.s.t.e.m p-r-o-m-p-t`` retains its word boundary. Double spaces and
    newlines delimit space-separated words; ordinary hyphenated words survive.
    A wholly single-spaced letter stream has no recoverable word boundaries.
    """
    punctuation_run = r"(?<!\w)\w(?:[ \t]*[.\-][ \t]*\w){2,}(?!\w)"
    text = re.sub(punctuation_run,
                  lambda match: re.sub(r"[ .\-\t]", "", match.group()), text)
    space_run = r"(?<!\w)\w(?:[ \t]\w){2,}(?!\w)"
    return re.sub(space_run,
                  lambda match: re.sub(r"[ \t]", "", match.group()), text)


def canonical(text: str) -> str:
    """One normalised form: NFKC, homoglyph-folded, spacing-stripped, lowercase."""
    t = unicodedata.normalize("NFKC", text)
    t = _fold_homoglyphs(t)
    t = _strip_intra_word_spacing(t)
    return t.lower()


def _try_base64(text: str) -> list[str]:
    out = []
    for m in _B64_RE.findall(text):
        pad = m + "=" * (-len(m) % 4)
        try:
            dec = base64.b64decode(pad, validate=True).decode("utf-8", "ignore")
        except (binascii.Error, ValueError):
            continue
        if dec and sum(c.isprintable() for c in dec) / len(dec) > 0.8:
            out.append(dec)
    return out


def _try_hex(text: str) -> list[str]:
    out = []
    for m in _HEX_RE.findall(text):
        cleaned = re.sub(r"[\s:]", "", m)
        if len(cleaned) % 2:
            continue
        try:
            dec = bytes.fromhex(cleaned).decode("utf-8", "ignore")
        except ValueError:
            continue
        if dec and sum(c.isprintable() for c in dec) / len(dec) > 0.8:
            out.append(dec)
    return out


def _try_rot13(text: str) -> str:
    return codecs.decode(text, "rot_13")


def decoded_variants(text: str) -> list[str]:
    """
    Return distinct plaintext candidates a filter should inspect:
    the canonical form, a de-leetspeak pass, rot13, and any base64/hex payloads.
    """
    variants = [canonical(text)]
    variants.append(canonical(text).translate(_LEET))
    variants.append(canonical(_try_rot13(text)))
    for dec in _try_base64(text) + _try_hex(text):
        variants.append(canonical(dec))
    # de-dupe, preserve order
    seen, uniq = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq
