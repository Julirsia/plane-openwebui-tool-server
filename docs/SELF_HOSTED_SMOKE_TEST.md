# Self-Hosted Plane Smoke Test

이 문서는 self-hosted Plane + OpenWebUI + 소형 모델 조합에서 이 tool server가 실제로 붙는지 빠르게 확인하기 위한 절차입니다.

목표:

1. host/path/auth 설정이 맞는지 확인
2. 현재 프로젝트의 runtime state 구조를 모델이 제대로 읽는지 확인
3. 읽기 성공 뒤 최소 쓰기 한 번만 검증

## 1. 설정 확인

최소 설정:

```dotenv
# 둘 중 하나
PLANE_WORKSPACE_URL=https://plane.company.internal/my-workspace/
# 또는
# PLANE_API_BASE_URL=https://plane.company.internal
# PLANE_WORKSPACE_SLUG=my-workspace

PLANE_PROJECT_ID=project-uuid-or-identifier
PLANE_API_KEY=plane_api_xxx
DEFAULT_COMMENT_ACCESS=INTERNAL
DEFAULT_COMMENT_LIMIT=30
DEFAULT_ACTIVITY_LIMIT=30
META_CACHE_TTL_SECONDS=60
REQUEST_TIMEOUT_SECONDS=20
LOG_LEVEL=INFO
```

주의:

- Plane Cloud UI URL `https://app.plane.so/{workspace}/`를 넣으면 서버가 `https://api.plane.so`로 자동 정규화합니다.
- self-hosted는 UI host와 API host가 같더라도 path는 서버가 `/api/v1` 기준으로 붙입니다.
- 더 이상 `PLANE_STATE_ID_*` 환경변수는 사용하지 않습니다.

## 2. 서버 실행

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3. OpenWebUI 설정

- 이 서버만 tool server로 등록
- 가능하면 테스트 중에는 다른 tool 비활성화
- system prompt는 `prompts/openwebui_system_prompt.txt` 사용

## 4. 권장 검증 순서

### A. Meta probe

OpenWebUI 예시:

- `먼저 get_meta_context를 호출해서 project, states, labels, members를 보여줘.`

기대 결과:

- `project` 조회 성공
- `states[].id`, `states[].name`, `states[].group`, `states[].is_default`, `states[].aliases` 확인 가능
- `labels`, `members` 조회 성공

확인 포인트:

- state 이름이 실제 self-hosted 프로젝트 상태와 일치하는지
- 같은 `group`에 state가 여러 개 있는지

### B. Read

반드시 `get_meta_context`에서 본 실제 state 이름 또는 group을 사용합니다.

OpenWebUI 예시:

- `get_meta_context에서 본 exact state 이름으로 티켓 5개를 검색해줘.`
- `SOFT-170 티켓 상세를 보여줘.`
- `SOFT-170 티켓의 최근 댓글 5개를 보여줘.`
- `SOFT-170 티켓의 최근 활동 10개를 보여줘.`

기대 결과:

- `search_tickets`가 compact summary 반환
- `get_ticket`이 identifier로 상세 조회 성공
- comments / activities 조회 성공

### C. Write

읽기 성공 후에만 수행합니다.

OpenWebUI 예시:

- `SOFT-170 티켓 상태를 get_meta_context에서 본 exact state 이름으로 바꿔줘.`
- `SOFT-170 티켓에 내부 댓글로 "mcp smoke test"를 남겨줘.`
- `SOFT-170 티켓 description 맨 아래에 "MCP smoke test line"을 추가해줘.`

기대 결과:

- `transition_ticket_state` 성공
- `add_ticket_comment` 성공
- `update_ticket`가 append 방식으로 description 수정 성공

## 5. 자주 나는 실패 유형

### UI host를 API host로 착각한 경우

증상:

- 404
- HTML 페이지 반환

원인:

- `app.plane.so` 또는 self-hosted UI 경로를 API base로 직접 사용

대응:

- `PLANE_WORKSPACE_URL`을 넣고 서버 정규화에 맡기거나
- `PLANE_API_BASE_URL`을 명시적으로 설정

### state 이름을 추측한 경우

증상:

- `Unknown state name`
- `State group 'started' is ambiguous`

원인:

- 모델이 `get_meta_context` 없이 canonical state를 추측

대응:

- 항상 `get_meta_context`에서 현재 프로젝트 state 이름을 읽고 exact name 사용

### identifier 상세 조회 실패

증상:

- `/workspaces/{workspace}/work-items/{identifier}/` 404

원인:

- workspace slug 오설정
- Plane self-hosted 버전 차이

### comments / activities shape 차이

증상:

- comments 또는 activities 404/422

원인:

- self-hosted 버전별 API 차이

## 6. 실패 시 남길 정보

- 사용자 프롬프트 원문
- OpenWebUI에서 보인 tool 이름
- tool 입력 payload
- HTTP status와 response body
- 해당 시점 서버 로그
