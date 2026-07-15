"""할 일 관리 MCP 서버 — 기존 할 일 저장소를 MCP로 노출한다.

핵심(calc-mcp 와 동일한 철학):
  tasks.py 는 한 줄도 고치지 않는다. import 해서 쓰기만 한다.
  MCP는 얇은 '껍데기(wrapper)'일 뿐이다.

계산기 예제와 다른 실무 포인트:
  - 데이터가 SQLite 파일(tasks.db)에 영속된다 → 서버를 껐다 켜도 남는다.
  - 도구가 dict/list 를 반환한다 → MCP가 JSON 구조로 클라이언트에 전달한다.
"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from fastmcp import FastMCP

from tasks import TaskStore, TaskError  # ← 기존 저장소를 그대로 사용

mcp = FastMCP("Task Manager")

# DB 경로.
#   호스트(Claude Desktop)가 서버를 실행하면 작업 디렉터리(CWD)를 보장할 수 없다.
#   → 상대 경로 "tasks.db" 는 엉뚱한 폴더로 해석돼 열기에 실패할 수 있다.
#   그래서 기본값을 '이 파일이 있는 폴더' 기준 절대경로로 잡는다.
_DEFAULT_DB = Path(__file__).resolve().parent / "tasks.db"
_store = TaskStore(os.environ.get("TASK_DB", str(_DEFAULT_DB)))


# ══════════════════════════════════════════════════════
#  TOOLS — 할 일을 만들고 바꾼다 (부작용 있음)
# ══════════════════════════════════════════════════════

@mcp.tool
def add_task(title: str, priority: str = "normal", due: str = "") -> dict:
    """할 일을 추가한다.

    priority: "low" | "normal" | "high" (기본 normal)
    due:      마감일 "YYYY-MM-DD" (없으면 빈 문자열)
    """
    try:
        return _store.add(title, priority=priority, due=due or None)
    except TaskError as e:
        # 저장소의 도메인 예외를 MCP가 이해하는 형태로 올려보낸다.
        raise ValueError(str(e)) from e


@mcp.tool
def list_tasks(status: str = "") -> list[dict]:
    """할 일 목록을 조회한다.

    status: "todo"(미완료) | "done"(완료) | ""(전체)
    미완료·우선순위·마감 임박 순으로 정렬된다.
    """
    try:
        return _store.list(status=status or None)
    except TaskError as e:
        raise ValueError(str(e)) from e


@mcp.tool
def complete_task(task_id: int) -> dict:
    """할 일을 완료 처리한다."""
    try:
        return _store.complete(task_id)
    except TaskError as e:
        raise ValueError(str(e)) from e


@mcp.tool
def delete_task(task_id: int) -> str:
    """할 일을 삭제한다."""
    try:
        _store.delete(task_id)
        return f"{task_id}번 할 일을 삭제했습니다."
    except TaskError as e:
        raise ValueError(str(e)) from e


# ══════════════════════════════════════════════════════
#  RESOURCES — 할 일을 읽는다 (부작용 없음)
# ══════════════════════════════════════════════════════

@mcp.resource("tasks://all")
def all_tasks() -> str:
    """전체 할 일 요약 (사람이 읽기 좋은 텍스트)."""
    return _render(_store.list())


@mcp.resource("tasks://pending")
def pending_tasks() -> str:
    """미완료 할 일만."""
    return _render(_store.list(status="todo"))


@mcp.resource("tasks://stats")
def stats() -> str:
    """요약 통계."""
    s = _store.stats()
    return f"전체 {s['total']}건 · 완료 {s['done']}건 · 미완료 {s['todo']}건"


def _render(tasks: list[dict]) -> str:
    """할 일 목록을 텍스트로 만든다."""
    if not tasks:
        return "(할 일이 없습니다)"
    lines = []
    for t in tasks:
        mark = "✔" if t["status"] == "done" else " "
        due = f" (마감 {t['due']})" if t["due"] else ""
        lines.append(f"[{mark}] #{t['id']} [{t['priority']}] {t['title']}{due}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════
#  PROMPTS — 재사용 프롬프트 템플릿
# ══════════════════════════════════════════════════════

@mcp.prompt
def plan_my_day() -> str:
    """오늘 할 일을 정리·추천하도록 지시하는 프롬프트."""
    return (
        "list_tasks 도구로 미완료 할 일을 가져와서, "
        "우선순위와 마감일을 고려해 오늘 처리할 순서를 정해줘. "
        "각 항목에 왜 그 순서인지 한 줄로 이유도 붙여줘."
    )


if __name__ == "__main__":
    # 전송 방식을 환경변수로 고른다.  기본 stdio(로컬) / http(원격)
    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "http":
        mcp.run(
            transport="http",
            host=os.environ.get("MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("MCP_PORT", "8000")),
        )
    else:
        mcp.run()  # stdio
