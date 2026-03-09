# Self-Hosted Plane 실서버 검증 가이드

이 문서는 **사내 Plane + OpenWebUI + 소형 모델(GPT-5 mini 등)** 조합에서
이 MCP thin adapter가 의도한 대로 동작하는지 검증하기 위한 체크리스트입니다.

목표는 2가지입니다.

1. **실제 self-hosted Plane에서 endpoint/path/shape가 맞는지 확인**
2. 실패 시 **재현 가능한 디버깅 정보**를 남겨서 빠르게 수정할 수 있게 하기

---

## 1. 사전 준비

### 1-1. 사내 `.env` 확인
최소한 아래 값이 올바르게 들어 있어야 합니다.

```dotenv
PLANE_BASE_URL=https://your-plane-host
PLANE_WORKSPACE_SLUG=your-workspace
PLANE_PROJECT_ID=your-project-uuid
PLANE_API_KEY=your-plane-api-key

DEFAULT_COMMENT_ACCESS=INTERNAL
DEFAULT_COMMENT_LIMIT=30
DEFAULT_ACTIVITY_LIMIT=30
META_CACHE_TTL_SECONDS=60
REQUEST_TIMEOUT_SECONDS=20
LOG_LEVEL=INFO

PLANE_STATE_ID_TRIAGE=...
PLANE_STATE_ID_IN_PROGRESS=...
PLANE_STATE_ID_WAITING_CUSTOMER=...
PLANE_STATE_ID_READY_TO_REPLY=...
PLANE_STATE_ID_RESOLVED=...
PLANE_STATE_ID_CLOSED=...
```

### 1-2. state UUID 확인 원칙
- state만 env에 고정 UUID로 둡니다.
- labels / assignees는 env에 넣지 않습니다.
- labels / assignees는 런타임에 `get_meta_context`로 읽게 되어 있습니다.

### 1-3. 서버 실행
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 1-4. OpenWebUI 설정
- Tool server로 이 서버를 등록
- system prompt는 `prompts/openwebui_system_prompt.txt` 사용
- 가능하면 테스트 중에는 **이 MCP만 활성화**
- web/search/knowledge/memory 류는 끄는 것을 권장

---

## 2. 검증 순서

아래 순서를 그대로 따르는 것을 권장합니다.

### Stage A. 서버/메타 확인

#### A-1. health
- 기대 결과: 200 OK
- 목적: 서버 자체가 살아 있는지 확인

#### A-2. `get_meta_context`
- 기대 결과:
  - project 정보 조회 성공
  - states 목록 조회 성공
  - labels 목록 조회 성공
  - members 목록 조회 성공
- 확인 포인트:
  - state UUID들이 env에 넣은 것과 실제 Plane state에 대응하는지
  - labels / members가 비어 있지 않은지

**OpenWebUI 테스트 프롬프트 예시**
- `먼저 get_meta_context를 호출해서 project, states, labels, members를 보여줘.`

---

### Stage B. 읽기(Read) 검증

#### B-1. state 기반 검색
목적: `search_tickets`가 실제로 state 필터 + 정렬 + 요약을 제대로 하는지 확인

**OpenWebUI 테스트 프롬프트 예시**
- `triage 상태 티켓 5개를 검색해줘.`
- `resolved 상태 티켓 3개만 보여줘.`

기대 결과:
- 티켓 목록 반환
- `identifier`, `title`, `state_name`, `updated_at` 등이 보임
- 최신순(`updated_at desc`)으로 보임

#### B-2. identifier 상세 조회
목적: self-hosted Plane에서 identifier lookup이 실제로 되는지 확인

**OpenWebUI 테스트 프롬프트 예시**
- `SOFT-170 티켓 상세를 보여줘.`

기대 결과:
- `get_ticket`이 identifier로 조회 성공
- `ticket.id`, `ticket.identifier`, `description_text` 등이 반환됨

#### B-3. comments 조회
**OpenWebUI 테스트 프롬프트 예시**
- `SOFT-170 티켓의 최근 댓글 5개를 보여줘.`

기대 결과:
- `get_ticket_comments` 성공
- comment list가 반환됨

#### B-4. activities 조회
**OpenWebUI 테스트 프롬프트 예시**
- `SOFT-170 티켓의 최근 활동 10개를 보여줘.`

기대 결과:
- `get_ticket_activities` 성공
- activity list가 반환됨

---

### Stage C. 쓰기(Write) 검증

읽기 검증이 끝난 뒤에만 수행하세요.

#### C-1. 상태 변경
목적: env의 state UUID mapping이 제대로 동작하는지 확인

**OpenWebUI 테스트 프롬프트 예시**
- `SOFT-170 티켓 상태를 in_progress로 바꿔줘.`
- `SOFT-170 티켓 상태를 resolved로 바꿔줘.`

기대 결과:
- `transition_ticket_state` 성공
- 반환에 변경된 상태가 반영됨

주의:
- 실제 운영 티켓을 건드리므로 테스트용 티켓 또는 되돌릴 수 있는 티켓으로 하세요.

#### C-2. 내부 댓글 추가
목적: INTERNAL comment가 실제 self-hosted Plane에서 정상 동작하는지 확인

**OpenWebUI 테스트 프롬프트 예시**
- `SOFT-170 티켓에 내부 댓글로 "mcp smoke test"를 남겨줘.`

기대 결과:
- 댓글 생성 성공
- Plane UI에서 internal comment로 보임

