import pytest

from powerforge_api.storage.disposition import build_content_disposition


def test_plain_ascii_filename() -> None:
    assert build_content_disposition("report.pdf") == (
        "attachment; filename=\"report.pdf\"; filename*=UTF-8''report.pdf"
    )


def test_inline_disposition() -> None:
    assert build_content_disposition("a.png", "inline").startswith("inline; ")


def test_spaces_are_percent_encoded_in_extended_form() -> None:
    value = build_content_disposition("Single Line Diagram.pdf")
    assert 'filename="Single Line Diagram.pdf"' in value
    assert "filename*=UTF-8''Single%20Line%20Diagram.pdf" in value


def test_non_ascii_uses_fallback_and_rfc5987() -> None:
    value = build_content_disposition("Schéma électrique.pdf")
    assert 'filename="Sch_ma _lectrique.pdf"' in value
    assert "filename*=UTF-8''Sch%C3%A9ma%20%C3%A9lectrique.pdf" in value
    value.encode("ascii")


def test_quotes_and_backslashes_are_escaped_in_fallback() -> None:
    value = build_content_disposition('a"b\\c.pdf')
    assert 'filename="a\\"b\\\\c.pdf"' in value
    assert "filename*=UTF-8''a%22b%5Cc.pdf" in value


@pytest.mark.parametrize("name", ["a\r\nSet-Cookie: x=1.pdf", "a\nb.pdf", "a\x00b.pdf", "a\tb.pdf"])
def test_control_characters_cannot_inject_headers(name: str) -> None:
    value = build_content_disposition(name)
    assert "\r" not in value
    assert "\n" not in value
    assert "\x00" not in value
    assert "\t" not in value


def test_bidi_override_is_removed() -> None:
    value = build_content_disposition("invoice\u202egnp.exe")
    assert "%E2%80%AE" not in value
    assert "\u202e" not in value


@pytest.mark.parametrize("name", ["", "   ", "\r\n"])
def test_empty_name_falls_back_to_download(name: str) -> None:
    assert 'filename="download"' in build_content_disposition(name)


def test_lone_surrogate_does_not_crash() -> None:
    value = build_content_disposition("bad\ud800name.pdf")
    value.encode("ascii")


def test_unsupported_disposition_rejected() -> None:
    with pytest.raises(ValueError):
        build_content_disposition("a.pdf", "form-data")  # type: ignore[arg-type]
