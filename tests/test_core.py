"""Core unit tests for obra — stdlib unittest, no network, no chromadb needed.

Run:  python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import asyncio
import unittest

# --- environment must be set BEFORE importing app modules ---
_TMP = tempfile.mkdtemp(prefix="obra_test_")
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["CHROMA_PATH"] = os.path.join(_TMP, "chroma")
os.environ.setdefault("GROQ_API_KEY", "gsk_test_key_for_chain")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm import detect_agent  # noqa: E402
from services.rich_format import detect_poll_intent, ensure_rich_structure, md_to_rich_html, estimate_complexity  # noqa: E402
from services.tools import execute_calculator  # noqa: E402
from services.sandbox import run_python  # noqa: E402
from services.file_tools import make_text_file, make_zip, _safe_name  # noqa: E402
from services.scheduler import _parse_interval_seconds, _parse_cron, _parse_schedule  # noqa: E402
from services.persona import quick_reply, polish_system, PERSONA  # noqa: E402
from services.i18n import t, language_system_hint, LANGS  # noqa: E402
from services.smart_context import suggest_title, force_file_delivery  # noqa: E402
from services import vector_memory  # noqa: E402
from services.db import db  # noqa: E402
from config.settings import settings  # noqa: E402


class TestAgentRouting(unittest.TestCase):
    def test_summarizer(self):
        self.assertEqual(detect_agent("summarize this article for me"), "summarizer")
        self.assertEqual(detect_agent("tldr please"), "summarizer")

    def test_terminal(self):
        self.assertEqual(detect_agent("run: print(2+2)"), "terminal")
        self.assertEqual(detect_agent("calculate 12*8"), "terminal")

    def test_coder(self):
        self.assertEqual(detect_agent("build me a full telegram bot with code"), "coder")
        self.assertEqual(detect_agent("fix this python bug in my script"), "coder")

    def test_researcher(self):
        self.assertEqual(detect_agent("what is the capital of France and why"), "researcher")
        self.assertEqual(detect_agent("latest news about AI today"), "researcher")

    def test_default(self):
        self.assertEqual(detect_agent("how are you today my friend"), "default")


class TestPollIntent(unittest.TestCase):
    def test_slash_after_question(self):
        r = detect_poll_intent("poll: Best color? red / blue / green")
        self.assertIsNotNone(r)
        q, opts = r
        self.assertIn("color", q)
        self.assertEqual(opts, ["red", "blue", "green"])

    def test_lettered(self):
        r = detect_poll_intent("vote: A) yes B) no C) maybe")
        self.assertIsNotNone(r)
        self.assertEqual(r[1], ["yes", "no", "maybe"])

    def test_options_keyword_no_colon(self):
        r = detect_poll_intent("create a poll about lunch with options pizza, pasta, salad")
        self.assertIsNotNone(r)
        q, opts = r
        self.assertEqual(opts, ["pizza", "pasta", "salad"])
        self.assertNotIn("with", q.split()[-1:] )

    def test_pick_or_list(self):
        r = detect_poll_intent("which one should I pick: pizza or pasta or salad")
        self.assertIsNotNone(r)
        self.assertEqual(r[1], ["pizza", "pasta", "salad"])

    def test_pipe_separated(self):
        r = detect_poll_intent("help me choose between tea | coffee | juice")
        self.assertIsNotNone(r)
        self.assertEqual(r[1], ["tea", "coffee", "juice"])

    def test_negative(self):
        self.assertIsNone(detect_poll_intent("can you vote in elections?"))
        self.assertIsNone(detect_poll_intent("just a normal message about polls maybe"))
        self.assertIsNone(detect_poll_intent("hello there"))


class TestRichFormat(unittest.TestCase):
    def test_ensure_structure_adds_title(self):
        out = ensure_rich_structure("x" * 400, user_text="q" * 50)
        self.assertTrue(out.startswith(">") or out.startswith("##"))  # quote or title
        self.assertIn("##", out)

    def test_md_to_rich_html_headings(self):
        html = md_to_rich_html("## Title\n\ntext with **bold** and `code`")
        self.assertIn("<h2>Title</h2>", html)
        self.assertIn("<b>bold</b>", html)
        self.assertIn("<code>code</code>", html)

    def test_md_to_rich_html_escapes(self):
        html = md_to_rich_html("## a < b & c")
        self.assertIn("&lt;", html)

    def test_complexity(self):
        self.assertEqual(estimate_complexity("hi"), "small")
        self.assertEqual(estimate_complexity("explain " + "x" * 500), "medium")
        self.assertEqual(estimate_complexity("write a comprehensive detailed report " + "x" * 1600), "big")


class TestCalculator(unittest.TestCase):
    def test_basic(self):
        r = asyncio.run(execute_calculator("2+2*3"))
        self.assertEqual(r, "8")

    def test_pow(self):
        r = asyncio.run(execute_calculator("2**10"))
        self.assertEqual(r, "1024")

    def test_rejects_code(self):
        r = asyncio.run(execute_calculator("__import__('os')"))
        self.assertIn("error", r.lower())


class TestSandbox(unittest.TestCase):
    def test_runs_print(self):
        out, ok = run_python("print(1+1)")
        self.assertTrue(ok)
        self.assertIn("2", out)

    def test_blocks_import(self):
        out, ok = run_python("import os")
        self.assertFalse(ok)
        self.assertIn("Blocked", out)

    def test_blocks_dunder(self):
        out, ok = run_python("x = __builtins__")
        self.assertFalse(ok)


class TestFileTools(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(_safe_name("../../etc/passwd"), "passwd.txt")  # path stripped, ext forced safe
        self.assertEqual(_safe_name("noext"), "noext.txt")
        self.assertEqual(_safe_name("evil.exe"), "evil.txt")
        self.assertNotIn("/", _safe_name("a/b/c.py"))

    def test_make_zip(self):
        fn, data = make_zip("proj", [{"filename": "a.py", "content": "print(1)"}])
        self.assertTrue(fn.endswith(".zip"))
        import io, zipfile
        zf = zipfile.ZipFile(io.BytesIO(data))
        self.assertEqual(zf.read("a.py").decode(), "print(1)")

    def test_make_text_file(self):
        fn, data = make_text_file("notes.md", "# hi")
        self.assertEqual(fn, "notes.md")
        self.assertEqual(data, b"# hi")


class TestSchedulerParsing(unittest.TestCase):
    def test_intervals(self):
        self.assertEqual(_parse_interval_seconds("every minute"), 60)
        self.assertEqual(_parse_interval_seconds("every 5 minutes do x"), 300)
        self.assertEqual(_parse_interval_seconds("every 2 hours ping"), 7200)
        self.assertIsNone(_parse_interval_seconds("every monday at 9am"))

    def test_cron_daily(self):
        c = _parse_cron("every day at 9:30 remind me")
        self.assertIsNotNone(c)

    def test_cron_weekday(self):
        c = _parse_cron("every monday at 8 remind me water")
        self.assertIsNotNone(c)

    def test_schedule_default(self):
        t = _parse_schedule("do something random without schedule words")
        self.assertIsNotNone(t)


class TestPersonaI18n(unittest.TestCase):
    def test_quick_reply(self):
        self.assertIsNotNone(quick_reply("hi"))
        self.assertIsNotNone(quick_reply("Namaste"))
        self.assertIsNone(quick_reply("write a poem about the sea and stars"))

    def test_polish_contains_persona(self):
        self.assertIn("obra", polish_system("base"))
        self.assertIn("secretary", polish_system("base", mode="secretary").lower())

    def test_i18n(self):
        self.assertIn("Hindi", t("hi", "lang_set", lang="Hindi"))
        self.assertEqual(t("xx", "done"), "Done.")
        self.assertEqual(language_system_hint("en"), "")
        self.assertIn("Hindi", language_system_hint("hi"))
        self.assertIn("hi", LANGS)

    def test_suggest_title(self):
        self.assertTrue(suggest_title("please help me build a bot") .startswith("help me") or len(suggest_title("please help me build a bot")) <= 60)

    def test_force_file_delivery(self):
        self.assertTrue(force_file_delivery("make a telegram bot"))
        self.assertFalse(force_file_delivery("hello how are you"))


class TestProviderChain(unittest.TestCase):
    def test_chain_built_from_env(self):
        chain = settings.provider_chain()
        names = [p["name"] for p in chain]
        self.assertIn("groq", names)  # GROQ_API_KEY set in env above
        # dedupe: no duplicate base+key
        keys = [(p["base_url"], p["api_key"][:16]) for p in chain]
        self.assertEqual(len(keys), len(set(keys)))

    def test_admin_list(self):
        self.assertEqual(settings.admin_list, [])
        settings.ADMIN_IDS = "123, 456, abc"
        self.assertEqual(settings.admin_list, [123, 456])


class TestDbAndMemoryFallback(unittest.TestCase):
    """chromadb is NOT installed in this env → memory must fall back to sqlite."""

    @classmethod
    def setUpClass(cls):
        asyncio.run(db.init())

    def test_history_order(self):
        cid = 999001
        asyncio.run(db.clear_history(cid))
        for i in range(5):
            asyncio.run(db.add_message(cid, "user", f"m{i}"))
        hist = asyncio.run(db.get_history(cid, limit=10))
        self.assertEqual([h["content"] for h in hist], ["m0", "m1", "m2", "m3", "m4"])

    def test_rate_limit(self):
        uid = 888001
        settings.RATE_LIMIT_MESSAGES = 3
        settings.RATE_LIMIT_WINDOW_SECONDS = 3600
        results = [asyncio.run(db.check_rate_limit(uid)) for _ in range(4)]
        self.assertEqual([r[0] for r in results], [True, True, True, False])
        settings.RATE_LIMIT_MESSAGES = 30

    def test_quotas(self):
        uid = 888002
        settings.DAILY_QUOTA = 2
        settings.MONTHLY_QUOTA = 1000
        ok1, _ = asyncio.run(db.check_quotas(uid))
        ok2, _ = asyncio.run(db.check_quotas(uid))
        ok3, reason = asyncio.run(db.check_quotas(uid))
        self.assertTrue(ok1 and ok2)
        self.assertFalse(ok3)
        self.assertIn("Daily", reason)
        settings.DAILY_QUOTA = 50

    def test_skills_pending_premium(self):
        uid = 888003
        asyncio.run(db.add_skill(uid, "test", "every minute say hi"))
        skills = asyncio.run(db.list_skills(uid))
        self.assertEqual(len(skills), 1)
        asyncio.run(db.save_pending("pid1", uid, 1, "gmail_send", {"to": "a@b.c"}))
        p = asyncio.run(db.pop_pending("pid1"))
        self.assertEqual(p["payload"]["to"], "a@b.c")
        self.assertIsNone(asyncio.run(db.pop_pending("pid1")))
        self.assertFalse(asyncio.run(db.is_premium(uid)))
        asyncio.run(db.grant_premium(uid, days=1, stars=50))
        self.assertTrue(asyncio.run(db.is_premium(uid)))
        n = asyncio.run(db.clear_pending_for_user(uid))
        self.assertGreaterEqual(n, 0)

    def test_vector_memory_fallback(self):
        # chromadb missing in test env → sqlite keyword fallback must kick in
        self.assertIsNone(vector_memory._get_collection())
        uid = 777001
        asyncio.run(vector_memory.add_memory(uid, "The user's favorite color is blue", metadata={"type": "auto_fact"}))
        asyncio.run(vector_memory.add_memory(uid, "User lives in Kerala, India", metadata={"type": "auto_fact"}))
        res = asyncio.run(vector_memory.search_memory(uid, "favorite color", n=5))
        self.assertTrue(any("blue" in r for r in res), res)
        asyncio.run(vector_memory.add_group_memory(-1001, "group likes pizza", {}))
        gres = asyncio.run(vector_memory.search_group_memory(-1001, "pizza", n=3))
        self.assertTrue(any("pizza" in r for r in gres), gres)
        asyncio.run(vector_memory.clear_user_vectors(uid))
        res2 = asyncio.run(vector_memory.search_memory(uid, "favorite color", n=5))
        self.assertFalse(any("blue" in r for r in res2))

    def test_local_embed(self):
        emb = vector_memory._local_embed(["hello world", "hello there"])
        self.assertEqual(len(emb[0]), 384)
        # similar texts should be closer than dissimilar
        import math
        def cos(a, b):
            return sum(x * y for x, y in zip(a, b))
        emb2 = vector_memory._local_embed(["completely different topic xyz"])
        self.assertGreater(cos(emb[0], emb[1]), cos(emb[0], emb2[0]))


class TestSettingsModelFor(unittest.TestCase):
    def test_model_for(self):
        self.assertTrue(settings.model_for("coder"))
        settings.MODEL_CODER = "my-coder-model"
        self.assertEqual(settings.model_for("coder"), "my-coder-model")


if __name__ == "__main__":
    unittest.main()
