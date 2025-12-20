import time
import random
import pandas as pd
import os
from playwright.sync_api import sync_playwright

class PlaywrightFetcher:
    def __init__(self, headless=True):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()

    def get_page_content(self, url, wait_selector=None):
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if wait_selector:
                try:
                    self.page.wait_for_selector(wait_selector, timeout=10000)
                except:
                    print(f"Timeout waiting for selector: {wait_selector}")
            
            # Scroll to trigger lazy loading
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight/4)")
            time.sleep(1)
            
            return self.page
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def close(self):
        self.context.close()
        self.browser.close()
        self.playwright.stop()

def get_post_links(fetcher, page=1):
    url = f"https://talk.op.gg/s/lol/tip?sort=popular&page={page}"
    print(f"Navigating to {url}...")
    
    # Wait for the article list
    page = fetcher.get_page_content(url, wait_selector="article")
    
    if not page:
        return []
        
    # DEBUG
    try:
        page.screenshot(path="crawler/outputs/debug_list.png")
        with open("crawler/outputs/debug_list.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("Debug screenshot and HTML saved to crawler/outputs/")
    except Exception as e:
        print(f"Failed to save debug info: {e}")

    links = []
    try:
        # Wait for any post link to appear
        page.wait_for_selector("a[href*='/s/lol/tip/']", timeout=10000)
        
        # Select all anchors that look like post links
        anchors = page.query_selector_all("a[href*='/s/lol/tip/']")
        
        for a in anchors:
            href = a.get_attribute("href")
            # Ensure it's a post link (usually has an ID) and not just the board link
            if href and "/s/lol/tip/" in href:
                # Exclude pagination or writing links if they follow this pattern (usually they don't)
                parts = href.split("/")
                # Check if it has an ID part (digits)
                has_id = False
                for part in parts:
                    if part.isdigit():
                        has_id = True
                        break
                
                if has_id:
                    full_url = "https://talk.op.gg" + href
                    if full_url not in links:
                        links.append(full_url)
                        
    except Exception as e:
        print(f"Error finding links: {e}")

    # Deduplicate while preserving order
    return list(dict.fromkeys(links))

def parse_post_details(fetcher, url):
    try:
        # Random sleep to behave human-like
        time.sleep(random.uniform(0.5, 1.5))
        
        page = fetcher.get_page_content(url, wait_selector="article")
        if not page:
            return None
            
        data = {
            "url": url,
            "title": None,
            "nickname": None,
            "date": None,
            "content": "",
            "comments": []
        }

        # Title
        try:
            title_elem = page.query_selector("h1")
            if title_elem:
                data["title"] = title_elem.inner_text().strip()
        except:
            pass

        # Nickname & Date
        try:
            nick_elem = page.query_selector(".article-meta__author .nickname")
            if not nick_elem:
                 nick_elem = page.query_selector(".user-name")
            
            if nick_elem:
                data["nickname"] = nick_elem.inner_text().strip()
                
                # Attempt to find absolute date from tooltip
                # The date wrapper is the previous sibling
                try:
                    date_wrapper_handle = nick_elem.evaluate_handle("el => el.previousElementSibling")
                    
                    # Hover to trigger tooltip
                    date_wrapper_handle.hover()
                    time.sleep(0.5)  # Wait for tooltip to appear
                    
                    # Look for react-tooltip-lite
                    tooltip = page.query_selector(".react-tooltip-lite")
                    if tooltip:
                        absolute_date = tooltip.inner_text().strip()
                        if absolute_date and '202' in absolute_date:  # Sanity check for year
                            data["date"] = absolute_date
                        else:
                            # Fallback to relative date
                            relative_date = date_wrapper_handle.evaluate("el => el.innerText")
                            data["date"] = relative_date.strip() if relative_date else None
                    else:
                        # No tooltip found, use relative date
                        relative_date = date_wrapper_handle.evaluate("el => el.innerText")
                        data["date"] = relative_date.strip() if relative_date else None
                except Exception as e:
                    print(f"Error extracting date with tooltip: {e}")
                    pass
            
            # Fallback/Old selector
            if not data["date"]:
                date_elem = page.query_selector(".article-meta__item--date")
                if date_elem:
                    data["date"] = date_elem.get_attribute("title") or date_elem.inner_text().strip()
        except:
            pass
        
        # Content (Body Text)
        try:
            # Fixed selector: article.toastui-editor-contents (no space)
            content_area = page.query_selector("article.toastui-editor-contents")
            if content_area:
                paragraphs = content_area.query_selector_all("p")
                data["content"] = "\n".join([p.inner_text().strip() for p in paragraphs if p.inner_text().strip()])
        except Exception as e:
            print(f"Error parsing content: {e}")

        # Comments
        try:
            # Scroll down multiple times to ensure comments section loads
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
            
            # Wait longer for comment container to appear
            try:
                page.wait_for_selector(".comment-contents", timeout=10000)
            except:
                pass  # Comments may not exist for all posts
            
            # Load all comments if "Load More" button exists
            while True:
                # Use text matching for button
                load_more_btn = page.query_selector("button:has-text('댓글 더보기')")
                
                if load_more_btn and load_more_btn.is_visible():
                    try:
                        load_more_btn.click()
                        time.sleep(1) # Wait for load
                    except:
                        break
                else:
                    break

            # Extract comments
            comments_div = page.query_selector(".comment-contents")
            
            if comments_div:
                comment_items = comments_div.query_selector_all("li")
                
                comments_list = []
                for item in comment_items:
                    c_data = {"nickname": None, "content": None, "date": None}
                    try:
                        # Nickname: .user-name > a > span > b
                        user_name_span = item.query_selector(".user-name")
                        if user_name_span:
                            nick_b = user_name_span.query_selector("b")
                            if nick_b:
                                c_data["nickname"] = nick_b.inner_text().strip()
                        
                        # Content: p tag
                        c_content = item.query_selector("p")
                        if c_content:
                            c_data["content"] = c_content.inner_text().strip()
                        
                        # Date: sibling span after .user-name (relative time)
                        if user_name_span:
                            try:
                                date_text = user_name_span.evaluate("el => el.nextElementSibling ? el.nextElementSibling.innerText : ''")
                                if date_text:
                                    c_data["date"] = date_text.strip()
                            except:
                                pass
                        
                        # Filtering: Exclude system buttons/labels and empty content
                        invalid_nicknames = ["신고", "답글 쓰기"]
                        if (c_data["nickname"] and c_data["nickname"] not in invalid_nicknames) and c_data["content"]:
                             comments_list.append(c_data)
                    except:
                        continue
                
                data["comments"] = comments_list
            
        except Exception as e:
            print(f"Error parsing comments: {e}")

        return data

    except Exception as e:
        print(f"Failed to parse {url}: {e}")
        return None

def crawl_opgg_tips(max_posts=20, headless=True):
    fetcher = PlaywrightFetcher(headless=headless)
    all_data = []
    import json
    from tqdm import tqdm
    
    try:
        pbar = tqdm(total=max_posts, desc="Collecting posts", unit="post")
        page_num = 1
        while len(all_data) < max_posts:
            # tqdm.write(f"Fetching post links from page {page_num}...") 
            # Commented out to reduce noise with progress bar
            links = get_post_links(fetcher, page=page_num)
            
            if not links:
                tqdm.write("No more links found.")
                break
                
            # tqdm.write(f"Collected {len(links)} links from page {page_num}.")
            
            for i, link in enumerate(links):
                # Check if we already have this URL
                if any(d['url'] == link for d in all_data):
                    continue

                # details = parse_post_details(fetcher, link) 
                # Converting print in parse_post_details to not interfere is hard without passing pbar, 
                # so we rely on stdout interception or just accept some interference.
                # Ideally we silence parse_post_details or change it to use logging.
                # For now let's just run it.
                
                details = parse_post_details(fetcher, link)
                if details:
                    all_data.append(details)
                    pbar.update(1)
                
                # Limit check
                if len(all_data) >= max_posts: 
                    break
            
            page_num += 1
        
        pbar.close()

    finally:
        fetcher.close()
        
    # Save results as JSON
    if all_data:
        # Save relative to the script location or current working directory
        # The script will be moved to data/crawler/opgg/opgg_crawler.py
        # Outputs should be in data/crawler/opgg/outputs/
        
        # Determine base directory based on script location
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "outputs")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "opgg_tips.json")
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
            
        print(f"Saved {len(all_data)} items to {output_path}")
    else:
        print("No data collected.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OPGG Talk Tip Crawler")
    parser.add_argument("--limit", type=int, default=20, help="Number of posts to crawl (default: 20)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode (default: True)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run in visible browser mode")
    
    args = parser.parse_args()
    
    crawl_opgg_tips(max_posts=args.limit, headless=args.headless)

