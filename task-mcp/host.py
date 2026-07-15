"""Host — 할 일 관리 MCP 서버를 가져다 쓴다.

calc-mcp/host.py 와 구조가 같다. (서버만 바뀌었을 뿐 호스트 로직은 재사용)

두 가지 모드:
  1) 직접 호출 모드  : LLM 없이 내가 도구를 지정해 호출   (python host.py)
  2) LLM 에이전트 모드: Ollama가 자연어를 보고 도구를 결정  (python host.py --llm)

구조는 Claude Desktop 과 같다:
  설정 파일 읽기 → 서버마다 Client 생성 → 도구 통합 → 호출 라우팅
"""

import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

CONFIG_PATH = Path("mcp_config.json")


class Host:
    """여러 MCP 서버를 등록·관리하고 도구를 통합 제공한다."""

    def __init__(self) -> None:
        self._clients: dict[str, Client] = {}   # 서버이름 → Client
        self._tool_owner: dict[str, str] = {}   # 도구이름 → 서버이름 (라우팅 테이블)
        self._tools: list = []                  # 통합 도구 목록
        self._stack = AsyncExitStack()

    async def __aenter__(self):
        await self._stack.__aenter__()
        servers = self._load_config()
        await self._connect_all(servers)
        await self._collect_tools()
        return self

    async def __aexit__(self, *exc):
        await self._stack.__aexit__(*exc)

    # ── 설정 읽기 ────────────────────────────────────
    @staticmethod
    def _load_config() -> dict:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f).get("mcpServers", {})

    # ── 서버 연결 (서버마다 Client 1개) ───────────────
    async def _connect_all(self, servers: dict) -> None:
        for name, conf in servers.items():
            command = conf["command"]
            if command == "python":
                command = sys.executable  # 현재 파이썬으로 교체

            transport = StdioTransport(
                command=command,
                args=conf.get("args", []),
                env=conf.get("env"),
                keep_alive=False,
            )
            client = Client(transport)
            await self._stack.enter_async_context(client)
            self._clients[name] = client

    # ── 도구 통합 + 라우팅 테이블 구축 ────────────────
    async def _collect_tools(self) -> None:
        for server_name, client in self._clients.items():
            for t in await client.list_tools():
                if t.name in self._tool_owner:
                    continue  # 이름 충돌 시 먼저 등록된 것 유지
                self._tool_owner[t.name] = server_name
                self._tools.append(t)

    # ── 공개 API ─────────────────────────────────────
    @property
    def tools(self) -> list:
        """LLM에게 넘길 통합 도구 목록."""
        return self._tools

    async def call_tool(self, name: str, args: dict):
        """도구 이름을 보고 담당 서버로 라우팅해 실행한다."""
        server = self._tool_owner.get(name)
        if server is None:
            raise ValueError(f"'{name}' 도구를 가진 서버가 없습니다.")
        return await self._clients[server].call_tool(name, args)

    async def read_resource(self, uri: str):
        """리소스를 읽는다. (첫 번째 서버에서 시도)"""
        for client in self._clients.values():
            try:
                return await client.read_resource(uri)
            except Exception:
                continue
        raise ValueError(f"'{uri}' 리소스를 찾을 수 없습니다.")


# ══════════════════════════════════════════════════════
#  모드 1: 직접 호출 (LLM 없음)
# ══════════════════════════════════════════════════════

async def run_direct() -> None:
    print("=" * 58)
    print("할 일 관리 MCP — 직접 호출 모드 (LLM 없음)")
    print("=" * 58)

    async with Host() as host:
        print(f"\n등록된 도구 {len(host.tools)}개:")
        for t in host.tools:
            print(f"  • {t.name}")

        print("\n── 할 일 추가 ──")
        for args in [
            {"title": "MCP 발표 자료 만들기", "priority": "high", "due": "2026-07-20"},
            {"title": "이메일 회신", "priority": "normal"},
            {"title": "커피 원두 주문", "priority": "low"},
        ]:
            r = await host.call_tool("add_task", args)
            print(f"  + #{r.data['id']} {r.data['title']} ({r.data['priority']})")

        print("\n── 완료 처리 ──")
        r = await host.call_tool("complete_task", {"task_id": 2})
        print(f"  #{r.data['id']} → {r.data['status']}")

        print("\n── 오류 처리 (없는 항목) ──")
        try:
            await host.call_tool("complete_task", {"task_id": 999})
        except Exception as e:
            print(f"  complete_task(999) → 차단됨: {str(e).splitlines()[-1]}")

        print("\n── 리소스 읽기 (미완료 목록) ──")
        r = await host.read_resource("tasks://pending")
        print(r[0].text)

        print("\n── 리소스 읽기 (통계) ──")
        r = await host.read_resource("tasks://stats")
        print(f"  {r[0].text}")


# ══════════════════════════════════════════════════════
#  모드 2: LLM 에이전트 (Ollama)
# ══════════════════════════════════════════════════════

SYSTEM_PROMPT = (
    "너는 할 일(todo)을 관리하는 한국어 어시스턴트다. "
    "할 일을 추가·조회·완료·삭제할 때는 반드시 제공된 도구를 사용해라. "
    "도구 결과를 받으면 그걸 바탕으로 간결하게 한국어로 답해라. "
    "오늘 날짜는 2026-07-14 이다."
)
MODEL = "qwen3"


def to_ollama_tools(mcp_tools: list) -> list[dict]:
    """MCP 도구 스키마 → Ollama tools 형식으로 변환."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": (t.description or "").splitlines()[0],
                "parameters": t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


async def ask(host: Host, ollama_tools: list, question: str) -> None:
    import ollama

    print(f"\n{'─' * 58}")
    print(f"🙋 {question}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    resp = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
    msg = resp["message"]
    messages.append(msg)

    calls = msg.get("tool_calls") or []
    if not calls:
        print(f"🤖 {msg.get('content', '').strip()}")
        return

    for call in calls:
        fn = call["function"]
        name, args = fn["name"], fn["arguments"]
        if isinstance(args, str):
            args = json.loads(args)

        print(f"🧠 LLM 판단 → {name}({args})")
        result = await host.call_tool(name, args)   # ← MCP 실행
        print(f"🔧 실행 결과 → {result.data}")

        messages.append(
            {"role": "tool", "tool_name": name, "content": str(result.data)}
        )

    final = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
    print(f"🤖 {final['message']['content'].strip()}")


async def run_llm() -> None:
    print("=" * 58)
    print("할 일 관리 MCP — LLM 에이전트 모드 (Ollama)")
    print("=" * 58)

    async with Host() as host:
        ollama_tools = to_ollama_tools(host.tools)
        print(f"모델: {MODEL} / 도구 {len(host.tools)}개")

        await ask(host, ollama_tools, "발표 자료 만들기를 높은 우선순위로 20일까지 할 일에 추가해줘.")
        await ask(host, ollama_tools, "지금 남은 할 일 뭐 있어?")
        await ask(host, ollama_tools, "발표 자료 만들기 끝냈어. 완료 처리해줘.")


if __name__ == "__main__":
    if "--llm" in sys.argv:
        asyncio.run(run_llm())
    else:
        asyncio.run(run_direct())
