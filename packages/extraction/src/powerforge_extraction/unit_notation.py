"""Check AI unit proposals against literal evidence and registered unit symbols."""

import re

from powerforge_engineering_model.units import UNITS

VERSION = "source-unit-interpretation-v3"
SCALAR = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_SOURCE_NUMBER = re.compile(rf"(?<![\w.,+/−-]){SCALAR.pattern}(?![\d.,])")

# Unit names and abbreviations describe base symbols. Prefixes are checked
# independently so changing capitalization cannot switch milli and mega.
_BASE_WORDS = {
    "V": "volts?",
    "A": "amps?|amperes?",
    "VA": "volt-?amperes?",
    "W": "watts?",
    "var": "vars?",
    "Ω": "ohms?",
    "m": "met(?:er|re)s?",
    "s": "secs?|seconds?",
    "Hz": "hertz",
    "F": "farads?",
    "H": "henr(?:y|ies)",
    "in": "inch(?:es)?",
    "ft": "feet|foot",
    "%": "percent|pct",
}
_PREFIXES = {
    "n": ("n", "nano"),
    "µ": ("[µμu]", "micro"),
    "m": ("m", "milli"),
    "c": ("c", "centi"),
    "k": ("[kK]", "kilo"),
    "M": ("M", "mega"),
}
_BASE_SYMBOLS = {
    "Ω": "[ΩΩ]",
    "VA": "(?i:VA)",
    "var": "(?i:var)",
    "Hz": "(?i:Hz)",
    "in": r"""(?:in|["″”])""",
    "ft": r"(?:ft|['′’])",
}
_LENGTH_MARKS = frozenset({"'", '"', "′", "″", "’", "”"})
_CONTEXT_SENSITIVE_UNITS = _LENGTH_MARKS | {"in"}
_BASE_PATTERN = "|".join(
    _BASE_SYMBOLS.get(base, re.escape(base)) for base in _BASE_WORDS if base != "%"
)
# Recognize competing SI spellings even if that prefix is unsupported by the
# registry. Examples include mA and MΩ, which must still block a conflicting claim.
_SI_PREFIX_SYMBOL = r"[qryzafpnµμumcdhkKMGTPEZYRQ]|da"
_SI_SYMBOL = re.compile(rf"(?:{_SI_PREFIX_SYMBOL})?(?:{_BASE_PATTERN})")
_SI_NAME = re.compile(
    rf"(?:{_SI_PREFIX_SYMBOL}|"
    r"(?i:quecto|ronto|yocto|zepto|atto|femto|pico|nano|micro|milli|centi|deci|"
    r"deca|hecto|kilo|mega|giga|tera|peta|exa|zetta|yotta|ronna|quetta))?"
    rf"(?i:{'|'.join(_BASE_WORDS.values())})"
)

# Keep slash and multiplication expressions together. A supported unit at the
# start of an unsupported compound is not evidence for that supported unit.
_WORD = r"""(?:(?i:volt-amperes?)|°?[^\W\d_]+(?:\.[^\W\d_]+)*\.?|[%℃℉'"′″’”])(?!\w)"""
_MULTIPLY_OR_ALTERNATIVE = r"[·⋅*×^-]|(?i:\bor\b)"
_OPERATOR = rf"/|(?i:\bper\b)|{_MULTIPLY_OR_ALTERNATIVE}"
_HORIZONTAL_SPACE = r"[^\S\r\n]"
_DENOMINATOR = rf"(?:{SCALAR.pattern}\s*)?{_WORD}"
_COMPOUND_PART = rf"(?:/|(?i:\bper\b))\s*(?:\(\s*{_DENOMINATOR}\s*\)|{_DENOMINATOR})"
_MIXED_LENGTH = (
    rf"(?:{_BASE_SYMBOLS['ft']}|(?i:feet|foot)){_HORIZONTAL_SPACE}*(?:-{_HORIZONTAL_SPACE}*)?"
    rf"{SCALAR.pattern}{_HORIZONTAL_SPACE}*"
    rf"(?:{_BASE_SYMBOLS['in']}|(?i:inch(?:es)?))(?!\w)"
)
# Degrees followed by arcminutes or arcseconds are a combined angular
# expression, even though the smaller units use the same marks as lengths.
_COMPOUND_ANGLE = (
    rf"""°(?:{_HORIZONTAL_SPACE}*{SCALAR.pattern}{_HORIZONTAL_SPACE}*['′"″’”]){{1,2}}(?!\w)"""
)
_TOKEN = re.compile(
    rf"(?<![^\W\d]|_)(?:{_MIXED_LENGTH}|{_COMPOUND_ANGLE}|"
    rf"{_WORD}(?:\s*(?:{_COMPOUND_PART}|(?:{_MULTIPLY_OR_ALTERNATIVE})\s*{_WORD}))*"
    rf"(?:\s*[/·⋅*×^])?)"
)
_VALUE_PART = re.compile(rf"(?P<number>{_SOURCE_NUMBER.pattern})|{_TOKEN.pattern}")
_SUFFIX_GAP = re.compile(rf"{_HORIZONTAL_SPACE}*(?:[(\[]{_HORIZONTAL_SPACE}*)?")
_DESCRIPTOR_GAP = re.compile(rf"(?i:sym\.?|asym\.?|rms){_HORIZONTAL_SPACE}+")
_PARENTHESIZED_NUMBER = re.compile(r"\(\s*[+-]?(?:[0-9]|\.[0-9])")
_UNIT_OPERATORS = re.compile(_OPERATOR)
_SPACE = re.compile(rf"{_HORIZONTAL_SPACE}+")
_UNIT_LABEL = re.compile(r"\bunits?\s*[:=]\s*$", re.IGNORECASE)
_UNCERTAIN = frozenset({"TRANSCRIPTION_CONFLICT", "AMBIGUOUS_OVERLAP"})


