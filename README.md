# Plane OpenWebUI Thin Adapter

내부 전용 Plane OpenWebUI thin adapter 입니다.

- Plane = source of truth
- OpenWebUI = 운영 콘솔
- 이메일은 수동 발송
- 이 서버는 GPT-5 mini가 사내 Plane과 안정적으로 상호작용하도록 만든 compatibility-first API wrapper 입니다.

배포 절차와 OpenWebUI 등록 절차는 [`docs/INTERNAL_SERVER_SETUP.md`](docs/INTERNAL_SERVER_SETUP.md) 에 정리되어 있습니다.

## 개요

이 프로젝트는 Plane Community, OpenWebUI, FastAPI 기반의 내부 티켓 운영용 thin adapter 입니다.

- 고객은 Plane이나 OpenWebUI에 로그인하지 않습니다.
- 운영자는 OpenWebUI에서 티켓을 조회, 요약, 수정, 상태 전환, 내부 메모 작성, 회신 초안 저장을 수행합니다.
- 자동 이메일 발송은 하지 않습니다.
- strict workflow engine 이 아니라 Plane API thin adapter 에 가깝게 동작합니다.
- 기존 Plane 티켓도 읽을 수 있습니다. canonical `ticket_meta`가 없는 legacy 티켓은 label/title/description 기반 fallback으로 해석합니다.

## 코드 구조

- `app/main.py`: FastAPI 진입점
- `app/routes/`: OpenAPI 표면. search/context/update/comment/transition/create 중심의 coarse-grained tool flow를 제공합니다.
- `app/plane_client.py`: Plane REST thin adapter. workspace-scoped identifier lookup 과 project-scoped create/update/list/comment/activity 경로를 분리합니다.
- `app/templates_registry.py`: YAML 템플릿 로딩
- `app/renderer.py` / `app/parser.py`: HTML 생성/파싱 helper
- `app/policy.py`: runtime state/label/member resolve 와 optional transition guard
- `app/ticket_document.py`: legacy/canonical ticket 해석 helper
- `templates/*.yaml`: optional template metadata
- `policies/transition_policy.yaml`: optional 상태 전이 guard
- `prompts/openwebui_system_prompt.txt`: OpenWebUI system prompt

작은 후속 모델이 수정할 때는 `routes -> plane_client -> ticket_document -> policy` 순서로 읽는 것이 가장 빠릅니다.

## Plane 사전 준비

1. 프로젝트 1개 생성
2. 아래 상태 이름 생성
   - `New`
   - `Triage`
   - `In Progress`
   - `Waiting Customer`
   - `Ready to Reply`
   - `Resolved`
   - `Closed`
3. 아래 label taxonomy 생성
   - channel
     - `channel:email`
     - `channel:chat`
     - `channel:phone`
     - `channel:manual`
   - kind
     - `kind:troubleshooting`
     - `kind:howto`
     - `kind:billing`
     - `kind:feature`
   - product
     - `product:auth`
     - `product:api`
     - `product:admin`
     - `product:billing`
     - `product:unknown`
   - severity
     - `severity:s1`
     - `severity:s2`
     - `severity:s3`
     - `severity:s4`
   - customer
     - `customer:premium`
     - `customer:standard`
     - `customer:unknown`
   - comm
     - `comm:reply-needed`
     - `comm:draft-ready`
     - `comm:resolved-notified`
4. service account PAT 발급
5. project id 확인

## 실행 방법

```bash
git clone <YOUR_GIT_REMOTE_URL> plane-openwebui-tool-server
cd plane-openwebui-tool-server
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

서버가 올라오면 OpenAPI docs는 `http://localhost:8000/docs` 에서 확인할 수 있습니다.

앱은 현재 작업 디렉터리의 `.env`를 자동으로 읽습니다.

Plane adapter scope 원칙:

- workspace-scoped:
  - identifier 기반 상세 조회
  - `/api/v1/workspaces/{workspace_slug}/work-items/{identifier}/`
- project-scoped:
  - project 조회
  - work item list/create/update
  - states / labels / members
  - comments / activities
  - `/api/v1/workspaces/{workspace_slug}/projects/{project_id}/...`

## 환경변수

