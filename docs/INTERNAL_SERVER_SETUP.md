# Internal Server Setup

이 문서는 사내 서버에 이 레포를 clone 해서 Plane + OpenWebUI용 tool server를 올리는 절차입니다.

## 1. 서버에 레포 clone

```bash
cd /opt
git clone <YOUR_GIT_REMOTE_URL> plane-openwebui-tool-server
cd plane-openwebui-tool-server
```

권장 위치는 `/opt/plane-openwebui-tool-server` 또는 팀 표준 애플리케이션 디렉터리입니다.

## 2. Python 가상환경 생성

Python 3.11+ 권장입니다.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 3. `.env` 준비

```bash
cp .env.example .env
```

필수 환경변수:

| 변수 | 설명 | 예시 |
| --- | --- | --- |
| `PLANE_BASE_URL` | 사내 Plane base URL | `https://plane.example.com` |
| `PLANE_WORKSPACE_SLUG` | Plane workspace slug | `my-workspace` |
| `PLANE_PROJECT_ID` | 대상 project UUID | `7ab4...` |
| `PLANE_API_KEY` | service account PAT | `plane_api_xxx` |
| `DEFAULT_LANGUAGE` | 기본 언어 | `ko` |
| `DEFAULT_TIMEZONE` | 기본 타임존 | `Asia/Seoul` |
| `CONTEXT_CACHE_TTL_SECONDS` | state/label/member 캐시 TTL | `60` |
| `DEFAULT_COMMENT_LIMIT` | 기본 note 조회 수 | `30` |
| `DEFAULT_ACTIVITY_LIMIT` | 기본 activity 조회 수 | `30` |
| `LOG_LEVEL` | 로그 레벨 | `INFO` |

예시:

```dotenv
PLANE_BASE_URL=https://plane.example.com
PLANE_WORKSPACE_SLUG=my-workspace
PLANE_PROJECT_ID=7ab4f7de-1111-2222-3333-abcdefabcdef
PLANE_API_KEY=plane_api_xxx
DEFAULT_LANGUAGE=ko
DEFAULT_TIMEZONE=Asia/Seoul
CONTEXT_CACHE_TTL_SECONDS=60
DEFAULT_COMMENT_LIMIT=30
DEFAULT_ACTIVITY_LIMIT=30
LOG_LEVEL=INFO
```

앱은 시작 시 현재 작업 디렉터리의 `.env`를 자동으로 읽습니다.

## 3-1. Plane API scope 가정

이 서버는 Plane 공식 work item 문서 기준으로 endpoint scope 를 나눕니다.

- workspace-scoped:
  - readable identifier 로 티켓 조회
  - `GET /api/v1/workspaces/{workspace_slug}/work-items/{identifier}/`
- project-scoped:
  - work item 목록 조회
  - work item 생성/수정
  - states/labels/project members
  - comments/activities
  - `GET|POST|PATCH /api/v1/workspaces/{workspace_slug}/projects/{project_id}/...`

운영 smoke test 시 `/meta/context`, `tickets/search`, `tickets/{identifier}/context` 를 먼저 호출해 이 가정이 배포본과 맞는지 확인하십시오.

## 4. 서버 실행

개발/단일 프로세스 실행:

```bash
. .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

기본 확인:

- health: `GET http://<server>:8000/health`
- docs: `http://<server>:8000/docs`

외부 reverse proxy 뒤에 둘 경우 내부 포트만 열고, OpenWebUI가 접근 가능한 내부 URL 또는 사내 HTTPS URL을 사용하십시오.

## 5. OpenWebUI 등록

1. OpenWebUI 관리자 화면에서 Global Tool Server 등록
2. Tool Server URL에 이 서버 주소 입력
   - 예: `http://tool-server.internal:8000`
3. 연결 후 OpenAPI schema 로드 확인
4. 이 서버만 tool 로 활성화

## 6. GPT-5 mini 권장 설정

권장값:

- 모델: GPT-5 mini
- tool 사용: 이 서버만 활성화
- built-in web search: 비활성화 권장
- knowledge: 비활성화 권장
- memory: 비활성화 권장
- native function calling: 가능하면 사용

이유:

- v1은 `search -> context -> upsert/transition` 흐름을 강하게 가정합니다.
- 다른 tool 이 섞이면 triage/query 흐름보다 웹검색이나 메모에 우선순위를 빼앗길 수 있습니다.

## 7. system prompt 적용

프로젝트에 포함된 [`prompts/openwebui_system_prompt.txt`](../prompts/openwebui_system_prompt.txt) 내용을 OpenWebUI custom model의 system prompt에 그대로 붙여넣습니다.

적용 위치:

1. OpenWebUI에서 Custom Model 생성 또는 기존 모델 래핑
2. System Prompt 입력란에 `prompts/openwebui_system_prompt.txt` 전체 내용 붙여넣기
3. `{{ USER_NAME }}` 가 operator name 으로 전달되는지 확인

## 8. 운영 시 주의사항

- 내부 전용 시스템입니다. 고객은 Plane/OpenWebUI에 접근하지 않습니다.
- 이메일은 draft만 생성합니다. 자동 발송하지 않습니다.
- write 전에는 항상 `tickets/search` 또는 `tickets/{identifier}/context`를 먼저 읽어야 합니다.
- `expected_updated_at`이 맞지 않으면 서버가 409로 막습니다. 이 경우 context를 다시 읽고 재시도해야 합니다.
- `editable_sections`는 템플릿 YAML 외부 정의를 따릅니다. 허용되지 않은 section은 400으로 거부됩니다.
- API key 는 shared service token 이므로 Plane의 최종 감사 주체는 서비스 계정입니다. `operator_name`이 내부 note 에 남습니다.

## 9. 운영자 체크리스트

- Plane 상태/라벨 taxonomy가 README와 일치하는가
- `.env` 값이 실제 workspace/project를 가리키는가
- `/meta/context` 호출 시 states/labels/templates가 정상 노출되는가
- OpenWebUI 모델이 write 전에 context read를 수행하는가
- `prompts/openwebui_system_prompt.txt` 최신본이 적용되어 있는가