def _spelling(unit: str) -> re.Pattern[str]:
    if unit in _BASE_WORDS:
        base, prefix = unit, ""
    elif unit[1:] in _BASE_WORDS and unit[0] in _PREFIXES:
        base, prefix = unit[1:], unit[0]
    else:
        symbol = re.escape(unit).replace("Ω", "[ΩΩ]").replace("/", r"\s*/\s*")
        symbol = symbol.replace(r"\ ", r"\s+")
        if unit in {"hp", "rpm"}:
            symbol = f"(?i:{symbol})"
        elif unit in {"°C", "°F"}:
            symbol = f"(?:{symbol}|{'℃' if unit == '°C' else '℉'})"
        return re.compile(symbol)
    symbol = _BASE_SYMBOLS.get(base, re.escape(base))
    words = f"(?i:{_BASE_WORDS[base]})"
    if not prefix:
        return re.compile(rf"(?:{symbol}|{words})")
    prefix_symbol, prefix_word = _PREFIXES[prefix]
    return re.compile(rf"(?:{prefix_symbol}(?:{symbol}|{words})|(?i:{prefix_word}){words})")


_SPELLINGS = {unit: _spelling(unit) for unit in UNITS}


def matches_proposal(raw_unit: str, proposed_unit: str, supported_units: tuple[str, ...]) -> bool:
    """Check a proposal's dimension, prefix and spelling without selecting a unit."""
    return (
        proposed_unit in supported_units
        and proposed_unit in _SPELLINGS
        and (
            raw_unit == proposed_unit
            if raw_unit in UNITS
            else _SPELLINGS[proposed_unit].fullmatch(raw_unit) is not None
        )
    )


def _looks_like_unit(token: str) -> bool:
    return (
        token in UNITS
        or _SI_SYMBOL.fullmatch(token) is not None
        or _SI_NAME.fullmatch(token) is not None
        or any(pattern.fullmatch(token) for pattern in _SPELLINGS.values())
    )


def _without_sentence_dot(token: str) -> str:
    return token if token == "p.u." else token.removesuffix(".")


def _ends_unit_expression(quote: str, end: int) -> bool:
    after = quote[end:].lstrip(" \t")
    return not after or after.startswith((",", ";", ")", "]", "\r", "\n"))


def _explicit_unit_designation(quote: str, match: re.Match[str]) -> bool:
    before = quote[: match.start()].rstrip()
    after = quote[match.end() :].lstrip()
    return (
        before.endswith("(")
        and after.startswith(")")
        or before.endswith("[")
        and after.startswith("]")
        or (_UNIT_LABEL.search(before) is not None and _ends_unit_expression(quote, match.end()))
    )


