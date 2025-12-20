# data

## 디렉토리 구조
- `crawler/namuwiki/namuwiki_crawler.py`: prefix 열거(`--prefix`)와 개별 문서 저장(`--per-article`)을 모두 지원하며, 결과 메타 데이터를 `outputs/namuwiki_articles.json`에 누적합니다.
- `crawler/namuwiki/outputs/`: 기본 집계 JSON과 `--per-article` 플래그가 활성화된 경우 각 문서별 파일(`리그오브레전드-챔피언.json` 등)을 저장하는 위치입니다.
- `src/` 등의 디렉토리는 이후 OP.GG, 다른 출처별 크롤러를 추가할 때 참고할 수 있도록 유지합니다.

## 나무위키 크롤러 사용법
1. 터미널에서 `lol` 루트로 이동한 뒤 `source venv/bin/activate` (macOS/Linux) 또는 `venv\\Scripts\\activate` (Windows)로 가상환경을 활성화합니다.
2. `pip install -r data/requirements.txt`로 의존성을 설치합니다.
3. Playwright가 브라우저를 다운로드했는지 확인합니다(`playwright install`).
4. 기본 실행 예시:
   - `python data/crawler/namuwiki/namuwiki_crawler.py --prefix "리그 오브 레전드/" --per-article` : prefix 하위 문서를 집계하고 `outputs/리그오브레전드-*.json`으로 저장합니다. 기본은 API 방식이지만 API 호출이 막히면 자동으로 Playwright 렌더링으로 대체합니다.
   - `python data/crawler/namuwiki/namuwiki_crawler.py --prefix "리그 오브 레전드/" --per-article --prefix-method playwright` : Playwright 렌더링만 쓰고 API 요청은 생략합니다(CF 제한이 있어 API 피벗을 못 할 때 사용).
   - `python data/crawler/namuwiki/namuwiki_crawler.py --prefix "리그 오브 레전드/" --per-article --use-playwright-fetch` : 각 문서를 Playwright로 렌더링해서 가져오며, reCAPTCHA가 뜨지만 브라우저로는 내용을 확인할 수 있는 경우 브라우저 모드를 통해 실제 콘텐츠를 확보합니다.
   - `python data/crawler/namuwiki/namuwiki_crawler.py --titles /path/to/your/list.txt` : 수동 제목 목록을 이용해 크롤링하고 싶을 때.
5. 옵션 정리:
   - `--limit N`: 상위 N개 제목만 처리합니다(디버그/테스트용).
- `--per-article-dir`: 문서별 저장 위치를 기본 `outputs/`가 아닌 다른 폴더로 지정할 수 있습니다.
- `--prefix-method [api|playwright|auto]`: API/Playwright/자동(cF 실패 시 Playwright) 중 prefix 열거 방식을 선택합니다.
- `--namespace`: MediaWiki에서 사용할 네임스페이스 번호를 바꿔야 하는 경우 값 조정.
- `--use-playwright-fetch`: reCAPTCHA/hCaptcha가 만들어내는 빈 페이지를 피하기 위해 Playwright로 렌더링된 HTML을 가져옵니다.
- `--playwright-browser [chromium|firefox|webkit]`, `--playwright-headed`, `--playwright-timeout`, `--playwright-wait`: Playwright 세션을 커스터마이징하여 필요한 브라우저 엔진과 로딩 타임을 조절할 수 있습니다. 헤드풀 모드는 `--playwright-headed`로 켜고, `playwright install`을 통해 브라우저를 미리 설치해 주세요.

## reCAPTCHA/차단 대응
- 기본 `requests` 모드로 반복하다가 `description`/`first_paragraph`에 reCAPTCHA 안내문만 뜨면 `--use-playwright-fetch` 플래그를 켜고 다시 한번 실행하세요.
- Playwright가 캡차 페이지를 띄운 뒤 `--playwright-headed`로 창을 띄워 직접 풀어놓으면, 그 세션을 계속 써서 나머지 문서도 정상 콘텐츠를 가져올 수 있습니다. 필요시 `--playwright-timeout`/`--playwright-wait`를 늘려서 렌더링 안정성을 확보하세요.
- Playwright로 내용을 받아온 후 결과를 `outputs/`에서 확인하면서 reCAPTCHA 시각이 줄었으면 그 방식으로 계속 사용하면 됩니다. 추후 자동감지를 원하면 `fetch_page`에서 reCAPTCHA 텍스트를 체크하여 Playwright로 재시도하는 로직을 추가하는 것도 고려해 보세요.

## 문서 수집 전략
- prefix 기반 크롤링(`--prefix`)은 `특수:PrefixIndex`/MediaWiki API를 통해 모든 하위 제목을 순차적으로 취합하므로, `리그 오브 레전드/챔피언` 같은 중첩된 문서도 끝까지 스캔할 수 있습니다.
- `--per-article`를 켜면 각 문서의 메타 데이터가 `per-article-dir`(기본 `outputs/`)에 `리그오브레전드-챔피언.json`처럼 저장됩니다. 공간을 확보하려면 이 옵션을 끈 뒤 전체 집계를 참고할 수 있습니다.
- 필요하다면 `--titles`에 사용자 정의 파일을 넘겨서 prefix 외 선택적인 문서 세트를 조합할 수도 있습니다.
