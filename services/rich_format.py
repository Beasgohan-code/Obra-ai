from __future__ import annotations
import re
from typing import Optional, List, Tuple

RICH_SYSTEM_APPENDIX = """
## OUTPUT FORMAT (Telegram Rich Messages — REQUIRED)
Your reply is delivered with Telegram sendRichMessage.
ALWAYS structure non-trivial answers like this:

## Title
Short intro paragraph.

### Section
- bullet points

| Column A | Column B |
|----------|----------|
| value    | value    |

```language
code if needed
```

> Important callout

Rules:
- Start with a ## heading for answers longer than 2 sentences
- Use a markdown table when comparing 2+ things
- Never send a plain wall of text for multi-part answers
"""

def estimate_complexity(text: str) -> str:
    n = len(text or "")
    low = (text or "").lower()
    if n > 800 or any(k in low for k in ("full code","complete","comprehensive","detailed report","make a","build a","create a","downloader","telegram bot")):
        return "big"
    if n > 400 or any(k in low for k in ("explain","code","compare","plan","design")):
        return "medium"
    return "small"

def detect_poll_intent(text: str) -> Optional[Tuple[str, List[str]]]:
    raw = (text or "").strip()
    low = raw.lower()
    if not any(k in low for k in ("poll","vote","choose between")):
        return None
    m = re.match(r"(?:create\s+)?(?:a\s+)?poll\s*[:\-]\s*(.+)$", raw, re.I|re.S)
    if not m:
        m = re.match(r"vote\s*[:\-]\s*(.+)$", raw, re.I|re.S)
    body = m.group(1).strip() if m else raw
    question, options = body, []
    if "?" in body:
        q, rest = body.split("?", 1)
        question = q.strip()+"?"
        for sep in ("/", "|", ",", " or "):
            if sep in rest:
                options = [x.strip()[:100] for x in rest.split(sep) if x.strip()]
                break
    options = [o for o in options if o][:10]
    if len(options) >= 2 and question:
        return question[:300], options
    return None

def auto_quote_block(user_text: str, max_len: int = 280) -> str:
    q = (user_text or "").strip()
    if len(q) > max_len:
        q = q[:max_len-1]+"…"
    return "\n".join("> "+(ln if ln else "") for ln in q.split("\n"))

def ensure_rich_structure(text: str, user_text: str = "", auto_quote: bool = True) -> str:
    if not text:
        return text
    t = text.strip()
    if auto_quote and user_text and len(t) > 200 and not t.lstrip().startswith(">"):
        t = f"{auto_quote_block(user_text)}\n\n{t}"
    if not re.search(r"^#{1,6}\s", t, re.M) and len(t) > 120:
        t = f"## Answer\n\n{t}"
    t = re.sub(r"(?m)^(Note|Important|Warning|Tip):\s*(.+)$", r"> **\1:** \2", t)
    return re.sub(r"\n{4,}", "\n\n\n", t)
