"""Bot wiring tests — dispatcher structure, routers, allowed updates, handlers."""
import os
import sys
import inspect
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="obra_bot_")
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ["DB_PATH"] = os.path.join(_TMP, "bot.db")
os.environ["CHROMA_PATH"] = os.path.join(_TMP, "chroma")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DP = None


def get_dp():
    global _DP
    if _DP is None:
        from bot.main import build_dispatcher
        _DP = build_dispatcher()
    return _DP


class TestDispatcher(unittest.TestCase):
    def test_routers_registered_in_safe_order(self):
        from bot.main import ALLOWED_UPDATES
        dp = get_dp()
        names = [getattr(r, "name", "") or "" for r in dp.sub_routers]
        for expected in ("secretary", "extras", "webapp", "payments"):
            self.assertIn(expected, names)
        # unnamed routers (commands, chat, media, inline, callbacks) get hex names;
        # secretary (deep link) and extras must come before them so their specific
        # handlers win over the generic chat/catch-all handlers
        first_generic = next(i for i, n in enumerate(names) if n.startswith("0x"))
        self.assertLess(names.index("secretary"), first_generic)
        self.assertLess(names.index("extras"), first_generic)
        # no duplicate update types
        self.assertEqual(len(ALLOWED_UPDATES), len(set(ALLOWED_UPDATES)))
        for needed in ("message", "callback_query", "inline_query",
                       "business_message", "pre_checkout_query"):
            self.assertIn(needed, ALLOWED_UPDATES)

    def test_command_handlers_present(self):
        import handlers.commands as cmds_mod
        src = inspect.getsource(cmds_mod)
        for c in ("start", "help", "clear", "lang", "memory", "forget", "skill",
                  "setkey", "project", "tts", "usage", "cancel", "search"):
            self.assertIn(f'Command("{c}"', src, f"missing /{c}")

    def test_main_module(self):
        import bot.main as m
        self.assertTrue(callable(m.main))
        self.assertTrue(callable(m.build_dispatcher))


if __name__ == "__main__":
    unittest.main()
