"""Rich Message structure + auto quote / poll intent detection (Bot API 10.1+)."""

from __future__ import annotations
import re
from typing import Optional, List, Tuple


RICH_SYSTEM_APPENDIX = """
## Telegram Rich Messages (ALWAYS use for non-trivial answers)

Your reply is rendered with Bot API Rich Messages (headings, tables, 32k chars).

MANDATORY structure when the answer is more than 2 short sentences:
1. Start with ## clear title
2. Use ### subsections
3. Bullet or numbered lists
4. Markdown tables when comparing options:
   | A | B |
   |---|---|
   | 1 | 2 |
5. Fenced code with language tag
6. Blockquotes for tips: > note
7. Collapsible extras:
   <details>
   <summary>Details</summary>
   more…
   </details>
8. Keep under 30,000 characters
9. Do NOT wrap the whole message in one giant code fence

Files: use create_file / create_zip for downloadable code.
Polls: use create_poll tool when user wants a vote.
"""


def estimate_complexity(text: str) -> str:
    n = len(text or "")
    low = (text or "").lower()
    big_kw = (
        "full code", "complete", "entire", "rewrite all", "long essay",
        "detailed report", "step by step", "comprehensive", "analyze deeply",
        "generate a full", "documentation", "refact",
    )
    if n > 1500 or any(k in low for k in big_kw):
        return "big"
    if n > 400 or any(k in low for k in ("explain", "code", "compare", "plan", "design")):
        return "medium"
    return "small"


def tokens_for_complexity(level: str) -> int:
    return {"small": 2048, "medium": 6144, "big": 16384}.get(level, 4096)


def detect_poll_intent(text: str) -> Optional[Tuple[str, List[str]]]:
    """
    Auto-detect simple poll requests.
    Returns (question, options) or None.
    Examples:
      - "poll: Best color? red / blue / green"
      - "vote: A) yes B) no C) maybe"
      - "create a poll about X with options a, b, c"
    """
    raw = (text or "").strip()
    low = raw.lower()

    if not any(k in low for k in ("poll", "vote", "which one should", "choose between")):
        return None

    # poll: question? a / b / c
    m = re.match(r"(?:create\s+)?(?:a\s+)?poll\s*[:\-]\s*(.+)$", raw, re.I | re.S)
    if not m:
        m = re.match(r"vote\s*[:\-]\s*(.+)$", raw, re.I | re.S)
    body = m.group(1).strip() if m else raw

    # Split question / options
    question = body
    options: List[str] = []

    # A) B) C) style
    parts = re.split(r"\s+(?=[A-D][\).:\-]\s*)", body)
    if len(parts) >= 3:
        question = parts[0].strip(" ?")
        for p in parts[1:]:
            opt = re.sub(r"^[A-D][\).:\-]\s*", "", p).strip()
            if opt:
                options.append(opt[:100])

    # slash or comma options after ?
    if len(options) < 2 and "?" in body:
        q, rest = body.split("?", 1)
        question = q.strip() + "?"
        for sep in ("/", "|", ",", " or "):
            if sep in rest:
                options = [x.strip()[:100] for x in rest.split(sep) if x.strip()]
                break

    # "options: a, b, c"
    if len(options) < 2:
        m2 = re.search(r"options?\s*[:\-]\s*(.+)$", body, re.I)
        if m2:
            options = [x.strip()[:100] for x in re.split(r"[,/|]", m2.group(1)) if x.strip()]
            question = body[: m2.start()].strip(" :-") or question

    options = [o for o in options if o and len(o) <= 100][:10]
    if len(options) >= 2 and question:
        return question[:300], options
    return None


def auto_quote_block(user_text: str, max_len: int = 280) -> str:
    """Build a markdown blockquote of the user's question."""
    q = (user_text or "").strip().replace("\r\n", "\n")
    if len(q) > max_len:
        q = q[: max_len - 1] + "…"
    lines = q.split("\n")
    return "\n".join("> " + (ln if ln else "") for ln in lines)


