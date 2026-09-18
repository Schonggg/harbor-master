from harbormaster.models import Evidence


def make_evidence(raw_text: str, source: str = "text") -> Evidence:
    return Evidence(raw_text=raw_text, source=source)
