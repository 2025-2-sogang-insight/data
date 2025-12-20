"""
Namuwiki crawler (seed table -> group -> titles -> crawl + by-group outputs)

- From a seed article (e.g., "리그 오브 레전드"), find large nav tables.
- Parse rows (tr):
    left td  => group name
    right td => /w/ links => titles
- Save:
    outputs/<seed>_groups.json          (group -> titles)
    outputs/<seed>_titles_flat.txt      (deduped titles)
- Crawl those titles:
    outputs/namuwiki_articles.json
    outputs/per-article/*.json (optional)
- By-group outputs (optional):
    outputs/by_group/<group>.json       (articles grouped by group name)
    outputs/title_to_groups.json        (title -> [groups])

Extra sources:
- --add-category "분류:리그 오브 레전드/챔피언" 같은 페이지에서 /w/ 링크를 추가 수집
  (챔피언 목록처럼 div inline-flex 그리드 구조도 지원)

Speed knobs:
- --light            : skip full_text/sections (훨씬 빠름)
- --no-sleep         : 요청 딜레이 제거(빨라지지만 부담↑)
- --min-delay/--max-delay : 딜레이 조절
- --workers N        : 스레드 병렬(권장 4~8)
- --expand-during-crawl : 1차 크롤링 중 /w/ 링크를 같이 수집해서 2차로 추가 크롤링(추가 요청 “0”으로 수집)

Usage:
python crawler/namuwiki/namuwiki_crawler.py --seed "리그 오브 레전드" --light --workers 6 --by-group
python crawler/namuwiki/namuwiki_crawler.py --seed "리그 오브 레전드" --add-category "분류:리그 오브 레전드/챔피언" --category-group-name "챔피언" --light --workers 6 --by-group
python crawler/namuwiki/namuwiki_crawler.py --seed "리그 오브 레전드" --light --workers 6 --expand-during-crawl --expand-limit 300
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, DefaultDict, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from tqdm import tqdm

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


# =========================
# Config
# =========================

BASE = "https://namu.wiki"
WIKI_BASE = f"{BASE}/w/"
REQUEST_TIMEOUT = 15

RETRY_CONFIG = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NamuwikiCrawler/1.0; +https://example.com/bot)",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

MIN_DELAY_SEC = 0.8
MAX_DELAY_SEC = 1.8

DESCRIPTION_MAX_CHARS = 400
FIRST_PARAGRAPH_MAX_CHARS = 1200

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

PLAYWRIGHT_DEFAULT_WAIT_SEC = 0.6


class PlaywrightFetcher:
    """Playwright 브라우저에서 렌더링된 HTML을 가져오는 헬퍼."""

    def __init__(self, browser_name: str, headless: bool, timeout_sec: float, wait_after_load: float):
        if sync_playwright is None:
            raise RuntimeError("Playwright가 설치되어 있지 않습니다; data/requirements.txt를 보고 설치하세요.")
        self._playwright = sync_playwright().start()
        browser_factory = getattr(self._playwright, browser_name, None)
        if browser_factory is None:
            self._playwright.stop()
            raise RuntimeError(f"지원되지 않는 브라우저 '{browser_name}'입니다.")
        self._browser = browser_factory.launch(headless=headless)
        self._timeout_ms = int(timeout_sec * 1000)
        self._wait_ms = int(wait_after_load * 1000)

    def fetch(self, url: str) -> str:
        page = self._browser.new_page()
        page.set_extra_http_headers(DEFAULT_HEADERS)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            if self._wait_ms:
                page.wait_for_timeout(self._wait_ms)
            return page.content()
        finally:
            page.close()

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._playwright.stop()


# =========================
# Helpers
# =========================

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "-", name)
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "item"


def sleep_jitter(min_delay: float, max_delay: float, enabled: bool = True) -> None:
    if not enabled:
        return
    time.sleep(random.uniform(min_delay, max_delay))


def build_article_url(title: str) -> str:
    return WIKI_BASE + urllib.parse.quote(title, safe="")


def load_titles(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"titles file not found: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_text(element: Optional[Any]) -> Optional[str]:
    if element is None:
        return None
    return element.get_text(separator=" ", strip=True)


def decode_title_from_href(href: str) -> Optional[str]:
    if not href.startswith("/w/"):
        return None
    raw = href[3:]
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    if not raw:
        return None
    try:
        return urllib.parse.unquote(raw)
    except Exception:
        return raw


def normalize_group_name(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip()
    t = t.replace("[펼치기 · 접기]", "").strip()
    return t or None


def clip_text(s: Optional[str], n: int) -> Optional[str]:
    if not s:
        return s
    s = s.strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def looks_like_noise(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if t.startswith("파일:") or t.startswith("attachment/"):
        return True
    if len(t) < 20:
        return True
    if "펼치기" in t and "접기" in t and len(t) < 60:
        return True
    return False


def looks_like_license(text: str) -> bool:
    lower = text.lower()
    if lower.startswith("이 저작물은"):
        return True
    if "cc by" in lower and "nc" in lower:
        return True
    if "기여하신 문서" in lower and "저작권" in lower:
        return True
    if "나무위키는 백과사전" in lower:
        return True
    if "나무위키는 위키위키" in lower:
        return True
    if "작성한 문서" in lower and "저작권" in lower:
        return True
    return False


@retry(retry=retry_if_exception_type(requests.RequestException), **RETRY_CONFIG)
def fetch_page(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


FetchFn = Callable[[requests.Session, str], str]

# =========================
# Expand (link extraction)
# =========================

def extract_titles_from_page(
    html: str,
    include_prefixes: Optional[List[str]] = None,
    exclude_prefixes: Optional[List[str]] = None,
    container_selector: Optional[str] = None,
) -> List[str]:
    soup = BeautifulSoup(html, "lxml")

    root = soup
    if container_selector:
        node = soup.select_one(container_selector)
        if node is not None:
            root = node

    titles: Set[str] = set()
    for a in root.select('a[href^="/w/"]'):
        href = a.get("href", "")
        t = decode_title_from_href(href)
        if not t:
            continue
        if t.startswith(("특수:", "파일:")):
            continue
        if exclude_prefixes and any(t.startswith(p) for p in exclude_prefixes):
            continue
        if include_prefixes and not any(t.startswith(p) for p in include_prefixes):
            continue
        titles.add(t)

    return sorted(titles)


def extract_titles_from_category_grid(
    html: str,
    container_selector: Optional[str] = None,
) -> List[str]:
    """
    분류:리그 오브 레전드/챔피언 같은 페이지의 챔피언 그리드(div inline-flex)에서 타이틀 추출.
    스크린샷에 나온:
      <div style="display:inline-flex; ..."><a href="/w/가렌" title="가렌"> ... </a></div>
    구조 대응.
    """
    soup = BeautifulSoup(html, "lxml")

    root = soup
    if container_selector:
        node = soup.select_one(container_selector)
        if node is not None:
            root = node

    titles: Set[str] = set()
    for a in root.select('div[style*="inline-flex"] a[href^="/w/"]'):
        href = a.get("href", "")
        t = decode_title_from_href(href)
        if not t:
            continue
        if t.startswith(("특수:", "파일:", "분류:")):
            continue
        titles.add(t)

    return sorted(titles)


# =========================
# Article parsing
# =========================

def find_article_body_container(soup: BeautifulSoup) -> Optional[Any]:
    selectors = [
        '[itemprop="articleBody"]',
        "div.wiki-article",
        "div.wiki-content",
        "article",
        "main",
    ]
    for sel in selectors:
        node = soup.select_one(sel)
        if node is not None:
            return node
    return None


def extract_first_meaningful_paragraph(soup: BeautifulSoup) -> Optional[str]:
    body = find_article_body_container(soup) or soup

    for sel in [
        "script", "style", "noscript",
        "aside",
        "table",
        "nav",
        "header",
        "footer",
        "div.wiki-toc",
        "div.toc",
        "div.wiki-folding",
    ]:
        for x in body.select(sel):
            x.decompose()

    candidates: List[str] = []
    for node in body.select("div.wiki-paragraph, p, div.paragraph"):
        txt = node.get_text(" ", strip=True)
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            candidates.append(txt)

    for txt in candidates:
        if looks_like_noise(txt):
            continue
        if looks_like_license(txt):
            continue
        return clip_text(txt, FIRST_PARAGRAPH_MAX_CHARS)

    return None


def extract_full_text(soup: BeautifulSoup) -> Optional[str]:
    body = find_article_body_container(soup) or soup

    for sel in [
        "script", "style", "noscript",
        "aside",
        "nav",
        "header",
        "footer",
        "div.wiki-toc",
        "div.toc",
    ]:
        for x in body.select(sel):
            x.decompose()

    for x in body.select("table"):
        x.decompose()

    txt = body.get_text(" ", strip=True)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt or None


def extract_sections_text(soup: BeautifulSoup) -> List[Dict[str, str]]:
    body = find_article_body_container(soup) or soup
    sections: List[Dict[str, str]] = []

    headers = body.select("h2, h3, h4")
    if not headers:
        full = extract_full_text(soup)
        return [{"heading": "FULL", "text": full}] if full else []

    for h in headers:
        heading = h.get_text(" ", strip=True)
        texts: List[str] = []
        for sib in h.find_all_next():
            if sib == h:
                continue
            if sib.name in ("h2", "h3", "h4"):
                break
            if sib.name in ("script", "style"):
                continue
            t = sib.get_text(" ", strip=True)
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                texts.append(t)

        merged = " ".join(texts).strip()
        if merged:
            sections.append({"heading": heading, "text": merged})

    return sections


def parse_article(requested_title: str, url: str, html: str, light: bool = False) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_img = soup.find("meta", property="og:image")

    title_tag = soup.find("title")
    time_tag = soup.find("time", datetime=True)

    response_title = (
        og_title["content"].strip()
        if og_title and og_title.has_attr("content")
        else extract_text(title_tag)
    )
    og_description = (
        og_desc["content"].strip()
        if og_desc and og_desc.has_attr("content")
        else None
    )
    thumbnail = og_img["content"].strip() if og_img and og_img.has_attr("content") else None
    last_modified = time_tag["datetime"] if time_tag and time_tag.has_attr("datetime") else None

    first_para = extract_first_meaningful_paragraph(soup)

    if first_para and not looks_like_noise(first_para):
        description = clip_text(first_para, DESCRIPTION_MAX_CHARS)
    else:
        description = clip_text(og_description, DESCRIPTION_MAX_CHARS)

    full_text = None
    sections: List[Dict[str, str]] = []
    if not light:
        full_text = extract_full_text(soup)
        sections = extract_sections_text(soup)

    return {
        "requested_title": requested_title,
        "url": url,
        "response_title": response_title,
        "description": description,
        "first_paragraph": first_para,
        "content_text": full_text,
        "sections": sections,
        "last_modified": last_modified,
        "thumbnail": thumbnail,
        "retrieved_at": datetime.utcnow().isoformat() + "Z",
    }


# =========================
# Seed table -> groups -> titles
# =========================

def _select_nav_tables(
    soup: BeautifulSoup,
    min_links_in_table: int,
    min_rich_rows: int = 5,
    rich_row_links: int = 3
) -> List[Any]:
    tables = soup.find_all("table")
    scored: List[Tuple[int, Any]] = []

    for t in tables:
        all_links = len(t.select('a[href^="/w/"]'))
        if all_links < min_links_in_table:
            continue

        rows = t.find_all("tr")
        row_counts = [len(r.select('a[href^="/w/"]')) for r in rows]
        rich_rows = sum(1 for c in row_counts if c >= rich_row_links)

        if rich_rows < min_rich_rows:
            continue

        scored.append((all_links, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:5]]


def _row_to_group_and_titles(tr: Any, min_links_in_row: int = 3) -> Optional[Tuple[str, List[str]]]:
    tds = tr.find_all("td", recursive=False)
    if len(tds) < 2:
        tds = tr.find_all(["th", "td"], recursive=False)
        if len(tds) < 2:
            return None

    left, right = tds[0], tds[1]
    group = normalize_group_name(extract_text(left))
    if not group:
        return None

    if re.fullmatch(r"(?:\d{4}\s*){2,}", group):
        return None

    titles: List[str] = []
    for a in right.select('a[href^="/w/"]'):
        href = a.get("href", "")
        title = decode_title_from_href(href)
        if not title:
            continue
        if title.startswith(("특수:", "파일:")):
            continue
        titles.append(title)

    titles = [t for t in titles if t]
    if len(titles) < min_links_in_row:
        return None

    seen: Set[str] = set()
    deduped: List[str] = []
    for t in titles:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)

    return group, deduped


def collect_grouped_titles_from_seed(
    seed_title: str,
    session: requests.Session,
    min_links_in_table: int = 30,
    debug_dir: Optional[Path] = None,
    min_links_in_row: int = 3,
) -> Dict[str, List[str]]:
    seed_url = build_article_url(seed_title)
    html = fetch_page(session, seed_url)

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{sanitize_filename(seed_title)}_seed.html").write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "lxml")
    tables = _select_nav_tables(soup, min_links_in_table=min_links_in_table)

    grouped: Dict[str, List[str]] = {}
    seen_global: Set[str] = set()

    for table in tables:
        for tr in table.find_all("tr", recursive=True):
            parsed = _row_to_group_and_titles(tr, min_links_in_row=min_links_in_row)
            if not parsed:
                continue
            group, titles = parsed

            filtered: List[str] = []
            for t in titles:
                if t in seen_global:
                    continue
                seen_global.add(t)
                filtered.append(t)

            if not filtered:
                continue

            grouped.setdefault(group, []).extend(filtered)

    for g, titles in list(grouped.items()):
        seen: Set[str] = set()
        deduped: List[str] = []
        for t in titles:
            if t in seen:
                continue
            seen.add(t)
            deduped.append(t)
        grouped[g] = deduped

    if debug_dir is not None:
        (debug_dir / f"{sanitize_filename(seed_title)}_groups.json").write_text(
            json.dumps(grouped, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return grouped


def flatten_grouped_titles(grouped: Dict[str, List[str]]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for g in grouped.keys():
        for t in grouped[g]:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
    return out


def save_group_outputs(
    seed_title: str,
    output_dir: Path,
    grouped: Dict[str, List[str]],
) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    groups_path = output_dir / f"{sanitize_filename(seed_title)}_groups.json"
    flat_path = output_dir / f"{sanitize_filename(seed_title)}_titles_flat.txt"

    groups_path.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")

    flat_titles = flatten_grouped_titles(grouped)
    flat_path.write_text("\n".join(flat_titles) + "\n", encoding="utf-8")

    return groups_path, flat_path


def build_title_to_groups(grouped: Dict[str, List[str]]) -> Dict[str, List[str]]:
    m: DefaultDict[str, List[str]] = defaultdict(list)
    for g, titles in grouped.items():
        for t in titles:
            m[t].append(g)
    return dict(m)


# =========================
# Output helpers
# =========================

def write_per_article(article: Dict[str, Any], output_dir: Path, title: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    name = sanitize_filename(title)
    path = output_dir / f"{name}.json"
    path.write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")


def save_by_group(by_group: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for group, items in by_group.items():
        path = out_dir / f"{sanitize_filename(group)}.json"
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# =========================
# Crawl (supports workers + expand-during-crawl)
# =========================

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


def crawl_titles(
    titles: List[str],
    output_path: Path,
    per_article: bool,
    per_article_dir: Path,
    limit: Optional[int] = None,
    title_to_groups: Optional[Dict[str, List[str]]] = None,
    by_group_dir: Optional[Path] = None,
    fetch_page_func: FetchFn = fetch_page,
    *,
    light_mode: bool = False,
    workers: int = 1,
    sleep_enabled: bool = True,
    min_delay: float = MIN_DELAY_SEC,
    max_delay: float = MAX_DELAY_SEC,
    expand_during_crawl: bool = False,
    expand_include_prefix: Optional[List[str]] = None,
    expand_exclude_prefix: Optional[List[str]] = None,
    expand_container: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if limit is not None:
        titles = titles[:limit]

    articles: List[Dict[str, Any]] = []
    by_group: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)

    extra_seen: Set[str] = set()
    extra_collected: List[str] = []

    def work(title: str) -> Tuple[str, Optional[Dict[str, Any]], Optional[str], List[str]]:
        url = build_article_url(title)
        session = _make_session()
        try:
            sleep_jitter(min_delay, max_delay, enabled=sleep_enabled)
            html = fetch_page_func(session, url)

            extra_titles: List[str] = []
            if expand_during_crawl:
                extra_titles = extract_titles_from_page(
                    html,
                    include_prefixes=expand_include_prefix,
                    exclude_prefixes=expand_exclude_prefix,
                    container_selector=expand_container,
                )

            article = parse_article(title, url, html, light=light_mode)

            groups = (title_to_groups or {}).get(title, [])
            if groups:
                article["groups"] = groups

            return (title, article, None, extra_titles)

        except requests.HTTPError as err:
            return (title, None, f"HTTPError: {err}", [])
        except requests.RequestException as err:
            return (title, None, f"RequestException: {err}", [])
        except Exception as err:
            return (title, None, f"Unexpected: {err}", [])

    if workers <= 1:
        for title in tqdm(titles, desc="Crawling Namuwiki", unit="article"):
            t, article, err, extra = work(title)
            if err:
                LOGGER.warning("Skipping %s: %s", t, err)
                continue

            assert article is not None
            articles.append(article)

            if per_article:
                write_per_article(article, per_article_dir, t)

            groups = article.get("groups", [])
            if by_group_dir is not None and groups:
                for g in groups:
                    by_group[g].append(article)

            if expand_during_crawl and extra:
                for nt in extra:
                    if nt not in extra_seen:
                        extra_seen.add(nt)
                        extra_collected.append(nt)

    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(work, t) for t in titles]
            for fut in tqdm(as_completed(futures), total=len(futures), desc="Crawling Namuwiki", unit="article"):
                t, article, err, extra = fut.result()
                if err:
                    LOGGER.warning("Skipping %s: %s", t, err)
                    continue

                assert article is not None
                articles.append(article)

                if per_article:
                    write_per_article(article, per_article_dir, t)

                groups = article.get("groups", [])
                if by_group_dir is not None and groups:
                    for g in groups:
                        by_group[g].append(article)

                if expand_during_crawl and extra:
                    for nt in extra:
                        if nt not in extra_seen:
                            extra_seen.add(nt)
                            extra_collected.append(nt)

    if articles:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("Saved %d records to %s", len(articles), output_path)
    else:
        LOGGER.warning("No articles were crawled.")

    if by_group_dir is not None and by_group:
        save_by_group(dict(by_group), by_group_dir)
        LOGGER.info("Saved grouped outputs to %s (%d groups)", by_group_dir, len(by_group))

    return articles, extra_collected


# =========================
# CLI
# =========================

def main() -> None:
    base_dir = Path(__file__).resolve().parent
    outputs_dir = base_dir / "outputs"
    debug_dir = outputs_dir / "debug"
    default_output = outputs_dir / "namuwiki_articles.json"

    parser = argparse.ArgumentParser(description="Namuwiki crawler (seed table grouped links).")
    parser.add_argument("--seed", type=str, help='Seed article title (e.g., "리그 오브 레전드").')
    parser.add_argument("--titles", type=Path, help="Path to newline-separated titles file (optional).")

    parser.add_argument("--output", type=Path, default=default_output, help="Combined JSON output path.")
    parser.add_argument("--per-article", action="store_true", help="Store each article in its own JSON file.")
    parser.add_argument("--per-article-dir", type=Path, default=None, help="Directory for per-article JSONs.")
    parser.add_argument(
        "--use-playwright-fetch",
        action="store_true",
        help="Playwright로 렌더링된 HTML을 받아와서 요청을 수행합니다.",
    )
    parser.add_argument(
        "--playwright-browser",
        choices=["chromium", "firefox", "webkit"],
        default="chromium",
        help="Playwright를 사용할 브라우저 종류.",
    )
    parser.add_argument(
        "--playwright-headed",
        action="store_true",
        help="Playwright를 헤드풀(headful) 모드로 실행합니다 (기본: headless).",
    )
    parser.add_argument(
        "--playwright-timeout",
        type=float,
        default=REQUEST_TIMEOUT,
        help="Playwright가 페이지를 기다리는 최대 시간(초).",
    )
    parser.add_argument(
        "--playwright-wait",
        type=float,
        default=PLAYWRIGHT_DEFAULT_WAIT_SEC,
        help="페이지 렌더링 후 추가로 기다릴 시간(초).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max number of titles to crawl (pass-1).")
    parser.add_argument("--debug-seed", action="store_true", help="Dump seed html + debug grouped outputs.")
    parser.add_argument("--min-links", type=int, default=30, help="Min /w/ links in a table to treat it as nav table.")
    parser.add_argument("--min-links-in-row", type=int, default=3, help="Min /w/ links in a row to treat it as a group row.")
    parser.add_argument("--skip-crawl", action="store_true", help="Only extract groups/titles, do not crawl articles.")

    parser.add_argument("--by-group", action="store_true", help="Save outputs/by_group/<group>.json")

    # ✅ category pages add-on
    parser.add_argument("--add-category", action="append", default=[],
                        help='추가로 긁을 분류/문서 타이틀. 예: "분류:리그 오브 레전드/챔피언" (여러 번 가능)')
    parser.add_argument("--category-group-name", type=str, default="챔피언",
                        help="add-category로 추가된 타이틀들을 grouped에 넣을 때 사용할 그룹명(기본: 챔피언)")
    parser.add_argument("--category-container", type=str, default=None,
                        help="add-category에서 링크 추출 범위를 제한할 CSS selector (선택)")

    # speed
    parser.add_argument("--light", action="store_true", help="Skip full_text/sections extraction (faster).")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent workers (threads). (추천 4~8)")
    parser.add_argument("--no-sleep", action="store_true", help="Disable request delay (faster, use carefully).")
    parser.add_argument("--min-delay", type=float, default=MIN_DELAY_SEC)
    parser.add_argument("--max-delay", type=float, default=MAX_DELAY_SEC)

    # expand without extra requests (during crawl)
    parser.add_argument("--expand-during-crawl", action="store_true",
                        help="Collect extra /w/ titles from crawled pages (no extra requests), then crawl them as pass-2.")
    parser.add_argument("--expand-limit", type=int, default=None,
                        help="Max number of extra titles to crawl in pass-2.")
    parser.add_argument("--expand-include-prefix", action="append", default=[],
                        help="Only keep extracted titles that start with this prefix. Can repeat.")
    parser.add_argument("--expand-exclude-prefix", action="append", default=[],
                        help="Drop extracted titles that start with this prefix. Can repeat.")
    parser.add_argument("--expand-container", type=str, default=None,
                        help="CSS selector to restrict link extraction area when expanding.")

    args = parser.parse_args()

    if not args.seed and not args.titles:
        LOGGER.error("Need either --seed or --titles.")
        raise SystemExit(1)

    outputs_dir.mkdir(parents=True, exist_ok=True)

    seed_session = _make_session()

    titles: List[str] = []
    grouped: Dict[str, List[str]] = {}
    title_to_groups: Dict[str, List[str]] = {}

    # 1) Seed -> grouped titles
    if args.seed:
        dbg = debug_dir if args.debug_seed else None
        grouped = collect_grouped_titles_from_seed(
            seed_title=args.seed,
            session=seed_session,
            min_links_in_table=args.min_links,
            debug_dir=dbg,
            min_links_in_row=args.min_links_in_row,
        )
        LOGGER.info("Collected %d groups from seed", len(grouped))

        groups_path, flat_path = save_group_outputs(args.seed, outputs_dir, grouped)
        LOGGER.info("Saved grouped titles: %s", groups_path)
        LOGGER.info("Saved flat titles: %s", flat_path)

        titles.extend(flatten_grouped_titles(grouped))

    # 2) Titles file
    if args.titles:
        file_titles = load_titles(args.titles)
        titles.extend(file_titles)
        LOGGER.info("Collected %d titles from file", len(file_titles))

    # 3) ✅ Add-category pages (e.g., 분류:리그 오브 레전드/챔피언)
    if args.add_category:
        gname = args.category_group_name

        for cat_title in args.add_category:
            try:
                url = build_article_url(cat_title)
                html = fetch_page(seed_session, url)

                # grid 우선
                extra = extract_titles_from_category_grid(html, container_selector=args.category_container)

                # 너무 적으면 일반 링크 추출 fallback
                if len(extra) < 30:
                    extra = extract_titles_from_page(html, container_selector=args.category_container)

                LOGGER.info("add-category %s -> +%d titles", cat_title, len(extra))

                titles.extend(extra)
                grouped.setdefault(gname, []).extend(extra)

            except Exception as e:
                LOGGER.warning("Failed add-category %s: %s", cat_title, e)

    # 4) Dedup preserving order
    seen: Set[str] = set()
    deduped: List[str] = []
    for t in titles:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    titles = deduped

    if not titles:
        LOGGER.warning("No titles collected.")
        raise SystemExit(0)

    # 5) title_to_groups 저장 (seed + add-category까지 반영)
    if grouped:
        title_to_groups = build_title_to_groups(grouped)
        (outputs_dir / "title_to_groups.json").write_text(
            json.dumps(title_to_groups, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # grouped outputs도 최신으로 저장(덮어쓰기)
        if args.seed:
            save_group_outputs(args.seed, outputs_dir, grouped)

    if args.skip_crawl:
        LOGGER.info("skip-crawl enabled. Done.")
        return

    per_article_dir = args.per_article_dir or (outputs_dir / "per-article")
    by_group_dir = (outputs_dir / "by_group") if args.by_group else None

    fetch_page_func: FetchFn = fetch_page
    playwright_fetcher: Optional[PlaywrightFetcher] = None
    if args.use_playwright_fetch:
        headless = not args.playwright_headed
        try:
            playwright_fetcher = PlaywrightFetcher(
                browser_name=args.playwright_browser,
                headless=headless,
                timeout_sec=args.playwright_timeout,
                wait_after_load=args.playwright_wait,
            )
        except RuntimeError as err:
            LOGGER.error("Playwright fetcher 생성 실패: %s", err)
            raise SystemExit(1)
        fetch_page_func = lambda session, target_url: playwright_fetcher.fetch(target_url)

    try:
        # pass-1 crawl
        articles1, extra_titles = crawl_titles(
            titles=titles,
            output_path=args.output,
            per_article=args.per_article,
            per_article_dir=per_article_dir,
            limit=args.limit,
            title_to_groups=title_to_groups if title_to_groups else None,
            by_group_dir=by_group_dir,
            light_mode=args.light,
            workers=max(1, args.workers),
            sleep_enabled=(not args.no_sleep),
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            expand_during_crawl=args.expand_during_crawl,
            expand_include_prefix=args.expand_include_prefix or None,
            expand_exclude_prefix=args.expand_exclude_prefix or None,
            expand_container=args.expand_container,
            fetch_page_func=fetch_page_func,
        )

        # pass-2 crawl (extras)
        if args.expand_during_crawl and extra_titles:
            base_set = set(titles)
            extras = [t for t in extra_titles if t not in base_set]

            if args.expand_limit is not None:
                extras = extras[:args.expand_limit]

            if extras:
                LOGGER.info("Pass-2 crawling %d extra titles (from extracted links)", len(extras))

                output2 = args.output.parent / f"{args.output.stem}_expanded{args.output.suffix}"

                articles2, _ = crawl_titles(
                    titles=extras,
                    output_path=output2,
                    per_article=args.per_article,
                    per_article_dir=per_article_dir,
                    limit=None,
                    title_to_groups=None,
                    by_group_dir=None,
                    light_mode=args.light,
                    workers=max(1, args.workers),
                    sleep_enabled=(not args.no_sleep),
                    min_delay=args.min_delay,
                    max_delay=args.max_delay,
                    expand_during_crawl=False,
                    fetch_page_func=fetch_page_func,
                )

                merged = articles1 + articles2
                merged_out = args.output.parent / f"{args.output.stem}_merged{args.output.suffix}"
                merged_out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
                LOGGER.info("Saved merged output to %s (%d records)", merged_out, len(merged))
    finally:
        if playwright_fetcher is not None:
            playwright_fetcher.close()


if __name__ == "__main__":
    main()
