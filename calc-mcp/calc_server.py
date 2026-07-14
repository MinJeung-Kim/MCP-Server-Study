"""계산기 MCP 서버 — 기존 계산기 앱을 MCP로 노출한다.

핵심: calculator.py 는 한 줄도 고치지 않았다.
      import 해서 쓰기만 한다. MCP는 얇은 '껍데기(wrapper)'일 뿐이다.

노출하는 것:
  Tools     — 계산 실행 (add, subtract, ..., evaluate, clear_history)
  Resources — 계산 기록 조회 (calc://history)
  Prompts   — 계산 도우미 프롬프트 템플릿
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from fastmcp import FastMCP

from calculator import Calculator, CalculatorError  # ← 기존 앱을 그대로 사용

mcp = FastMCP("Calculator Server")

# 서버가 살아있는 동안 유지되는 계산기 인스턴스 (히스토리가 쌓인다)
_calc = Calculator()


# ══════════════════════════════════════════════════════
#  TOOLS — 계산을 실행한다
# ══════════════════════════════════════════════════════

@mcp.tool
def add(a: float, b: float) -> float:
    """두 수를 더한다."""
    return _calc.add(a, b)


@mcp.tool
def subtract(a: float, b: float) -> float:
    """첫 번째 수에서 두 번째 수를 뺀다."""
    return _calc.subtract(a, b)


@mcp.tool
def multiply(a: float, b: float) -> float:
    """두 수를 곱한다."""
    return _calc.multiply(a, b)


@mcp.tool
def divide(a: float, b: float) -> float:
    """첫 번째 수를 두 번째 수로 나눈다. 0으로 나누면 오류."""
    try:
        return _calc.divide(a, b)
    except CalculatorError as e:
        # 앱의 예외를 MCP가 이해할 수 있는 형태로 올려보낸다
        raise ValueError(str(e)) from e


@mcp.tool
def power(base: float, exponent: float) -> float:
    """거듭제곱을 계산한다. (base의 exponent 제곱)"""
    return _calc.power(base, exponent)


@mcp.tool
def evaluate(expression: str) -> float:
    """수식 문자열을 계산한다.

    괄호와 사칙연산, 거듭제곱(**)을 지원한다.
    예: "(2 + 3) * 4", "2 ** 10", "10 / 4"
    """
    try:
        return _calc.evaluate(expression)
    except CalculatorError as e:
        raise ValueError(str(e)) from e


@mcp.tool
def clear_history() -> str:
    """계산 기록을 모두 지운다."""
    _calc.clear_history()
    return "계산 기록을 지웠습니다."


# ══════════════════════════════════════════════════════
#  RESOURCES — 계산 기록을 읽는다 (부작용 없음)
# ══════════════════════════════════════════════════════

@mcp.resource("calc://history")
def history() -> str:
    """최근 계산 기록 전체."""
    records = _calc.get_history(limit=20)
    if not records:
        return "(계산 기록이 없습니다)"
    return "\n".join(f"{i}. {r}" for i, r in enumerate(records, 1))


@mcp.resource("calc://history/{limit}")
def history_limited(limit: str) -> str:
    """최근 N건의 계산 기록. (리소스 템플릿 — calc://history/5)"""
    try:
        n = int(limit)
    except ValueError:
        return "limit은 숫자여야 합니다."
    records = _calc.get_history(limit=n)
    if not records:
        return "(계산 기록이 없습니다)"
    return "\n".join(f"{i}. {r}" for i, r in enumerate(records, 1))


# ══════════════════════════════════════════════════════
#  PROMPTS — 재사용 프롬프트 템플릿
# ══════════════════════════════════════════════════════

@mcp.prompt
def solve_word_problem(problem: str) -> str:
    """문장으로 된 계산 문제를 풀도록 지시하는 프롬프트."""
    return (
        "다음 문제를 풀어줘. 계산이 필요하면 반드시 제공된 계산기 도구를 사용해라.\n"
        "암산하지 말고 도구를 써서 정확히 계산해라.\n\n"
        f"문제: {problem}"
    )


if __name__ == "__main__":
    # 전송 방식을 환경변수로 고를 수 있게 한다.
    #   기본(로컬)  : stdio
    #   운영(원격)  : MCP_TRANSPORT=http
    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "http":
        mcp.run(
            transport="http",
            host=os.environ.get("MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("MCP_PORT", "8000")),
        )
    else:
        mcp.run()  # stdio
