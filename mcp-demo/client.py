"""세 가지 primitive를 모두 시연하는 클라이언트.

각 primitive마다:
  - 목록 조회 (discovery)
  - 실제 사용 (tool 실행 / resource 읽기 / prompt 렌더링)
을 순서대로 보여준다.
"""

import asyncio
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


def sec(title: str) -> None:
    print(f"\n{'═' * 58}\n {title}\n{'═' * 58}")


async def main() -> None:
    from pathlib import Path
    transport = StdioTransport(
        command=sys.executable,
        args=["server.py"],
        log_file=Path("server_stderr.log"),
        keep_alive=False,
    )

    async with Client(transport) as client:
        print("Client ↔ Server 연결 완료")

        # ── 1. TOOLS ──────────────────────────────────────
        sec("1. TOOLS (행동)")
        tools = await client.list_tools()
        print(f"등록된 도구 {len(tools)}개:")
        for t in tools:
            print(f"  • {t.name} — {t.description.splitlines()[0]}")

        print("\n▶ add(3, 5)")
        r = await client.call_tool("add", {"a": 3, "b": 5})
        print(f"  = {r.data}")

        print("\n▶ calculate_1rm(weight=100, reps=5)")
        r = await client.call_tool("calculate_1rm", {"weight": 100, "reps": 5})
        print(f"  = {r.data}")

        # ── 2. RESOURCES ──────────────────────────────────
        sec("2. RESOURCES (읽기)")
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        print(f"정적 리소스 {len(resources)}개:")
        for res in resources:
            print(f"  • {res.uri} — {res.description.splitlines()[0]}")
        print(f"리소스 템플릿 {len(templates)}개:")
        for tmpl in templates:
            print(f"  • {tmpl.uriTemplate} — {tmpl.description.splitlines()[0]}")

        print("\n▶ read config://app")
        r = await client.read_resource("config://app")
        print(f"  = {r[0].text}")

        print("\n▶ read server://time (동적)")
        r = await client.read_resource("server://time")
        print(f"  = {r[0].text}")

        print("\n▶ read member://1 (템플릿에 ID 주입)")
        r = await client.read_resource("member://1")
        print(f"  = {r[0].text}")

        # ── 3. PROMPTS ────────────────────────────────────
        sec("3. PROMPTS (템플릿)")
        prompts = await client.list_prompts()
        print(f"등록된 프롬프트 {len(prompts)}개:")
        for p in prompts:
            args = [a.name for a in (p.arguments or [])]
            print(f"  • {p.name}{tuple(args)} — {p.description.splitlines()[0]}")

        print("\n▶ render summarize(text=...)")
        r = await client.get_prompt("summarize", {"text": "MCP는 AI를 위한 표준 연결 규격이다. 도구와 데이터를 붙인다."})
        for m in r.messages:
            print(f"  [{m.role}] {m.content.text}")

        print("\n▶ render code_review(language='python', code=...)")
        r = await client.get_prompt(
            "code_review",
            {"language": "python", "code": "def f(x): return x*2"},
        )
        for m in r.messages:
            print(f"  [{m.role}] {m.content.text}")

    sec("완료 — 세 primitive 모두 시연됨")


if __name__ == "__main__":
    asyncio.run(main())
