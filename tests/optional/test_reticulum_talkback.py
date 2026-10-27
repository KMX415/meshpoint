"""Pure-function tests for talkback.py -- command parsing and reply text,
no RNS/LXMF/asyncio involved (see that module's docstring for why)."""

from __future__ import annotations

import unittest

from apps.reticulum.backend import talkback


class TestParseCommand(unittest.TestCase):
    def test_recognizes_each_dotted_command_case_insensitively(self) -> None:
        for cmd in ("help", "ping", "stats", "spacestate", "events", "nodes"):
            with self.subTest(cmd=cmd):
                self.assertEqual(talkback.parse_command("." + cmd.upper()), cmd)

    def test_bare_word_without_dot_is_not_a_command(self) -> None:
        # The whole point of the dot prefix: a human typing a plain word
        # that happens to match a command name must not trigger a reply.
        for cmd in ("help", "ping", "stats", "spacestate", "events", "nodes"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(talkback.parse_command(cmd))

    def test_only_first_word_matters(self) -> None:
        self.assertEqual(talkback.parse_command(".ping me back please"), "ping")

    def test_strips_surrounding_whitespace(self) -> None:
        self.assertEqual(talkback.parse_command("  .stats  "), "stats")

    def test_unrecognized_dotted_word_returns_none(self) -> None:
        self.assertIsNone(talkback.parse_command(".banana"))

    def test_unrecognized_text_returns_none(self) -> None:
        self.assertIsNone(talkback.parse_command("hey, are you around?"))

    def test_empty_and_blank_return_none(self) -> None:
        self.assertIsNone(talkback.parse_command(""))
        self.assertIsNone(talkback.parse_command("   "))

    def test_lone_dot_returns_none(self) -> None:
        self.assertIsNone(talkback.parse_command("."))


class TestBuildReply(unittest.TestCase):
    def _reply(self, command: str, **overrides) -> str:
        kwargs = dict(
            node_name="TestNode",
            stats={},
            spaceapi_configured=False,
            spaceapi={},
            events_configured=False,
            events=[],
        )
        kwargs.update(overrides)
        return talkback.build_reply(command, **kwargs)

    def test_ping_is_pong(self) -> None:
        self.assertEqual(self._reply("ping"), "pong")

    def test_help_lists_commands_with_a_dot_prefix(self) -> None:
        reply = self._reply("help")
        self.assertIn(".stats", reply)
        self.assertIn(".ping", reply)

    def test_help_omits_unconfigured_commands(self) -> None:
        reply = self._reply("help")
        self.assertIn("stats", reply)
        self.assertNotIn("spacestate", reply)
        self.assertNotIn("events", reply)

    def test_help_includes_configured_commands(self) -> None:
        reply = self._reply("help", spaceapi_configured=True, events_configured=True)
        self.assertIn("spacestate", reply)
        self.assertIn("events", reply)

    def test_help_reply_never_starts_with_a_command_word(self) -> None:
        # Loop-safety invariant documented in talkback.py's module docstring:
        # a reply must never itself be parseable as a new command.
        reply = self._reply("help", spaceapi_configured=True, events_configured=True)
        self.assertIsNone(talkback.parse_command(reply))

    def test_stats_includes_present_fields_only(self) -> None:
        reply = self._reply("stats", stats={"version": "0.8.1", "uptime": "3d"})
        self.assertIn("TestNode", reply)
        self.assertIn("0.8.1", reply)
        self.assertIn("3d", reply)
        self.assertNotIn("Reticulum peers heard", reply)

    def test_stats_with_empty_dict_still_names_the_node(self) -> None:
        reply = self._reply("stats")
        self.assertEqual(reply, "TestNode")

    def test_spacestate_not_configured(self) -> None:
        reply = self._reply("spacestate", spaceapi_configured=False)
        self.assertIn("isn't configured", reply)

    def test_spacestate_open(self) -> None:
        reply = self._reply(
            "spacestate", spaceapi_configured=True,
            spaceapi={"space": "TechInc", "open": True},
        )
        self.assertIn("TechInc", reply)
        self.assertIn("OPEN", reply)

    def test_spacestate_closed(self) -> None:
        reply = self._reply(
            "spacestate", spaceapi_configured=True,
            spaceapi={"space": "TechInc", "open": False},
        )
        self.assertIn("CLOSED", reply)

    def test_spacestate_unknown_when_never_fetched(self) -> None:
        reply = self._reply("spacestate", spaceapi_configured=True, spaceapi={})
        self.assertIn("unknown", reply)
        self.assertIn("not fetched yet", reply)

    def test_events_not_configured(self) -> None:
        reply = self._reply("events", events_configured=False)
        self.assertIn("No events feed", reply)

    def test_events_configured_but_empty(self) -> None:
        reply = self._reply("events", events_configured=True, events=[])
        self.assertEqual(reply, "No upcoming events.")

    def test_events_lists_summaries_and_truncates(self) -> None:
        events = [{"summary": f"Talk {i}", "start": __import__("datetime").datetime(2026, 1, i + 1)}
                  for i in range(7)]
        reply = self._reply("events", events_configured=True, events=events)
        self.assertIn("Talk 0", reply)
        self.assertIn("and 2 more", reply)

    def test_nodes_empty(self) -> None:
        self.assertEqual(self._reply("nodes"), "No NomadNet nodes heard yet.")

    def test_nodes_lists_display_names_and_truncates(self) -> None:
        recent = [{"display_name": f"node{i}", "destination_hash": f"{i:032x}"} for i in range(20)]
        reply = self._reply("nodes", stats={"recent_nodes": recent})
        self.assertIn("node0", reply)
        self.assertIn("and 5 more", reply)

    def test_nodes_falls_back_to_hash_without_display_name(self) -> None:
        recent = [{"destination_hash": "ab" * 16}]
        reply = self._reply("nodes", stats={"recent_nodes": recent})
        self.assertIn("ab" * 16, reply)


if __name__ == "__main__":
    unittest.main()
