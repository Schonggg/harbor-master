from pydantic import BaseModel


class VerdictCard(BaseModel):
    status: str
    reason: str
