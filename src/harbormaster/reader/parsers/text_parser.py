from .base import Parser


class TextParser(Parser):
    def parse(self, payload: bytes) -> str:
        return payload.decode("utf-8", errors="ignore")
