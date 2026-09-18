from harbormaster.models import FieldValue


def extract_fields(text: str) -> list[FieldValue]:
    return [FieldValue(field="raw_text", value=text)]
