"""할 일 저장소 — MCP와 무관한 순수 로직 + SQLite.

calc-mcp 의 calculator.py 와 같은 역할이다.
이 파일만 떼어내도 그대로 동작한다. MCP는 나중에 이걸 '감싸기'만 한다.

실무 포인트(계산기 예제와 다른 점):
  1. 상태가 파일(SQLite)에 영속된다 — 서버를 재시작해도 데이터가 남는다.
  2. 모든 SQL은 '?' 파라미터 바인딩으로만 값을 넘긴다 → SQL 인젝션 원천 차단.
  3. 입력 검증 실패는 TaskError 로 명확히 던진다 (MCP 껍데기가 이걸 변환한다).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date

# 허용되는 값들 — 검증에 사용한다.
STATUSES = ("todo", "done")
PRIORITIES = ("low", "normal", "high")


class TaskError(Exception):
    """할 일 처리 중 발생한 오류 (잘못된 입력, 없는 항목 등)."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'todo',
    priority   TEXT    NOT NULL DEFAULT 'normal',
    due        TEXT,                                  -- 'YYYY-MM-DD' 또는 NULL
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


class TaskStore:
    """SQLite로 뒷받침되는 할 일 저장소."""

    def __init__(self, db_path: str = "tasks.db") -> None:
        # check_same_thread=False: MCP 서버가 다른 스레드에서 호출할 수 있어서.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row  # 행을 dict 처럼 다룬다
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    # ── 쓰기 (부작용 있음) ────────────────────────────
    def add(self, title: str, priority: str = "normal", due: str | None = None) -> dict:
        """할 일을 추가하고, 만들어진 항목을 돌려준다."""
        title = title.strip()
        if not title:
            raise TaskError("할 일 제목은 비어 있을 수 없습니다.")
        if priority not in PRIORITIES:
            raise TaskError(f"priority는 {PRIORITIES} 중 하나여야 합니다: {priority!r}")
        if due is not None:
            self._validate_due(due)

        cur = self._conn.execute(
            # 값은 반드시 '?' 로만 전달한다 — f-string으로 SQL을 만들지 않는다.
            "INSERT INTO tasks (title, priority, due) VALUES (?, ?, ?)",
            (title, priority, due),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)

    def complete(self, task_id: int) -> dict:
        """할 일을 완료 처리한다."""
        self.get(task_id)  # 없으면 여기서 TaskError
        self._conn.execute(
            "UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,)
        )
        self._conn.commit()
        return self.get(task_id)

    def delete(self, task_id: int) -> None:
        """할 일을 삭제한다."""
        cur = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        if cur.rowcount == 0:
            raise TaskError(f"{task_id}번 할 일이 없습니다.")

    # ── 읽기 (부작용 없음) ────────────────────────────
    def get(self, task_id: int) -> dict:
        """할 일 하나를 조회한다. 없으면 오류."""
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise TaskError(f"{task_id}번 할 일이 없습니다.")
        return dict(row)

    def list(self, status: str | None = None, limit: int = 50) -> list[dict]:
        """할 일 목록. status를 주면 그 상태만 거른다."""
        if status is not None and status not in STATUSES:
            raise TaskError(f"status는 {STATUSES} 중 하나여야 합니다: {status!r}")

        # 정렬: 미완료 먼저 → 우선순위 높은 순 → 마감 임박 순.
        order = (
            "ORDER BY status = 'done', "
            "CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, "
            "due IS NULL, due"
        )
        if status is None:
            rows = self._conn.execute(
                f"SELECT * FROM tasks {order} LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT * FROM tasks WHERE status = ? {order} LIMIT ?",
                (status, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """요약 통계 — 전체/완료/미완료 개수."""
        row = self._conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(status = 'done') AS done, "
            "  SUM(status = 'todo') AS todo "
            "FROM tasks"
        ).fetchone()
        return {
            "total": row["total"],
            "done": row["done"] or 0,
            "todo": row["todo"] or 0,
        }

    def close(self) -> None:
        self._conn.close()

    # ── 내부 유틸 ────────────────────────────────────
    @staticmethod
    def _validate_due(due: str) -> None:
        """마감일이 'YYYY-MM-DD' 형식인지 검증한다."""
        try:
            date.fromisoformat(due)
        except ValueError as e:
            raise TaskError(f"마감일은 YYYY-MM-DD 형식이어야 합니다: {due!r}") from e


# ── 단독 실행: 빠른 동작 확인 (MCP 없이) ──────────────
if __name__ == "__main__":
    with closing(TaskStore(":memory:")) as store:  # 메모리 DB로 테스트
        store.add("MCP 예제 만들기", priority="high", due="2026-07-20")
        store.add("문서 정리")
        t = store.add("커피 사기", priority="low")
        store.complete(t["id"])

        print("== 전체 목록 ==")
        for task in store.list():
            mark = "x" if task["status"] == "done" else " "
            print(f"  [{mark}] #{task['id']} ({task['priority']}) {task['title']}"
                  f"  {task['due'] or ''}")

        print("\n── 통계 ──")
        print(f"  {store.stats()}")
