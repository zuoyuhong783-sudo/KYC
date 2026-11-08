from datetime import date

import pytest

from errors import OcrExtractionError
from extraction import extract_fields


TODAY = date(2026, 11, 6)
TEXT = "姓名 张三\n公民身份号码 000000200001011234\n签发机关 测试市公安局\n有效期限 2020.05.01-2030.05.01"
EXPECTED = {
    "name": "张三", "id_number_masked": "**************1234",
    "expiry_date": "2030-05-01", "issuing_authority": "测试市公安局", "id_valid": True,
}


def test_chinese_range_and_exact_contract():
    assert extract_fields(TEXT, today=TODAY) == EXPECTED


def test_english_labels_and_single_expiry():
    text = "Full Name: ZHANG SAN\nID Number: 000000200001011234\nExpiry Date: 2030/5/1\nIssuing Authority: XX Public Security Bureau"
    result = extract_fields(text, today=TODAY)
    assert result == {**EXPECTED, "name": "ZHANG SAN", "issuing_authority": "XX Public Security Bureau"}


def test_labels_on_separate_lines_and_spaced_chinese():
    text = "姓 名\n张 三\n公 民 身 份 号 码\n000000200001011234\n签 发 机 关\n测 试 市 公 安 局\n有 效 期 限\n2020年05月01日 至 2030年05月01日"
    assert extract_fields(text, today=TODAY) == EXPECTED


def test_multiple_labels_on_one_line_ignore_birthday():
    text = TEXT.replace("\n", " ").replace("公民身份号码", "性别 男 出生 2000年01月01日 公民身份号码")
    assert extract_fields(text, today=TODAY) == EXPECTED


@pytest.mark.parametrize("expiry,valid", [("2026-11-05", False), ("2026-11-06", True), ("2026-11-07", True)])
def test_expiry_boundary(expiry, valid):
    text = TEXT.replace("2020.05.01-2030.05.01", expiry)
    assert extract_fields(text, today=TODAY)["id_valid"] is valid


@pytest.mark.parametrize("identifier,masked", [
    ("00000020000101123X", "**************123X"),
    ("000000000001234", "***********1234"),
    ("000000 20000101 1234", "**************1234"),
    ("000000200001011 234", "**************1234"),
])
def test_identifier_forms(identifier, masked):
    assert extract_fields(TEXT.replace("000000200001011234", identifier), today=TODAY)["id_number_masked"] == masked


def test_nfkc_fullwidth_digits():
    text = TEXT.translate(str.maketrans("0123456789", "０１２３４５６７８９"))
    assert extract_fields(text, today=TODAY) == EXPECTED


@pytest.mark.parametrize("line,field", [(0, "name"), (1, "id_number_masked"), (2, "issuing_authority"), (3, "expiry_date")])
def test_missing_fields_are_errors_without_pii(line, field):
    text = "\n".join(value for i, value in enumerate(TEXT.splitlines()) if i != line)
    with pytest.raises(OcrExtractionError, match=field) as error:
        extract_fields(text, today=TODAY)
    assert "000000200001011234" not in str(error.value)
    assert "张三" not in str(error.value)


@pytest.mark.parametrize("expiry", ["2030-02-30", "长期", "2020.05.01-长期", "permanent", "2030.05.01-2020.05.01", "2030.1.1 2031.1.1 2032.1.1"])
def test_invalid_or_unsupported_expiry(expiry):
    with pytest.raises(OcrExtractionError, match="expiry_date"):
        extract_fields(TEXT.replace("2020.05.01-2030.05.01", expiry), today=TODAY)


def test_conflicting_identifiers_rejected():
    with pytest.raises(OcrExtractionError, match="Ambiguous"):
        extract_fields(TEXT.replace("000000200001011234", "000000200001011234 000000200001015678"), today=TODAY)


@pytest.mark.parametrize("text", ["", "   ", "unrelated text", None])
def test_non_document_rejected(text):
    with pytest.raises(OcrExtractionError):
        extract_fields(text, today=TODAY)


def test_no_identifier_ocr_character_guessing():
    with pytest.raises(OcrExtractionError, match="id_number_masked"):
        extract_fields(TEXT.replace("000000200001011234", "OOOOOO200001011234"), today=TODAY)


def test_identifier_with_trailing_extra_digits_is_not_truncated():
    with pytest.raises(OcrExtractionError, match="id_number_masked"):
        extract_fields(TEXT.replace("000000200001011234", "000000200001011234 5"), today=TODAY)


def test_english_label_does_not_match_inside_a_value():
    text = "Name: TEST SURNAME\nID Number: 000000200001011234\nExpiry Date: 2030-05-01\nIssuing Authority: MIDDLESEX BUREAU"
    result = extract_fields(text, today=TODAY)
    assert result["name"] == "TEST SURNAME"
    assert result["issuing_authority"] == "MIDDLESEX BUREAU"
