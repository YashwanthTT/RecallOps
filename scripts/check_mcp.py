"""Exercise the real npm stdio server; no mocked MCP or Hindsight responses."""
import asyncio
import argparse
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Also call briefing, reflection and probe")
    options = parser.parse_args()
    params = StdioServerParameters(command="npm", args=["run", "--silent", "mcp"],
        cwd=str(Path(__file__).resolve().parents[1]), env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 8
            assert all(tool.outputSchema for tool in tools.tools)
            print(json.dumps({"server": initialized.serverInfo.model_dump(),
                              "tools": [tool.name for tool in tools.tools]}))
            for tool, args in [("list_recovery_actions", {}), ("hindsight_status", {})]:
                result = await session.call_tool(tool, args)
                assert not result.isError
                assert result.structuredContent is not None
                assert json.loads(result.content[0].text) == result.structuredContent
                print(json.dumps({"tool": tool, "result": result.structuredContent}))
            recalled = await session.call_tool("recall_incidents", {"query": "checkout-api outage rollback"})
            print(json.dumps({"tool": "recall_incidents", "isError": recalled.isError,
                              "content": [c.model_dump() for c in recalled.content]}))
            if options.full:
                for name, arguments in [
                    ("incident_briefing", {"service": "payment-gateway", "alert": "Payment gateway outage — elevated errors and latency in the payment processing service"}),
                    ("reflect_on_history", {"question": "What caused payments-gateway incident INC-2057 and how was it resolved? Cite retained evidence."}),
                    ("probe_service", {"url": "http://localhost:8080/health", "service": "checkout-api"}),
                ]:
                    result = await session.call_tool(name, arguments)
                    print(json.dumps({"tool": name, "isError": result.isError,
                                      "result": result.structuredContent or [c.model_dump() for c in result.content]}), flush=True)
                    if result.isError:
                        raise RuntimeError(f"{name} failed; see result above")
            if recalled.isError:
                raise RuntimeError("Hindsight recall failed; MCP transport works but memory is unavailable")
            await session.send_ping()
            print("PASS: npm launch, initialize, discovery, output schemas, structured/text results, ping")


if __name__ == "__main__":
    asyncio.run(main())
