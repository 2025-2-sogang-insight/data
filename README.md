# LOL Coach AI Backend (Python FastAPI)

<details>
  <summary><h2>⚙️ 개발 환경 설정 (Setup)</h2></summary>

### <mark>🎯 필수 요구사항</mark>

**기반 환경**
> - **Python 3.9+**: 최신 비동기 처리를 위한 파이썬 버전 필요
> - **API Key**: Riot Games API Key 및 Google Gemini (또는 OpenAI) 키 발급

<br/>

### <mark>🚀 설치 및 실행 (Installation)</mark>

**1. 가상환경 및 라이브러리**

> - **가상환경 생성**: 프로젝트 격리를 위해 `venv` 생성 및 활성화
> - **의존성 설치**: `requirements.txt`에 명시된 필수 라이브러리 일괄 설치

```bash
# 가상환경 세팅
python -m venv venv
venv\Scripts\activate

# 라이브러리 설치
pip install -r requirements.txt
```

**2. 환경 변수 설정 (.env)**
> - **보안**: API 키는 코드에 노출하지 않고 `.env` 파일로 관리함
> - **설정값**: `RIOT_API_KEY`, `GOOGLE_API_KEY` 필수 입력

**3. 서버 실행**

```bash
uvicorn main:app --reload
```
> - **접속 주소**: `http://localhost:8000`
> - **API 문서**: `http://localhost:8000/docs` (Swagger UI 제공)

</details>


<details>
  <summary><h2>📂 프로젝트 구조 (Structure)</h2></summary>

### <mark>💾 디렉토리 구조</mark>

```
backend/
├── main.py                 # FastAPI 앱 엔트리포인트 
├── routers/                # API 라우터 (기능별 분리)
│   ├── coach.py            # AI 코칭/분석 API
│   ├── match.py            # 매치 히스토리 조회
│   └── search.py           # 소환사 검색
├── rag/                    # RAG (검색 증강 생성) 서비스
│   ├── service.py          # LangChain + LLM 분석 로직
│   ├── settings.py         # 모델 파라미터 및 DB 설정
│   └── create_db.py        # Vector DB 구축 스크립트
├── services/               # 외부 연동
│   └── riot_service.py     # Riot Games API 통신 핸들러
└── schemas/                # 데이터 검증 (Pydantic)
```

</details>


<details>
  <summary><h2>🚀 핵심 기능 및 흐름 (Key Features & Flow)</h2></summary>

### <mark>🔄 서비스 유기적 흐름 (Workflow)</mark>

**Step 1: 소환사 식별 (Search)**
> 소환사명으로 고유 식별자(PUUID)를 조회하여 분석 대상을 특정함

**Step 2: 데이터 확보 (Match)**
> 해당 소환사의 최근 전적 리스트를 불러와 분석할 특정 경기를 선택함

**Step 3: 심층 분석 (Coach)**
> 선택된 경기의 타임라인 데이터를 AI에게 전달하여 정밀 코칭 리포트를 생성함

<br/>

### <mark>🔍 1. 소환사 검색 (Search)</mark>

**API 엔드포인트**
> `GET /search/{summoner_name}/{tagline}`

**기능 설명 (Description)**
> - **기본 정보**: 태그라인을 포함한 소환사명으로 PUUID 및 레벨 조회
> - **전적 요약**: 최근 20게임의 승률 기여도 및 주력 챔피언 분석

<br/>

### <mark>⚔️ 2. 매치 상세 조회 (Match)</mark>

**API 엔드포인트**
> `GET /match/{match_id}`

**기능 설명 (Description)**
> - **세부 스탯**: 분당 데미지(DPM), 시야 점수, 골드 격차 등 상세 지표 제공
> - **타임라인**: 시간대별 아이템 빌드 및 동선 데이터 확보하여 AI 분석의 기초 데이터로 활용

<br/>

### <mark>🤖 3. AI 게임 코칭 (Coach)</mark>

**API 엔드포인트**
> `POST /coach/analyze`

**기능 설명 (Description)**
> - **데이터 종합**: Match 단계에서 확보한 데이터와 타임라인을 결합
> - **심층 분석**: LLM이 승패 요인을 파악하고 구체적인 피드백을 생성함

**분석 프로세스 (Process Overview)**
> - **① 데이터 요약**: 수천 줄의 복잡한 원본(Raw) JSON 데이터에서 핵심 지표(KDA, 골드, 아이템, 딜량)만 추출
> - **② 중요 장면 감지**: 킬/데스, 오브젝트 처치 등 게임의 승부처(Turning Point) 자동 식별
> - **③ 지식 검색 (RAG)**: ChromaDB에서 해당 챔피언의 정석 운영법과 상대법을 검색하여 참조
> - **④ 리포트 생성**: 위 정보를 바탕으로 코칭 리포트(한줄평, 상세 분석) 작성

**분석 예시 (Example)**
> - **입력 (Input)**: `페이커(아리) vs 쵸비(요네)` 미드 라인전 데이터 + 15분 용 앞 한타 데이터
> - **출력 (Output)**:
>   - **한줄평**: "초반 라인전 주도권은 좋았으나, 15분 용 앞 한타에서 포지셔닝 실수로 제압골을 내준 것이 패인입니다."
>   - **피드백**: "요네 상대로는 E(매혹)를 아끼고 Q 끝사거리를 유지하며 견제하는 것이 핵심입니다."

</details>


<details>
  <summary><h2>🛠 기술 스택 (Tech Stack)</h2></summary>

### <mark>📃 스택 목록</mark>

**Framework & Language**
> - **Python**: 데이터 분석 및 AI 라이브러리 활용에 최적화
> - **FastAPI**: 비동기 처리 지원 및 자동 문서화(Swagger) 강점

**AI & Database**
> - **LangChain**: LLM 페르소나 설정 및 프롬프트 체이닝 관리
> - **Google Gemini Pro**: 높은 성능과 긴 컨텍스트 처리가 가능한 LLM 모델 사용
> - **ChromaDB**: 벡터 임베딩 저장 및 유사도 검색을 위한 경량화 DB

**External API**
> - **Riot Games API**: 공식 인게임 데이터 원천 (Match-V5, Summoner-V4)

</details>