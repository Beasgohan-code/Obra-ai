LANGS = {"en":"English","hi":"Hindi","es":"Spanish","ru":"Russian","ar":"Arabic","bn":"Bengali","pt":"Portuguese","fr":"French","de":"German"}
_MSG = {
    "en": {"rate_limit":"⏳ Slow down a bit.","quota":"Daily quota reached.","done":"Done.","cancelled":"Cancelled.","lang_set":"Language set to {lang}."},
}
def t(lang, key, **kw):
    d = _MSG.get(lang) or _MSG["en"]
    return (d.get(key) or _MSG["en"].get(key) or key).format(**kw)
def language_system_hint(lang: str) -> str:
    name = LANGS.get(lang, lang)
    if lang and lang != "en":
        return f"\nReply in {name} ({lang}) unless user asks otherwise."
    return ""
