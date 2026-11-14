import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.integrations import mcp_server as server
from src.core.memory import Memory


class ToolTests(unittest.TestCase):
    def test_briefing_reflection_and_retention(self):
        with patch.object(server, "MemoryStore") as cls, patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            store = cls.return_value
            store.connect.return_value = "hindsight"
            store.bank_id = "test-bank"
            store.recall.return_value = []
            store.reflect.return_value = "Historical pattern with evidence"
            for name, args in [
                ("incident_briefing", {"service": "payment-gateway", "alert": "errors"}),
                ("reflect_on_history", {"question": "past causes?"}),
                ("retain_resolution", {"incident_id": "TEST-1", "service": "test", "summary": "Verified test outcome"}),
            ]:
                result = asyncio.run(server.mcp.call_tool(name, args))
                self.assertIn("test-bank", str(result))
            self.assertEqual(store.retain.call_args.kwargs["document_id"], "mcp-resolution:TEST-1")
            self.assertEqual(store.retain.call_args.kwargs["update_mode"], "replace")

    def test_sync_client_runs_outside_transport_loop(self):
        def connect():
            async def probe():
                return "hindsight"
            return asyncio.run(probe())
        with patch.object(server, "MemoryStore") as cls:
            cls.return_value.connect.side_effect = connect
            cls.return_value.recall.return_value = [Memory("INC-loop-safe", 1)]
            cls.return_value.bank_id = "test"
            result = asyncio.run(server.mcp.call_tool("recall_incidents", {"query": "test"}))
            self.assertIn("INC-loop-safe", str(result))

    def test_recall_uses_real_store_contract(self):
        with patch.object(server, "MemoryStore") as cls:
            store = cls.return_value
            store.connect.return_value = "hindsight"
            store.recall.return_value = [Memory("INC-123 rollback", 0.9)]
            result = server.recall_incidents("checkout", 3)
            self.assertEqual(result["memories"][0]["text"], "INC-123 rollback")
            store.recall.assert_called_once_with("checkout", 3)
            store.close.assert_called_once()

    def test_unavailable_memory_is_error(self):
        with patch.object(server, "MemoryStore") as cls:
            cls.return_value.connect.return_value = "unavailable"
            cls.return_value.error = "offline"
            with self.assertRaisesRegex(RuntimeError, "offline"):
                server.recall_incidents("checkout")
            cls.return_value.close.assert_called_once()

    def test_action_gate_allowlist_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "actions.json"
            config.write_text(json.dumps({"diagnostic": {
                "description": "test diagnostic", "command": [sys.executable, "-c", "print('healthy')"]}}))
            with patch.dict(os.environ, {"RECALLOPS_ACTIONS_FILE": str(config), "RECALLOPS_ENABLE_ACTIONS": "false"}):
                with self.assertRaisesRegex(ValueError, "disabled"):
                    server.execute_recovery_action("diagnostic")
                os.environ["RECALLOPS_ENABLE_ACTIONS"] = "true"
                with self.assertRaisesRegex(ValueError, "Unknown"):
                    server.execute_recovery_action("arbitrary shell command")
                result = server.execute_recovery_action("diagnostic")
                self.assertEqual(result["exit_code"], 0)
                self.assertEqual(result["stdout"].strip(), "healthy")

    def test_stdio_protocol(self):
        async def check():
            params = StdioServerParameters(command="npm", args=["run", "--silent", "mcp"],
                cwd=str(server.ROOT), env={"UV_CACHE_DIR": os.getenv("UV_CACHE_DIR", str(Path.home() / ".cache/uv"))})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual(len(tools.tools), 8)
                    self.assertTrue(all(tool.outputSchema for tool in tools.tools))
                    result = await session.call_tool("list_recovery_actions", {})
                    self.assertFalse(result.isError)
                    self.assertEqual(json.loads(result.content[0].text), result.structuredContent)
                    # Invalid inputs must fail at the protocol boundary.
                    invalid = await session.call_tool("recall_incidents", {"query": "test", "limit": 100})
                    self.assertTrue(invalid.isError)
                    # Execution failures are tool errors; the connection stays usable.
                    failed = await session.call_tool("execute_recovery_action", {"action": "unknown-test-action"})
                    self.assertTrue(failed.isError)
                    await session.send_ping()
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
