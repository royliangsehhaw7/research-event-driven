from dataclasses import dataclass

@dataclass
class FetchResult:
    url:     str
    content: str         # page content as markdown-formatted text
    status:  str         # "ok" | "error"
    error:   str | None  # error message if status == "error", else None