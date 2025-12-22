# LOL 데이터 수집 프로젝트 (Data Collection Project)

본 프로젝트는 OPGG 커뮤니티(Talk Tip)와 나무위키(Namuwiki)에서 LOL 관련 데이터를 수집하기 위한 크롤러 모음입니다. 협업 개발자를 위해 환경 설정부터 실행 방법까지 안내합니다.

## 1. 개발 환경 설정 (Setup)

이 프로젝트는 **Python 3.x** 환경에서 동작하며, `playwright` 라이브러리를 사용하여 동적 웹 페이지를 크롤링합니다.

### 1-1. 가상환경 설정 (Virtual Environment)
프로젝트 루트(`data/`)에서 가상환경을 생성하고 활성화합니다.

```bash
# 가상환경 생성 (최초 1회)
python -m venv venv

# 가상환경 활성화 (Mac/Linux)
source venv/bin/activate

# 가상환경 활성화 (Windows)
venv\Scripts\activate
```

### 1-2. 라이브러리 설치 (Dependencies)
필요한 패키지를 설치합니다.

```bash
# 필수 패키지 설치
pip install playwright pandas

# Playwright용 브라우저 설치 (필수)
playwright install chromium
```

---

## 2. 프로젝트 구조 (Directory Structure)

```
data/
├── crawler/
│   ├── opgg/               # OPGG 크롤러 관련 디렉토리
│   │   ├── opgg_crawler.py # 실행 스크립트
│   │   └── outputs/        # 결과 저장소
│   └── namuwiki/           # 나무위키 크롤러 관련 디렉토리
│       └── outputs/        # 결과 저장소
├── preprocessed/           # 데이터 전처리 관련 디렉토리
│   └── opgg/
│       ├── opgg_preprocessed_crawler.py # 전처리 스크립트
│       └── outputs/        # 전처리 결과 저장소 (preprocessed_opgg_tips.json)
├── README.md               # 프로젝트 안내 문서
└── venv/                   # 가상환경
```

---

## 3. 크롤러 실행 가이드 (How to Run)

### 3-1. OPGG 톡 팁 게시판 크롤러
OPGG의 팁 게시판에서 게시글의 상세 내용(본문)과 댓글 목록을 수집합니다.

- **기능**:
  - 게시글 제목, 작성자, 날짜 수집
  - **본문 내용** 전체 추출
  - **댓글 전체** ('더보기' 자동 로드) 수집 (단, '신고', '답글 쓰기' 등 불필요 텍스트 자동 필터링)
- **실행 명령**:
  ```bash
  # 기본 실행 (20개 포스트, 헤드리스 모드)
  python crawler/opgg/opgg_crawler.py

  # 50개 포스트 수집
  python crawler/opgg/opgg_crawler.py --limit 50

  # 브라우저 UI 보면서 실행 (디버깅용)
  python crawler/opgg/opgg_crawler.py --no-headless
  ```
- **옵션 (Options)**:
  - `--limit [숫자]`: 수집할 게시글 최대 개수 (기본값: 20)
  - `--no-headless`: 브라우저 창을 띄워서 실행 (기본값: 헤드리스 모드)

- **결과 확인**:
  - 파일 위치: `crawler/opgg/outputs/opgg_tips.json`
  - 형식: JSON (UTF-8)

### 3-2. 나무위키 크롤러 (Namuwiki)
나무위키에서 특정 LOL 관련 문서를 수집합니다.

- **실행 명령**:
  ```bash
  # 기본 실행 (특정 키워드 수집)
  python crawler/namuwiki/namuwiki_crawler.py --keyword "리그 오브 레전드"

  # 옵션 지정 실행
  python crawler/namuwiki/namuwiki_crawler.py --keyword "페이커" --limit 10 --no-headless
  ```
- **옵션 (Options)**:
  - `--keyword [검색어]`: 수집할 문서의 주제/키워드 (예: "리그 오브 레전드")
  - `--limit [숫자]`: 수집할 문서 최대 개수
  - `--no-headless`: 브라우저 창을 띄워서 실행
- **결과 확인**:
  - **전체 데이터**: `crawler/namuwiki/outputs/namuwiki_articles.json` (전체 통합 JSON)
  - **개별 데이터**: `crawler/namuwiki/outputs/per-article/`
    - 각 문서별로 개별 JSON 파일이 저장됩니다. (예: `기인.json`, `T1.json` 등)


---

## 4. 데이터 전처리 가이드 (Data Preprocessing)

### 4-1. OPGG 데이터 정제 및 중복 제거
수집된 OPGG 데이터를 정제하고 중복 항목을 제거하여 분석에 적합한 형태로 변환합니다.

- **기능**:
  - `crawler/opgg/outputs/opgg_tips.json` 데이터를 로드
  - **텍스트 정제**: 본문 및 댓글의 불필요한 공백, 줄바꿈 제거
  - **중복 제거**: 고유 URL 및 (제목 + 본문) 조합 기반 중복 항목 필터링
- **실행 명령**:
  ```bash
  python preprocessed/opgg/opgg_preprocessed_crawler.py
  ```
- **결과 확인**:
  - 파일 위치: `preprocessed/opgg/outputs/preprocessed_opgg_tips.json`


---

## 5. 참고 사항 (Notes)
- **봇 탐지 우회**: Playwright를 사용하며 User-Agent 설정 및 랜덤 대기 시간(`random.sleep`)이 적용되어 있습니다.
- **데이터 필터링**: OPGG 크롤러는 내용이 없는 빈 댓글이나 시스템 버튼 텍스트를 자동으로 제외하고 저장합니다.
- **수정 문의**: 크롤러 로직 수정이 필요한 경우 `crawler/opgg/opgg_crawler.py` 파일을 참고하세요.
