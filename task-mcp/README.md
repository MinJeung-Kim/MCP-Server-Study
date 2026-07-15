# task-mcp — SQLite 할 일 관리 MCP 서버

`calc-mcp` 와 같은 철학으로 만든 **실무형** 예제.
계산기(순수 로직)와 달리 **상태가 SQLite 파일에 영속**되고, 도구가 부작용을 갖는다.

```
tasks.py         순수 로직 + SQLite (MCP 없음 — 단독 실행 가능)
task_server.py   MCP 껍데기 — tasks.py 를 감싸기만 한다
host.py          클라이언트 — 서버를 띄워 도구를 호출한다 (직접 호출 / LLM)
mcp_config.json  호스트가 서버를 실행하는 방법
```

## 노출하는 것

| 구분 | 항목 | 설명 |
|------|------|------|
| Tools | `add_task` `list_tasks` `complete_task` `delete_task` | 할 일 생성·조회·완료·삭제 |
| Resources | `tasks://all` `tasks://pending` `tasks://stats` | 읽기 전용 뷰 |
| Prompts | `plan_my_day` | "오늘 할 일 정리" 프롬프트 |

## 실무 포인트

- **영속성** — 데이터가 `tasks.db` 에 저장된다. 서버를 재시작해도 남는다.
- **SQL 인젝션 방어** — 모든 값은 `?` 파라미터 바인딩으로 전달. f-string으로 SQL을 만들지 않는다.
- **입력 검증** — 잘못된 우선순위·마감일·없는 ID는 `TaskError` → MCP 오류로 변환.
- **관심사 분리** — DB 로직(`tasks.py`)과 MCP 노출(`task_server.py`)이 분리돼 있어, 로직은 그대로 두고 껍데기만 바꿀 수 있다.

## 실행

```bash
# 1) 순수 로직만 확인 (MCP 없이)
python tasks.py

# 2) MCP 서버 실행 (stdio)
python task_server.py

# 3) 원격(HTTP) 모드
MCP_TRANSPORT=http MCP_PORT=8000 python task_server.py
```

DB 파일 위치는 `TASK_DB` 환경변수로 바꿀 수 있다 (기본 `tasks.db`, 테스트는 `:memory:`).

## host.py 로 서버 호출하기

stdio 서버는 혼자 실행하면 조용히 대기만 한다 — **클라이언트가 붙어야** 동작한다.
`host.py` 가 그 클라이언트다 (Claude Desktop 과 같은 역할).

```bash
# 직접 호출 모드 — LLM 없이 내가 도구를 지정해 호출
python host.py

# LLM 에이전트 모드 — Ollama(qwen3)가 자연어를 보고 도구를 결정
python host.py --llm     # 사전 준비: ollama 실행 + `ollama pull qwen3`
```

## Claude Desktop 에 연결

`claude_desktop_config.json` 에 추가:

```json
{
  "mcpServers": {
    "task-manager": {
      "command": "python",
      "args": ["C:\\Users\\kmj\\Desktop\\kmj\\mcp-study\\task-mcp\\task_server.py"]
    }
  }
}
```

연결 후 Claude 에게 이렇게 말하면 된다:
> "보고서 작성을 높은 우선순위로 20일까지 할 일에 추가해줘" → `add_task` 호출
> "오늘 뭐부터 할까?" → `plan_my_day` 프롬프트 + `list_tasks`
