"""Conservative extraction for labelled Chinese/English sample ID documents.

This is field extraction, not a document-authenticity or identity validator.
No values are invented, and the complete identifier never leaves this module.
"""

import re
import unicodedata
from datetime import date, datetime, timezone

from errors import OcrExtractionError


_ALIASES = {
    "name": r"姓\s*名|\b(?:Full\s+Name|Name)\b",
    "id_number": r"公民身份号码|公民身份证号码|身份证号码|身份证号|证件号码|证件号|\bID\s*(?:Number|No\.?)\b",
    "expiry_date": r"有效期限|有效期至|有效期|失效日期|到期日期|\b(?:Valid\s*(?:Until|Through|To)|Expiry\s*Date|Expiration\s*Date|Date\s*of\s*Expiry)\b",
    "issuing_authority": r"签发机关|簽發機關|发证机关|發證機關|\b(?:Issuing\s*Authority|Issued\s*By)\b",
    # These delimit unrelated values when OCR puts several fields on one line.
    "ignored": r"出生日期|出生|性别|民族|住址|签发日期|\b(?:Date\s*of\s*Birth|DOB|Gender|Sex|Address|Issue\s*Date|Nationality)\b",
}
_LABEL = re.compile(
    "|".join(f"(?P<{key}>{value})" for key, value in _ALIASES.items()), re.I
)
_DATE = re.compile(r"(?<!\d)(\d{4})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})\s*日?(?!\d)")
_ID = re.compile(r"(?:\d{17}[\dX]|\d{15})", re.I)
_ID_RUN = re.compile(r"(?<![0-9A-Z])[0-9X]+(?:[ \t]+[0-9X]+)*(?![0-9A-Z])", re.I)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r", "\n")
    text = text.replace("—", "-").replace("–", "-").replace("−", "-")
    # OCR often inserts spaces between individual Chinese characters.
    text = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", text)
    return text.strip()


def _fields(text: str) -> dict[str, list[str]]:
    matches = list(_LABEL.finditer(text))
    fields = {key: [] for key in _ALIASES}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fields[match.lastgroup].append(text[match.end():end].strip(" \t\n:：|"))
    return fields


def _single(values: list[str], field: str) -> str:
    unique = set(values)
    if not unique:
        raise OcrExtractionError(f"Missing or invalid field: {field}")
    if len(unique) != 1:
        raise OcrExtractionError(f"Ambiguous field: {field}")
    return unique.pop()


def _line_value(value: str) -> str:
    # A label may occupy its own OCR line; the next nonempty line is its value.
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


def _expiry(values: list[str]) -> str:
    candidates = []
    for value in values:
        # Interface v1.2 reserves this date for a lifetime-valid document.
        if re.search(r"长期|長期|permanent|lifetime|indefinite", value, re.I):
            candidates.append("9999-12-31")
            continue
        dates = []
        for match in _DATE.finditer(value):
            try:
                dates.append(date(*(int(part) for part in match.groups())))
            except ValueError:
                raise OcrExtractionError("Invalid field: expiry_date") from None
        if len(dates) == 1:
            candidates.append(dates[0].isoformat())
        elif len(dates) == 2:
            if dates[1] < dates[0]:
                raise OcrExtractionError("Invalid field: expiry_date (reversed range)")
            candidates.append(dates[1].isoformat())
        elif dates:
            raise OcrExtractionError("Ambiguous field: expiry_date")
    return _single(candidates, "expiry_date")


def extract_fields(text: str, *, today: date | None = None) -> dict:
    """Return exactly the five keys in interface §5.3, or raise the agreed error."""
    if not isinstance(text, str) or not text.strip():
        raise OcrExtractionError("No readable text; missing required OCR fields")
    text = _normalize(text)
    fields = _fields(text)

    names = []
    for value in fields["name"]:
        name = re.sub(r"\s+", " ", _line_value(value)).strip()
        if re.fullmatch(r"[\u3400-\u9fff·]{2,30}|[A-Za-z][A-Za-z .'-]{1,79}", name):
            names.append(name)
    name = _single(names, "name")

    # Prefer labelled identifiers. An unlabelled 15/18-character numeric ID is
    # accepted only when unique. Never silently repair O/0 or I/1 in an ID.
    identifiers = []
    regions = fields["id_number"] or [text]
    for region in regions:
        for match in _ID_RUN.finditer(region):
            tokens = match.group().upper().split()
            if all(_ID.fullmatch(token) for token in tokens):
                # Distinct complete IDs are ambiguous, not one concatenated ID.
                identifiers.extend(tokens)
            elif _ID.fullmatch(compact := "".join(tokens)):
                identifiers.append(compact)
    identifier = _single(identifiers, "id_number_masked")

    expiry = _expiry(fields["expiry_date"])
    authorities = []
    for value in fields["issuing_authority"]:
        authority = re.sub(r"\s+", " ", _line_value(value)).strip()
        if 2 <= len(authority) <= 120 and re.search(r"[A-Za-z\u3400-\u9fff]", authority):
            authorities.append(authority)
    authority = _single(authorities, "issuing_authority")
    current_date = today if today is not None else datetime.now(timezone.utc).date()
    return {
        "name": name,
        "id_number_masked": "*" * (len(identifier) - 4) + identifier[-4:],
        "expiry_date": expiry,
        "issuing_authority": authority,
        "id_valid": date.fromisoformat(expiry) >= current_date,
    }
