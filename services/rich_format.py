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
      - "create a poll about lunch with options pizza, pasta, salad"
      - "which one should I pick: pizza or pasta or salad"
      - "help me choose between tea | coffee | juice"
    """
    raw = (text or "").strip()
    low = raw.lower()

    if not any(k in low for k in ("poll", "vote", "which one should", "choose between", "pick between", "help me choose", "help me pick")):
        return None

    body = raw
    # strip leading verbs: "create a poll about …", "make me a vote - …"
    m = re.match(
        r"^(?:please\s+)?(?:can you\s+|could you\s+)?(?:create|make|start|send|give)\s+(?:me\s+)?(?:a\s+)?(?:poll|vote)\s*(?:about|for|on)?\s*[:\-]?\s*(.*)$",
        raw, re.I | re.S,
    )
    if m and m.group(1).strip():
        body = m.group(1).strip()
    else:
        m2 = re.match(r"^(?:poll|vote)\s*[:\-]\s*(.*)$", raw, re.I | re.S)
        if m2:
            body = m2.group(1).strip()

    question = body
    options: List[str] = []

    # 1) lettered options: "A) yes B) no" / "a. yes b. no"
    lettered = re.split(r"\s+(?=[A-Za-z][\)\.\:]\s)", body)
    if len(lettered) >= 2 and re.match(r"^[A-Za-z][\)\.\:]\s", lettered[-1]):
        if re.match(r"^[A-Za-z][\)\.\:]\s", lettered[0]):
            question = "Vote"
            opts_raw = lettered
        else:
            question = lettered[0].strip(" ?")
            opts_raw = lettered[1:]
        options = [re.sub(r"^[A-Za-z][\)\.\:]\s*", "", p).strip()[:100] for p in opts_raw]
        options = [o for o in options if o]

    # 2) "options: a, b, c" / "options a, b, c" / "with options a / b / c"
    if len(options) < 2:
        m2 = re.search(r"(?:with\s+)?options?\s*[:\-]?\s+(.+)$", body, re.I)
        if m2:
            opts = [x.strip()[:100] for x in re.split(r"[,/|]|\s+or\s+", m2.group(1), flags=re.I) if x.strip()]
            if len(opts) >= 2:
                options = opts
                q = re.sub(r"\s+with$", "", body[: m2.start()].strip(" :-"), flags=re.I)
                question = q or question

    # 3) pipe separated: "question | a | b | c" (also "choose between a | b | c")
    if len(options) < 2 and "|" in body:
        parts = [x.strip() for x in body.split("|") if x.strip()]
        if len(parts) >= 3:
            head = parts[0]
            m4 = re.match(r"^(.*\b(?:choose|pick)(?:\s+between)?)\s+(\S+)$", head, re.I)
            if m4 and len(parts) >= 3:
                question = m4.group(1).strip(" ?")
                options = [m4.group(2)[:100]] + [p[:100] for p in parts[1:]]
            else:
                question = head.rstrip(" ?")
                options = [p[:100] for p in parts[1:]]

    # 4) options after "?": "best color? red / blue / green"
    if len(options) < 2 and "?" in body:
        q, rest = body.split("?", 1)
        for sep in ("/", "|", ",", " or "):
            if sep in rest:
                options = [x.strip()[:100] for x in rest.split(sep) if x.strip()]
                question = q.strip() + "?"
                break

    # 5) "pick: X or Y or Z" / "choose between X and Y" style
    if len(options) < 2:
        m3 = re.search(r"(?:choose between|pick between)\s+(.+)$", body, re.I)
        if m3:
            options = [x.strip()[:100] for x in re.split(r"\s+or\s+|\s+and\s+|,", m3.group(1), flags=re.I) if x.strip()]
            question = body[: m3.start()].strip(" ?") or "Choose one"
    if len(options) < 2 and ":" in body:
        head, tail = body.split(":", 1)
        if re.search(r"\s+or\s+|,", tail, re.I):
            options = [x.strip()[:100] for x in re.split(r",|\s+or\s+", tail, flags=re.I) if x.strip()]
            question = head.strip(" ?") or "Choose one"

    options = [o for o in options if o and len(o) <= 100][:10]
    question = (question or "").strip()[:300]
    if len(options) >= 2 and question:
        return question, options
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