#### C-3. 최소 필드 수정
목적: thin adapter의 patch write가 잘 동작하는지 확인

**OpenWebUI 테스트 프롬프트 예시**
- `SOFT-170 티켓 description에 맨 아래에 "MCP smoke test line" 문구를 추가해줘.`

기대 결과:
- `update_ticket` 성공
- description_html이 수정됨

---

## 3. 권장 검증 시나리오

가장 안전한 권장 순서:

1. `get_meta_context`
2. `search_tickets` (`triage`, `resolved` 같은 상태로)
3. `get_ticket` (`SOFT-170` 같은 identifier)
4. `get_ticket_comments`
5. `get_ticket_activities`
6. `transition_ticket_state`
7. `add_ticket_comment`
8. `update_ticket`

즉 **read가 모두 통과한 뒤 write로 넘어가세요.**

---

## 4. 기대되는 실패 유형

### 4-1. identifier 조회 실패
예:
- 404 Not Found
- `/workspaces/{workspace}/work-items/{identifier}/` 실패

가능 원인:
- self-hosted Plane 버전 차이
- identifier lookup path 차이
- workspace slug / base URL 오설정

### 4-2. comments / activities 조회 실패
예:
- comments path 404
- activities path 404
- shape mismatch

가능 원인:
- self-hosted Plane API 버전 차이
- cloud 문서와 경로/응답 차이

### 4-3. 상태 변경 실패
예:
- 400 / 404 / 422

가능 원인:
- env의 state UUID 오설정
- self-hosted Plane state schema 차이
- PATCH body 형식 차이

### 4-4. label/member resolve 실패
예:
- unknown label name
- unknown assignee name

가능 원인:
- OpenWebUI 모델이 `get_meta_context`를 먼저 읽지 않음
- 이름 exact match 실패

---

## 5. 실패 시 반드시 남겨야 할 정보

실패를 수정하려면 아래 정보가 꼭 필요합니다.

### 필수 1. 사용한 사용자 프롬프트
예:
- `SOFT-170 티켓 상세를 보여줘`
- `triage 상태 티켓 5개를 검색해줘`
- `SOFT-170 티켓 상태를 resolved로 바꿔줘`

### 필수 2. OpenWebUI에서 보인 tool 호출 이름
예:
- `get_ticket`
- `search_tickets`
- `transition_ticket_state`

### 필수 3. tool 입력 payload
예:
```json
{
  "identifier": "SOFT-170"
}
```

### 필수 4. 실제 에러 메시지 전문
예:
- HTTP status
- response body
- stack trace 일부
- OpenWebUI tool error text

### 필수 5. 서버 로그
가능하면 해당 시점의 서버 로그 몇 줄을 같이 남겨 주세요.

예:
```bash
tail -n 200 server.log
```
또는 실행 터미널 로그 복사

### 필수 6. 해당 티켓이 read/write 어디서 실패했는지
예:
- `get_ticket은 실패, search_tickets는 성공`
- `comments 조회만 실패`
- `transition은 실패하지만 update는 성공`

이 정보가 있으면 endpoint scope 문제인지, payload shape 문제인지 빠르게 구분할 수 있습니다.

---

## 6. 디버깅 메시지 템플릿

문제가 생겼을 때 아래 형식으로 보내주시면 가장 빠릅니다.

```text
[환경]
- Plane 배포 형태: self-hosted
- MCP 서버 주소: ...
- OpenWebUI 모델: ...

[사용자 프롬프트]
...

[호출된 tool]
...

[tool input payload]
```json
...
```

[에러 메시지]
```text
...
```

[서버 로그]
```text
...
```

[추가 관찰]
- search_tickets는 성공 / get_ticket만 실패
- identifier는 SOFT-170
- comments만 404
```

---

## 7. 최소 수동 curl 체크

OpenWebUI 이전에 서버/Plane 경로 자체를 확인하려면 아래를 참고하세요.

### 7-1. meta context
```bash
curl http://<mcp-host>:8000/tools/get_meta_context
```

### 7-2. search
```bash
curl -X POST http://<mcp-host>:8000/tools/search_tickets \
  -H 'Content-Type: application/json' \
  -d '{"state_names": ["triage"], "limit": 5}'
```

### 7-3. identifier detail
```bash
curl -X POST http://<mcp-host>:8000/tools/get_ticket \
  -H 'Content-Type: application/json' \
  -d '{"identifier": "SOFT-170"}'
```

### 7-4. comments
```bash
curl -X POST http://<mcp-host>:8000/tools/get_ticket_comments \
  -H 'Content-Type: application/json' \
  -d '{"identifier": "SOFT-170", "limit": 5}'
```

### 7-5. activities
```bash
curl -X POST http://<mcp-host>:8000/tools/get_ticket_activities \
  -H 'Content-Type: application/json' \
  -d '{"identifier": "SOFT-170", "limit": 10}'
```

---

## 8. 합격 기준

다음이 되면 1차 실서버 검증 통과로 봐도 됩니다.

- `get_meta_context` 성공
- `search_tickets(state_names=[...])` 성공
- `get_ticket(identifier=...)` 성공
- `get_ticket_comments` 성공
- `get_ticket_activities` 성공
- `transition_ticket_state` 성공
- `add_ticket_comment(access=INTERNAL)` 성공
- `update_ticket` 성공

이후 남는 건 운영 세부조정(prompt, exact match, 모델 습관) 수준입니다.