def ensure_rich_structure(text: str, user_text: str = "", auto_quote: bool = True) -> str:
    if not text:
        return text
    t = text.strip()

    # Auto-prepend quote of user for medium+ answers if not already quoting
    if auto_quote and user_text and len(t) > 200:
        if not t.lstrip().startswith(">") and "\n> " not in t[:400]:
            t = f"{auto_quote_block(user_text)}\n\n{t}"

    # Add title if long plain wall
    if not re.search(r"^#{1,6}\s", t, re.M) and len(t) > 280:
        t = f"## Answer\n\n{t}"

    # Promote "Note:" lines to blockquotes
    t = re.sub(r"(?m)^(Note|Important|Warning|Tip):\s*(.+)$", r"> **\1:** \2", t)

    t = re.sub(r"\n{4,}", "\n\n\n", t)
    return t


def md_to_rich_html(text: str) -> str:
    """Convert common markdown to Rich HTML tags for better client rendering."""
    import html as html_mod

    t = text
    # Protect code fences
    fences = []
    def _save_fence(m):
        fences.append(m.group(0))
        return f"\x00FENCE{len(fences)-1}\x00"
    t = re.sub(r"```[\s\S]*?```", _save_fence, t)

    # Escape then selective format — actually work on raw then escape non-tag parts is hard;
    # prefer light replacements that produce valid tags around already-safe content
    def esc(s: str) -> str:
        return html_mod.escape(s, quote=False)

    # Headings
    t = re.sub(r"(?m)^######\s+(.+)$", lambda m: f"<h6>{esc(m.group(1))}</h6>", t)
    t = re.sub(r"(?m)^#####\s+(.+)$", lambda m: f"<h5>{esc(m.group(1))}</h5>", t)
    t = re.sub(r"(?m)^####\s+(.+)$", lambda m: f"<h4>{esc(m.group(1))}</h4>", t)
    t = re.sub(r"(?m)^###\s+(.+)$", lambda m: f"<h3>{esc(m.group(1))}</h3>", t)
    t = re.sub(r"(?m)^##\s+(.+)$", lambda m: f"<h2>{esc(m.group(1))}</h2>", t)
    t = re.sub(r"(?m)^#\s+(.+)$", lambda m: f"<h1>{esc(m.group(1))}</h1>", t)

    # Blockquotes (multiline consecutive)
    def _bq(m):
        body = m.group(0)
        lines = [re.sub(r"^>\s?", "", ln) for ln in body.strip().split("\n")]
        inner = "<br/>".join(esc(x) for x in lines)
        return f"<blockquote>{inner}</blockquote>"
    t = re.sub(r"(?m)((?:^>.*\n?)+)", _bq, t)

    # HR
    t = re.sub(r"(?m)^---+$", "<hr/>", t)

    # Inline
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<b>{esc(m.group(1))}</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", lambda m: f"<i>{esc(m.group(1))}</i>", t)
    t = re.sub(r"``([^`]+)``", lambda m: f"<code>{esc(m.group(1))}</code>", t)
    t = re.sub(r"`([^`]+)`", lambda m: f"<code>{esc(m.group(1))}</code>", t)
    t = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", t)

    # Restore fences as pre
    for i, f in enumerate(fences):
        lang = ""
        m = re.match(r"```(\w*)\n?([\s\S]*?)```", f)
        if m:
            lang, code = m.group(1), m.group(2)
            block = f'<pre><code class="language-{lang}">{esc(code)}</code></pre>' if lang else f"<pre><code>{esc(code)}</code></pre>"
        else:
            block = f"<pre><code>{esc(f)}</code></pre>"
        t = t.replace(f"\x00FENCE{i}\x00", block)

    # Newlines to br for remaining plain lines (avoid double inside tags)
    # Keep simple: only outside tags is hard; leave newlines — Telegram HTML accepts <br/>
    t = re.sub(r"(?<!>)\n(?!<)", "<br/>\n", t)
    return t