def _length_suffix_is_explicit(quote: str, number: re.Match[str], unit: re.Match[str]) -> bool:
    spelling = _without_sentence_dot(unit[0])
    if spelling not in _CONTEXT_SENSITIVE_UNITS or _explicit_unit_designation(quote, unit):
        return True
    if spelling == "in":
        # A following object can make this "in" an English preposition.
        return _ends_unit_expression(quote, unit.end()) or bool(
            _PARENTHESIZED_NUMBER.match(quote[unit.end() :].lstrip())
        )
    openings = {'"': '"', "'": "'", "”": "“", "’": "‘"}
    if spelling in openings:
        # A closing prose quote is not a linear measurement mark.
        close, open_ = re.escape(spelling), re.escape(openings[spelling])
        if re.search(rf"(?<!\w){open_}(?=\s*\w)[^{close}\n]*$", quote[: number.end()]):
            return False
        if spelling in {"’", "”"}:
            # Typeset quotation marks need more context than a standalone number.
            before = quote[: number.start()].rstrip()
            after = quote[unit.end() :].lstrip()
            return unit.start() == number.end() and (
                bool(_PARENTHESIZED_NUMBER.match(after))
                or (before.endswith("(") and after.startswith(")"))
            )
        return unit.start() == number.end() or _ends_unit_expression(quote, unit.end())
    return True


def _source_units(quote: str):
    # Scan both bare unit expressions and numbered quantities. Consuming a
    # complete unit token keeps internal denominator numbers out of the scan.
    cursor = 0
    while part := _VALUE_PART.search(quote, cursor):
        cursor = part.end()
        if part["number"] is None:
            yield None, part
            continue
        start = _SUFFIX_GAP.match(quote, cursor).end()
        descriptor = _DESCRIPTOR_GAP.match(quote, start)
        unit = _TOKEN.match(quote, descriptor.end() if descriptor else start)
        if unit is not None:
            cursor = unit.end()
            yield part, unit


def numeric_unit_spans(text: str):
    """Expose numbered unit expressions for exact proposal validation."""
    for number, unit in _source_units(text):
        if number is not None and _length_suffix_is_explicit(text, number, unit):
            yield number.span(), unit.span(), _without_sentence_dot(unit[0])


def is_unit_notation(token: str) -> bool:
    return _looks_like_unit(token) or any(
        _looks_like_unit(part.strip()) for part in _UNIT_OPERATORS.split(token)
    )


def _unit_tokens(quote: str, raw_value: str, raw_unit: str, role: str):
    for number, unit in _source_units(quote):
        token = unit[0]
        if number is None:
            if role == "VALUE":
                continue
            bare = _without_sentence_dot(token)
            if bare in _CONTEXT_SENSITIVE_UNITS and not _explicit_unit_designation(quote, unit):
                continue
            if (
                token == raw_unit
                or _looks_like_unit(bare)
                or any(_looks_like_unit(part.strip()) for part in _UNIT_OPERATORS.split(token))
            ):
                yield token
            continue
        if number[0] != raw_value or not _length_suffix_is_explicit(quote, number, unit):
            continue
        # Whitespace-separated symbols may form an unsupported compound.
        gap = _SPACE.match(quote, unit.end())
        following = _TOKEN.match(quote, gap.end()) if gap else None
        following_unit = _without_sentence_dot(following[0]) if following else None
        if (
            following_unit
            and following_unit not in _CONTEXT_SENSITIVE_UNITS
            and _looks_like_unit(following_unit)
        ):
            yield quote[unit.start() : following.end()]
        else:
            yield token


def source_supports_unit(
    raw_value: str,
    raw_unit: str,
    proposed_unit: str,
    evidence,
    *,
    same_value_alternate_units: frozenset[str] = frozenset(),
) -> bool:
    """Require the literal unit and reject conflicting or uncertain unit evidence."""
    supported = False
    spelling = _SPELLINGS[proposed_unit]
    for fragment in evidence:
        if fragment["localization"] != "RESOLVED":
            continue
        role = fragment["role"]
        if role not in {"VALUE", "UNIT", "HEADER", "LABEL"}:
            continue
        tokens = list(_unit_tokens(fragment["quote"], raw_value, raw_unit, role))
        if role == "UNIT" and not tokens:
            return False
        if tokens and _UNCERTAIN.intersection(fragment.get("source_issues", ())):
            return False
        for token in tokens:
            bare = _without_sentence_dot(token)
            if spelling.fullmatch(bare) is None and bare not in same_value_alternate_units:
                return False
            supported |= raw_unit in (token, bare)
    return supported
