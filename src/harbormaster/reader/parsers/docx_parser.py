from .base import Parser


class DocxParser(Parser):
    def parse(self, payload: bytes) -> str:
        return payload.decode("utf-8", errors="ignore")
