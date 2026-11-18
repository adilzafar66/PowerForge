"""Check AI unit proposals against literal evidence and registered unit symbols."""

import re

from powerforge_engineering_model.units import UNITS

VERSION = "source-unit-interpretation-v1"
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
_BASE_SYMBOLS = {"Ω": "[ΩΩ]", "VA": "(?i:VA)", "var": "(?i:var)", "Hz": "(?i:Hz)"}
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
_WORD = r"(?:(?i:volt-amperes?)|°?[^\W\d_]+(?:\.[^\W\d_]+)*\.?|[%℃℉])(?!\w)"
_OPERATOR = r"[/·⋅*×^-]|(?i:\bper\b)"
_TOKEN = re.compile(
    rf"(?<![^\W\d]|_){_WORD}(?:\s*(?:{_OPERATOR})\s*(?:[0-9]+\s*)?{_WORD})*"
    rf"(?:\s*[/·⋅*×^])?"
)
_SUFFIX_GAP = re.compile(r"\s*(?:[(\[]\s*)?")
_UNIT_OPERATORS = re.compile(_OPERATOR)
_SPACE = re.compile(r"\s+")
_UNCERTAIN = frozenset({"TRANSCRIPTION_CONFLICT", "AMBIGUOUS_OVERLAP"})


def _spelling(unit: str) -> re.Pattern[str]:
    if unit in _BASE_WORDS:
        base, prefix = unit, ""
    elif unit[1:] in _BASE_WORDS and unit[0] in _PREFIXES:
        base, prefix = unit[1:], unit[0]
    else:
        symbol = re.escape(unit).replace("Ω", "[ΩΩ]").replace("/", r"\s*/\s*")
        symbol = symbol.replace(r"\ ", r"\s+")
        if unit in {"°C", "°F"}:
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


def _header_tokens(quote: str, raw_unit: str):
    for match in _TOKEN.finditer(quote):
        token = match[0]
        if token == "in" and raw_unit != "in":
            # In "voltage in kV", the preposition is not an inch notation.
            next_token = _TOKEN.match(quote, _SUFFIX_GAP.match(quote, match.end()).end())
            if next_token and _looks_like_unit(_without_sentence_dot(next_token[0])):
                continue
        if (
            token == raw_unit
            or _looks_like_unit(_without_sentence_dot(token))
            or any(_looks_like_unit(part.strip()) for part in _UNIT_OPERATORS.split(token))
        ):
            yield token


def source_supports_unit(raw_value: str, raw_unit: str, proposed_unit: str, evidence) -> bool:
    """Require the literal unit and reject conflicting or uncertain unit evidence."""
    supported = False
    spelling = _SPELLINGS[proposed_unit]
    for fragment in evidence:
        if fragment["localization"] != "RESOLVED":
            continue
        role = fragment["role"]
        quote = fragment["quote"]
        if role == "VALUE":
            tokens = []
            for number in _SOURCE_NUMBER.finditer(quote):
                match = _TOKEN.match(quote, _SUFFIX_GAP.match(quote, number.end()).end())
                if match is not None:
                    # Whitespace-separated unit symbols can form a compound.
                    gap = _SPACE.match(quote, match.end())
                    following = _TOKEN.match(quote, gap.end()) if gap else None
                    if following and _looks_like_unit(_without_sentence_dot(following[0])):
                        return False
                    tokens.append((match[0].strip(), number[0] == raw_value))
        elif role in {"UNIT", "HEADER", "LABEL"}:
            tokens = [(token, True) for token in _header_tokens(quote, raw_unit)]
            if role == "UNIT" and not tokens:
                return False
        else:
            continue
        if tokens and _UNCERTAIN.intersection(fragment.get("source_issues", ())):
            return False
        for token, literal_context in tokens:
            if spelling.fullmatch(_without_sentence_dot(token)) is None:
                return False
            supported |= literal_context and raw_unit in (token, _without_sentence_dot(token))
    return supported
