"""MCP 서버 예제 — 도구 2개와 리소스 1개를 노출한다.

각 함수가 호출될 때 stderr에 로그를 남겨서,
Client가 실제로 서버 쪽 코드를 실행시켰다는 걸 눈으로 확인할 수 있게 한다.
(stdout은 MCP 프로토콜 통신 채널이라 로그는 반드시 stderr로 보낸다)
"""

import sys

# Windows에서 stdio 기본 인코딩(cp949)과 UTF-8 충돌로 한글 통신 시
# 파이프가 깨지는 문제 방지. 표준 입출력을 UTF-8로 강제 재설정한다.
# (Python 3.7+ 에서 reconfigure 사용 가능)
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from fastmcp import FastMCP

mcp = FastMCP("Demo Server")


def log(msg: str) -> None:
    """서버 내부 동작을 stderr로 출력한다."""
    print(f"[SERVER] {msg}", file=sys.stderr, flush=True)


@mcp.tool
def add(a: int, b: int) -> int:
    """두 정수를 더한다."""
    log(f"add(a={a}, b={b}) 실행됨")
    return a + b


@mcp.tool
def greet(name: str) -> str:
    """이름을 받아 한국어 인사말을 만든다."""
    log(f"greet(name={name!r}) 실행됨")
    return f"안녕하세요, {name}님!"


@mcp.resource("config://app")
def get_config() -> str:
    """앱 설정 정보를 반환하는 읽기 전용 리소스."""
    log("config://app 리소스 읽힘")
    return "app_name=Demo, version=1.0, env=local"


if __name__ == "__main__":
    log("서버 시작 (stdio 대기 중)")
    mcp.run()  # 기본 transport = stdio
