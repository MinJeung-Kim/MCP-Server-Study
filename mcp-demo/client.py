"""MCP 클라이언트 예제 — 서버에 붙어서 3단계 흐름을 밟는다.

  ① 연결   : Client가 server.py를 하위 프로세스로 띄우고 handshake
  ② 조회   : tools/list, resources/list 로 능력 목록을 받아온다
  ③ 실행   : tools/call, resources/read 로 실제 기능을 호출한다

`async with Client(...)` 블록에 들어가는 순간 ①이 자동으로 일어난다.
(버전 협상, initialize, initialized 까지 FastMCP가 알아서 처리)
"""

import asyncio
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


def line(title: str) -> None:
    print(f"\n{'=' * 55}\n{title}\n{'=' * 55}")


async def main() -> None:
    # 서버를 어떤 명령으로 띄울지 명시적으로 지정한다.
    # sys.executable = 지금 client.py를 돌리고 있는 바로 그 파이썬의 절대경로.
    # 이 파이썬으로 서버도 띄우므로 uv/venv/시스템 파이썬 불일치가 원천 차단된다.
    # 서버가 뜨다 죽으면 그 에러가 Connection closed에 가려진다.
    # log_file로 서버의 stderr를 파일에 받아서 진짜 원인을 확인한다.
    transport = StdioTransport(
        command=sys.executable,
        args=["server.py"],
        log_file=Path("server_stderr.log"),
        keep_alive=False,
    )
    client = Client(transport)

    line("① 연결 (handshake)")
    async with client:  # ← 여기서 initialize/initialized 자동 수행
        print("Client ↔ Server 연결 완료 (버전·기능 협상 끝)")

        line("② 조회 (discovery)")
        tools = await client.list_tools()
        print(f"사용 가능한 도구 {len(tools)}개:")
        for t in tools:
            params = list(t.inputSchema.get("properties", {}).keys())
            print(f"  - {t.name}{tuple(params)}  :: {t.description}")

        resources = await client.list_resources()
        print(f"\n사용 가능한 리소스 {len(resources)}개:")
        for r in resources:
            print(f"  - {r.uri}  :: {r.description}")

        line("③ 실행 (execution)")

        print("→ tools/call: add(a=3, b=5)")
        r1 = await client.call_tool("add", {"a": 3, "b": 5})
        print(f"← 결과: {r1.data}")

        print("\n→ tools/call: greet(name='Roxie')")
        r2 = await client.call_tool("greet", {"name": "Roxie"})
        print(f"← 결과: {r2.data}")

        print("\n→ resources/read: config://app")
        r3 = await client.read_resource("config://app")
        print(f"← 결과: {r3[0].text}")

    line("연결 종료")
    print("async with 블록을 벗어나면 서버 프로세스도 정리된다")


if __name__ == "__main__":
    asyncio.run(main())
