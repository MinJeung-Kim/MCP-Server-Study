"""Host — 계산기 MCP 서버를 가져다 쓴다.

두 가지 모드를 지원한다:
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
    print("계산기 MCP — 직접 호출 모드 (LLM 없음)")
    print("=" * 58)

    async with Host() as host:
        print(f"\n등록된 도구 {len(host.tools)}개:")
        for t in host.tools:
            print(f"  • {t.name}")

        print("\n── 계산 실행 ──")
        for name, args in [
            ("add", {"a": 3, "b": 5}),
            ("multiply", {"a": 7, "b": 6}),
            ("evaluate", {"expression": "(2 + 3) * 4"}),
            ("power", {"base": 2, "exponent": 10}),
        ]:
            r = await host.call_tool(name, args)
            print(f"  {name}({args}) = {r.data}")

        print("\n── 오류 처리 ──")
        try:
            await host.call_tool("divide", {"a": 1, "b": 0})
        except Exception as e:
            print(f"  divide(1, 0) → 차단됨: {str(e).splitlines()[0]}")

        print("\n── 리소스 읽기 (계산 기록) ──")
        r = await host.read_resource("calc://history")
        print(r[0].text)


# ══════════════════════════════════════════════════════
#  모드 2: LLM 에이전트 (Ollama)
# ══════════════════════════════════════════════════════

SYSTEM_PROMPT = (
    "너는 계산기 도구를 쓸 수 있는 한국어 어시스턴트다. "
    "계산이 필요하면 반드시 도구를 사용해라. 절대 암산하지 마라. "
    "도구 결과를 받으면 그걸 바탕으로 간결하게 한국어로 답해라."
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
        print(f"🔧 계산 결과 → {result.data}")

        messages.append(
            {"role": "tool", "tool_name": name, "content": str(result.data)}
        )

    final = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
    print(f"🤖 {final['message']['content'].strip()}")


async def run_llm() -> None:
    print("=" * 58)
    print("계산기 MCP — LLM 에이전트 모드 (Ollama)")
    print("=" * 58)

    async with Host() as host:
        ollama_tools = to_ollama_tools(host.tools)
        print(f"모델: {MODEL} / 도구 {len(host.tools)}개")

        await ask(host, ollama_tools, "3 더하기 5는?")
        await ask(host, ollama_tools, "2의 10제곱은 얼마야?")
        await ask(host, ollama_tools, "사과가 12개씩 든 상자가 7개 있어. 총 몇 개야?")


if __name__ == "__main__":
    if "--llm" in sys.argv:
        asyncio.run(run_llm())
    else:
        asyncio.run(run_direct())
