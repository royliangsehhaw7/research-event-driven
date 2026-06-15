# schemas/fetch_result.py
from dataclasses import dataclass

@dataclass
class FetchResult:
    url:     str
    content: str
    status:  str        # "ok" or "error"
    error:   str | None = None