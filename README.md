# Plane OpenWebUI MCP Thin Adapter

사내용 Plane 티켓 운영을 위한 compatibility-first thin adapter 입니다.

- state UUID만 env에 고정 매핑합니다.
- labels / assignees는 runtime meta로 읽습니다.
- strict workflow / template / policy 엔진은 두지 않습니다.
- 서버는 raw-ish Plane tool surface를 제공하고, 해석은 LLM이 맡습니다.

## 코드 구조

- `app/main.py`: FastAPI entrypoint
- `app/routes/tools.py`: OpenWebUI가 쓰는 coarse-grained tool surface
- `app/plane_client.py`: Plane REST thin adapter
- `app/resolvers.py`: state/name/id/identifier resolution
- `app/models.py`: request/response schema
- `prompts/openwebui_system_prompt.txt`: 최소 system prompt

후속 수정 시 읽기 순서:
- `app/routes/tools.py`
- `app/resolvers.py`
- `app/plane_client.py`
- `app/config.py`

## 실행 방법

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

OpenAPI docs:
- `http://localhost:8000/docs`

## 환경변수

```dotenv
PLANE_BASE_URL=https://plane.example.com
PLANE_WORKSPACE_SLUG=my-workspace
PLANE_PROJECT_ID=project-uuid
PLANE_API_KEY=plane_api_xxx
DEFAULT_COMMENT_ACCESS=INTERNAL
DEFAULT_COMMENT_LIMIT=30
DEFAULT_ACTIVITY_LIMIT=30
META_CACHE_TTL_SECONDS=60
REQUEST_TIMEOUT_SECONDS=20
LOG_LEVEL=INFO
PLANE_STATE_ID_TRIAGE=state-triage-uuid
PLANE_STATE_ID_IN_PROGRESS=state-in-progress-uuid
PLANE_STATE_ID_WAITING_CUSTOMER=state-waiting-customer-uuid
PLANE_STATE_ID_READY_TO_REPLY=state-ready-to-reply-uuid
PLANE_STATE_ID_RESOLVED=state-resolved-uuid
PLANE_STATE_ID_CLOSED=state-closed-uuid
```

## Scope 원칙

- workspace-scoped:
  - identifier 기반 상세 조회
  - `GET /api/v1/workspaces/{workspace_slug}/work-items/{identifier}/`
- project-scoped:
  - project meta
  - work item list/create/update
  - comments / activities
  - states / labels / members

## Tool surface

- `GET /tools/get_meta_context`
- `POST /tools/search_tickets`
- `POST /tools/get_ticket`
- `POST /tools/get_ticket_comments`
- `POST /tools/get_ticket_activities`
- `POST /tools/create_ticket`
- `POST /tools/update_ticket`
- `POST /tools/add_ticket_comment`
- `POST /tools/transition_ticket_state`

## 상태 해석 원칙

- 입력은 `state_name` 또는 `state_id`를 받을 수 있습니다.
- canonical state name:
  - `triage`
  - `in_progress`
  - `waiting_customer`
  - `ready_to_reply`
  - `resolved`
  - `closed`
- `state_name`이 들어오면 서버가 env UUID mapping으로 resolve 합니다.
- list API filter는 가능한 경우 state ID를 사용하고, 부족한 부분만 서버 후처리합니다.

## 쓰기 payload 원칙

Plane 최종 request body는 반드시 아래 key를 사용합니다.

- `state`
- `labels`
- `assignees`

서버 내부에서만 `state_name -> state id`, `label_names -> label ids`, `assignee_names -> assignee ids`를 resolve 합니다.

## OpenWebUI 연결

1. 이 서버를 OpenWebUI tool server로 등록합니다.
2. `prompts/openwebui_system_prompt.txt`를 system prompt로 사용합니다.
3. labels / assignees 선택 전에는 `get_meta_context`를 먼저 호출합니다.
4. write 전에는 `search_tickets` 또는 `get_ticket`을 먼저 호출합니다.
5. self-hosted Plane 실서버 검증 절차는 `docs/SELF_HOSTED_SMOKE_TEST.md`를 따릅니다.

```bash
PYTHONPATH=. .venv/bin/pytest
```

테스트는 fake Plane client로 동작하므로 외부 Plane 서버 없이 API 표면과 정책 로직을 검증합니다.

## 실서버 검증

- OpenWebUI + 소형 모델 + 사내용 `.env` 조합으로 실제 동작 여부를 점검하려면:
  - `docs/SELF_HOSTED_SMOKE_TEST.md`
- 이 문서에는:
  - 권장 테스트 순서
  - 실패 시 수집할 로그/에러 정보
  - 저에게 다시 전달할 디버깅 템플릿
  이 포함되어 있습니다.

## 제한사항

- 자동 이메일 발송 없음
- 고객 포털 없음
- 유료 Plane 기능 미사용
- shared service token 사용으로 Plane 감사 주체는 서비스 계정 중심
- 서버는 strict workflow engine 이 아니라 thin adapter 이므로, 해석 품질은 모델 prompt 와 운영 규칙에 영향을 받습니다.

## 향후 확장 아이디어

- per-user PAT
- webhook
- 메일 inbox 연동
- SLA 리마인더
- 검색용 read-through cache
