"""세 가지 primitive를 모두 갖춘 완전한 MCP 서버.

MCP 서버가 노출할 수 있는 세 가지 기본 요소를 한 파일에 모았다.

  ┌───────────┬──────────────┬─────────────────────────────┐
  │ primitive │ 성격         │ 비유                        │
  ├───────────┼──────────────┼─────────────────────────────┤
  │ Tools     │ 행동(하게 함) │ LLM이 호출해 실행. 부작용 O │
  │ Resources │ 읽기(보게 함) │ LLM이 데이터 조회. 부작용 X │
  │ Prompts   │ 템플릿(시킴)  │ 재사용 프롬프트. 사용자 선택 │
  └───────────┴──────────────┴─────────────────────────────┘

각 primitive를 '단순형'과 '파라미터형' 두 가지로 보여준다.
"""

import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message

mcp = FastMCP("Complete Demo Server")

# 리소스가 읽어올 가짜 데이터 저장소 (실무라면 DB나 외부 API)
_MEMBERS = {
    "1": {"name": "민정", "box": "CrossFit Incheon", "level": "Rx"},
    "2": {"name": "민준", "box": "CrossFit Seoul", "level": "Scaled"},
}


# ══════════════════════════════════════════════════════════
#  1. TOOLS — 행동하는 함수 (부작용 있음)
# ══════════════════════════════════════════════════════════

@mcp.tool
def add(a: int, b: int) -> int:
    """두 정수를 더한다. (단순 도구)"""
    return a + b


@mcp.tool
def calculate_1rm(weight: float, reps: int) -> dict:
    """들어올린 무게와 횟수로 1RM(1회 최대 중량)을 추정한다.

    Epley 공식 사용. (파라미터가 여러 개인 실용 도구 예시)
    """
    if reps < 1:
        raise ValueError("reps는 1 이상이어야 합니다.")
    one_rm = weight * (1 + reps / 30)
    return {
        "input": f"{weight}kg x {reps}회",
        "estimated_1rm": round(one_rm, 1),
        "formula": "Epley",
    }


# ══════════════════════════════════════════════════════════
#  2. RESOURCES — 읽는 데이터 (부작용 없음)
# ══════════════════════════════════════════════════════════

@mcp.resource("config://app")
def get_config() -> str:
    """앱 설정 정보. (단순 정적 리소스 — 고정 URI)"""
    return "app_name=CompleteDemo, version=1.0, env=local"


@mcp.resource("server://time")
def get_server_time() -> str:
    """서버 현재 시각. (호출할 때마다 값이 달라지는 동적 리소스)"""
    return datetime.now().isoformat(timespec="seconds")


@mcp.resource("member://{member_id}")
def get_member(member_id: str) -> dict:
    """회원 ID로 회원 정보를 조회한다. (리소스 템플릿 — URI에 변수 포함)

    member://1, member://2 처럼 ID를 URI에 담아 호출한다.
    """
    member = _MEMBERS.get(member_id)
    if member is None:
        return {"error": f"회원 {member_id}를 찾을 수 없습니다."}
    return member


# ══════════════════════════════════════════════════════════
#  3. PROMPTS — 재사용 프롬프트 템플릿
# ══════════════════════════════════════════════════════════

@mcp.prompt
def summarize(text: str) -> str:
    """주어진 텍스트를 3문장으로 요약하도록 지시하는 프롬프트. (단순형)"""
    return f"다음 텍스트를 한국어 3문장으로 요약해줘:\n\n{text}"


@mcp.prompt
def code_review(language: str, code: str) -> list[Message]:
    """코드 리뷰용 프롬프트. (여러 메시지로 구성된 대화형 프롬프트)

    시스템 역할 안내 + 실제 리뷰 요청을 한 세트로 묶어 재사용한다.
    """
    return [
        Message(
            f"당신은 숙련된 {language} 개발자입니다. "
            "가독성, 버그 가능성, 성능 관점에서 간결하게 리뷰하세요.",
            role="assistant",
        ),
        Message(
            f"다음 {language} 코드를 리뷰해줘:\n\n```{language}\n{code}\n```",
            role="user",
        ),
    ]


if __name__ == "__main__":
    # 학습·확인용은 stdio가 편하다. (운영이면 transport="http")
    mcp.run()