| 변수 | 설명 | 예시 |
| --- | --- | --- |
| `PLANE_BASE_URL` | Plane 인스턴스 base URL | `https://plane.example.com` |
| `PLANE_WORKSPACE_SLUG` | 대상 workspace slug | `my-workspace` |
| `PLANE_PROJECT_ID` | 대상 project UUID | `project-uuid` |
| `PLANE_API_KEY` | service account PAT | `plane_api_xxx` |
| `DEFAULT_LANGUAGE` | 기본 언어 | `ko` |
| `DEFAULT_TIMEZONE` | 기본 시간대 | `Asia/Seoul` |
| `CONTEXT_CACHE_TTL_SECONDS` | context cache TTL | `60` |
| `DEFAULT_COMMENT_LIMIT` | 기본 comment 조회 수 | `30` |
| `DEFAULT_ACTIVITY_LIMIT` | 기본 activity 조회 수 | `30` |
| `ENFORCE_TRANSITION_POLICY` | optional transition guard 사용 여부 | `false` |
| `LOG_LEVEL` | 로그 레벨 | `INFO` |

예시:

```dotenv
PLANE_BASE_URL=https://plane.example.com
PLANE_WORKSPACE_SLUG=my-workspace
PLANE_PROJECT_ID=project-uuid
PLANE_API_KEY=plane_api_xxx
DEFAULT_LANGUAGE=ko
DEFAULT_TIMEZONE=Asia/Seoul
CONTEXT_CACHE_TTL_SECONDS=60
DEFAULT_COMMENT_LIMIT=30
DEFAULT_ACTIVITY_LIMIT=30
ENFORCE_TRANSITION_POLICY=false
LOG_LEVEL=INFO
```

## OpenWebUI 연결 방법

1. OpenWebUI에서 Global Tool Server로 이 서버를 등록합니다.
2. 이 서버만 tool로 활성화합니다.
3. built-in web search / knowledge / memory 는 비활성화 권장입니다.
4. custom model을 만들고 `prompts/openwebui_system_prompt.txt` 내용을 system prompt로 붙여넣습니다.
5. Native function calling 가능한 모델이면 Native 사용을 권장합니다.
6. 작은 로컬 모델이나 GPT-5 mini 계열은 coarse-grained tool flow를 유지하십시오.

권장 운영 설정:

- 모델: GPT-5 mini
- tool: 이 서버만 활성화
- web search / knowledge / memory: 비활성화 권장
- system prompt: [`prompts/openwebui_system_prompt.txt`](prompts/openwebui_system_prompt.txt) 전체 내용 사용
- 운영 규칙: write 전에 항상 `search` 또는 `context`를 먼저 읽기
- 해석 책임: raw-ish ticket data 해석은 모델이 담당, 서버는 thin wrapper 역할

## Revised v1 API

### Core

- `GET /health`
  - liveness 확인
- `GET /meta/context`
  - 상태, 라벨, 멤버, optional template metadata, optional transition policy 조회
- `POST /tickets/search`
  - state 기반 triage/search
  - 기본 정렬은 항상 `updated_at desc`
  - Plane 필터가 부족하면 서버가 fetch 후 서버측 필터링을 적용
  - raw-ish summary 와 description excerpt 를 반환
- `GET /tickets/{identifier}/context`
  - raw description_html, description_text, parsed sections, 최근 internal notes, 최근 activities, `expected_updated_at` 조회
- `POST /tickets/{identifier}/update`
  - title / description / priority / labels / assignees / state 를 raw patch
- `POST /tickets/{identifier}/comment`
  - internal comment 추가
- `POST /tickets/{identifier}/transition`
  - 상태 변경 wrapper
  - transition policy 는 optional guard

### Secondary

- `POST /tickets/create`
  - 신규 티켓 생성
  - raw description 또는 optional template metadata 기반 생성 지원
- `POST /tickets/{identifier}/upsert-sections`
  - convenience wrapper
  - structured section patch가 필요한 경우에만 사용
- `POST /tickets/{identifier}/save-email-draft`
  - 고객 회신 초안 snapshot 저장

## 템플릿과 editable sections

`editable_sections_by_template`는 optional metadata 입니다. 이 값은 LLM이 참고할 수는 있지만, 서버가 compatibility를 위해 모든 write를 강하게 막는 용도로는 쓰지 않습니다.

예:

```yaml
editable_sections:
  - current_summary
  - confirmed_facts
  - open_questions
  - next_actions_internal
  - customer_reply_points
  - resolution
```

서버는 이 값을 읽어서 `/meta/context`에 노출하고, `upsert-sections` convenience wrapper 에서만 사용합니다.

## 운영 예시 프롬프트

- `Triage 상태 티켓 보여줘`
- `홍길동 담당 In Progress 티켓 찾아줘`
- `SUP-214 현재 상황 요약 갱신해줘`
- `SUP-214 고객 회신 초안 작성해줘`
- `SUP-214 Resolved로 전환해줘`

## 테스트 방법

```bash
PYTHONPATH=. .venv/bin/pytest
```

테스트는 fake Plane client로 동작하므로 외부 Plane 서버 없이 API 표면과 정책 로직을 검증합니다.

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
