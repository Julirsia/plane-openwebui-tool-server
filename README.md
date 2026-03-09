# Plane OpenWebUI Thin Adapter

사내 self-hosted Plane 또는 Plane Cloud를 OpenWebUI tool server로 연결하기 위한 단일 프로젝트용 thin adapter 입니다.

- state는 env에 고정하지 않습니다.
- 현재 프로젝트의 `states / labels / members`를 런타임에 읽어 해석합니다.
- 소형 모델이 실수하기 쉬운 작업은 coarse-grained tool로 감쌉니다.
- 해석이 애매하면 자동으로 추측하지 않고 400 + candidate 목록을 돌려줍니다.

## 코드 구조

- `app/config.py`: Plane API host, workspace URL, workspace slug 정규화
- `app/plane_client.py`: Plane REST adapter, endpoint 조합, read-only probe
- `app/resolvers.py`: state/name/group/id, label, assignee, ticket ref 해석
- `app/routes/tools.py`: OpenWebUI에서 호출할 tool surface
- `app/models.py`: request/response schema
- `prompts/openwebui_system_prompt.txt`: small-model용 system prompt

후속 수정 권장 순서:

1. `app/routes/tools.py`
2. `app/resolvers.py`
3. `app/plane_client.py`
4. `app/config.py`

## 실행

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

둘 중 하나를 선택해서 설정합니다.

```dotenv
# Option A: workspace URL 사용
PLANE_WORKSPACE_URL=https://app.plane.so/my-workspace/

# Option B: API base URL 직접 지정
# PLANE_API_BASE_URL=https://api.plane.so
# PLANE_WORKSPACE_SLUG=my-workspace

PLANE_PROJECT_ID=project-uuid
PLANE_API_KEY=plane_api_xxx
DEFAULT_COMMENT_ACCESS=INTERNAL
DEFAULT_COMMENT_LIMIT=30
DEFAULT_ACTIVITY_LIMIT=30
META_CACHE_TTL_SECONDS=60
REQUEST_TIMEOUT_SECONDS=20
LOG_LEVEL=INFO
```

주의:

- Cloud UI URL인 `https://app.plane.so/{workspace}/`를 넣어도 서버가 내부적으로 `https://api.plane.so`로 정규화합니다.
- self-hosted는 보통 `https://plane.company.internal` 같은 호스트를 그대로 쓰고, 서버가 `/api/v1`를 붙입니다.
- `PLANE_PROJECT_ID`는 단일 프로젝트 고정값이며, UUID/identifier/exact name 중 하나를 넣을 수 있습니다.

## Tool Surface

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

- 입력은 `state_id`, `state_name`, `state_group`만 사용합니다.
- 해석 우선순위는 `state_id > exact state_name > normalized state_name alias > unique state_group` 입니다.
- `state_group` 허용값은 `backlog`, `unstarted`, `started`, `completed`, `cancelled` 입니다.
- 같은 group에 state가 여러 개면 자동 선택하지 않고 candidate 목록을 반환합니다.
- 모델은 반드시 먼저 `get_meta_context`를 호출해 현재 프로젝트의 실제 state 이름과 group을 확인해야 합니다.

## 쓰기 원칙

Plane write payload는 최종적으로 아래 key만 사용합니다.

- `state`
- `labels`
- `assignees`

description 수정은 다음 중 하나만 사용합니다.

- `description_html`
- `description_text_replace`
- `description_text_append`

## OpenWebUI 연결

1. 이 서버를 OpenWebUI tool server로 등록합니다.
2. `prompts/openwebui_system_prompt.txt`를 system prompt로 사용합니다.
3. state, labels, assignees를 고르기 전 `get_meta_context`를 먼저 호출합니다.
4. write 전에는 `search_tickets` 또는 `get_ticket`을 먼저 호출합니다.
5. self-hosted 검증은 `docs/SELF_HOSTED_SMOKE_TEST.md`를 따릅니다.

## 테스트

```bash
PYTHONPATH=. .venv/bin/pytest
```

- 기본 테스트는 fake Plane client로 tool contract와 resolver 로직을 검증합니다.
- 실서버 읽기 smoke test는 env-gated이며 기본 실행에는 포함되지 않습니다.

## 제한사항

- 범위는 단일 프로젝트 고정입니다.
- state 자체 CRUD API는 노출하지 않습니다.
- strict workflow engine 은 넣지 않았습니다.
- shared service token 사용 시 Plane 감사 주체는 서비스 계정으로 남습니다.
