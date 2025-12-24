# LOL-Coach DATA README

OP.GG 커뮤니티와 나무위키에서 롤 관련 데이터를 수집하기 위한 크롤러 모음

<br>

## ⚙️ 개발 환경 설정 (Setup)

### <mark>🎯 필수 환경 (Prerequisites)</mark>

**기반 시스템**
- **Python 3.9+**: 최신 파이썬 런타임 필요함
- **Playwright**: 동적 웹 수집을 위한 브라우저 자동화 도구

<br/>

### <mark>🚀 설치 및 실행 (Quick Start)</mark>

<details>
<summary><strong>1. 환경 구성 (Installation)</strong></summary>

- **가상환경**: `venv`로 독립된 실행 환경 구성함
- **의존성 설치**: `requirements.txt` 내 필수 라이브러리 일괄 설치함
```bash
# 초기 세팅 명령어
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```
</details>

<details>
<summary><strong>2. 크롤러 구동 (Installation)</strong></summary>

```bash
# 나무위키 수집 (Seed: 롤)
python crawler/namuwiki/namuwiki_crawler.py --seed "리그 오브 레전드" --limit 50

# OPGG 팁 수집
python crawler/opgg/opgg_crawler.py --limit 100
```

</details>
<br>

## 📂 프로젝트 구조 (Project Structure)


### <mark>💾 디렉토리 구성</mark>
<details>
  <summary><strong>디렉토리 구조</strong></summary>
  
```
data/
├── crawler/                # 데이터 수집 (Crawling)
│   ├── namuwiki/           # [Source 1] 나무위키 크롤러
│   │   ├── namuwiki_crawler.py
│   │   └── outputs/        # 결과 JSON
│   └── opgg/               # [Source 2] OPGG 팁 크롤러
│       ├── opgg_crawler.py
│       └── outputs/        # 결과 JSON
└── preprocessed/           # 데이터 전처리 (Preprocessing) 결과
    ├── namuwiki/           
    └── opgg/               
```
  
</details>



</details>

<br>

## 🚀 데이터 파이프라인 (Pipeline)

### <mark>🕷️ 데이터 수집 (Crawling)</mark>

<details>
<summary><strong>1. 나무위키 </strong></summary>

- **시드 확장**: `BeautifulSoup`으로 문서 내 분류 표를 파싱해 하위 문서(챔피언, 아이템) 링크를 자동 추출함
- **구조화 수집**: 제목, 본문, 썸네일 등을 수집하고 섹션(Heading) 단위로 내용을 구조화하여 데이터베이스에 저장함
- **동적 처리**: `Playwright`를 통해 JavaScript 렌더링이 완료된 완전한 HTML을 확보함
</details>

<details>
<summary><strong>2. OP.GG </strong></summary>

- **페이지 순회**: `Playwright` 브라우저로 게시판 목록을 순차적으로 탐색하며 상세 게시글 URL을 수집함
- **동적 로딩**: 스크롤 다운 기능을 제어해 숨겨진 콘텐츠와 댓글을 모두 확보함
- **데이터 추출**: 게시글과 댓글 정보를 `JSON` 형식으로 구조화하여 추출함
</details>


<br>

### <mark>✨ 데이터 정제 (Preprocessing)</mark>

<details>
<summary><strong>1. 나무위키 </strong></summary>

- **노이즈 제거**: `RegEx`(정규표현식)를 활용해 본문 각주(`[1]`) 및 메타데이터를 정밀하게 삭제함
- **중복 방지**: 메모리 상의 `Set` 자료구조로 이미 수집한 문서를 체크해 중복 저장을 차단함

</details>

<details>
<summary><strong>2. OP.GG </strong></summary>

- **텍스트 정규화**: `Pandas` 등을 이용해 불규칙한 공백과 줄바꿈을 단일 공백으로 통일함
- **필터링**: 분석에 불필요한 시스템 텍스트('신고' 등)를 조건부 로직으로 제거함
- **중복 제거**: 문서 내용의 `Hash`(해시값) 비교를 통해 중복된 게시글을 이중으로 걸러냄
</details>


<br>

### <mark>📝 정제 효과 (Before & After)</mark>

<details>
<summary><strong>Case 1: 위키 각주 제거 </strong></summary>

> **Before**
> ```text
> 페이커는 역대 최고의 선수이다.[3] 그의 플레이는... [편집]
> ```
> ⬇️
> **After**
> ```text
> 페이커는 역대 최고의 선수이다. 그의 플레이는...
> ```
</details>

<details>
<summary><strong>Case 2: 댓글 공백 정리 </strong></summary>

> **Before**
> ```text
> 		ㄹㅇㅋㅋ  
> (이모티콘)
> ```
> ⬇️
> **After**
> ```text
> ㄹㅇㅋㅋ
> ```
</details>

<br/>

### <mark>💾 최종 결과물 (Output Examples)</mark>

<details>
<summary><strong>1. 나무위키 (JSON) </strong></summary>

```json
{
  "requested_title": "말파이트",
  "response_title": "말파이트",
  "description": "리그 오브 레전드의 챔피언 말파이트 거석의 파편...",
  "content_text": "리그 오브 레전드의 챔피언 말파이트 거석의 파편...",
  "sections": [
    {
      "heading": "개요",
      "text": "가능한 한 빨리 가라. (Go as fast as you can.)..."
    },
    {
      "heading": "배경",
      "text": "조화가 엉망이 된 세상은 거석의 파편이 고칠 것이다..."
    }
  ]
}
```
</details>

<details>
<summary><strong>2. OP.GG (JSON) </strong></summary>

```json
{
  "title": "탑 제이스 무라마나 빨간약",
  "nickname": "5라인중롤제일못하고인성더러운라인은원딜",
  "date": "2025년 12월 19일 금요일 오후 12:06",
  "content": "훈련봇 방어력 대충 그 코어 나올때 시점으로 세팅하고...",
  "comments": []
},
{
  "title": "천상계 빌드 소개-무라마나 안가는 제이스",
  "content": "이 빌드는 우선 제이스 원챔 챌 김망치 빌드임을 알림...",
  "comments": [
    {
      "nickname": "롤체운빨좋망겜",
      "content": "와씨 망치햄 전적봐라 천상계 양학하고다니네;",
      "date": "2일 전"
    }
  ]
}
```
</details>





</details>

<br>

## 🛠 기술 스택 (Tech Stack)

### <mark>📃 핵심 기술</mark>

<details>
<summary><strong>수집 (Crawling) </strong></summary>

- **Playwright**: 동적 웹페이지 제어 (Headless Browser)
- **BeautifulSoup4**: HTML 구조 파싱
</details>

<details>
<summary><strong>가공 (Processing) </strong></summary>

- **Pandas**: 데이터 포맷 변환 및 저장
- **RegEx**: 텍스트 노이즈 정제
</details>


</details>
