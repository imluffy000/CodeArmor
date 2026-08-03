from pydantic import BaseModel


class Issue(BaseModel):
    file: str
    severity: str
    category: str
    issue: str
    suggestion: str
    code_snippet: str | None = None
    suggestion_snippet: str | None = None