"""Web search module - search the web using Python stdlib urllib.

Uses DuckDuckGo HTML endpoint (free, no API key needed).
Falls back gracefully if search fails.
"""
import json
import re
import urllib.parse
import urllib.request
import urllib.error
import time

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _make_request(url, data=None, timeout=5):
    """Make an HTTP request with timeout and error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None


def _parse_duckduckgo_results(html):
    """Parse DuckDuckGo HTML search results page."""
    results = []

    # Find all result blocks - DuckDuckGo uses result__body containers
    # Pattern: <h2 class="result__title"> ... <a class="result__a" href="URL">TITLE</a>
    # Snippet: <a class="result__snippet" href="URL">SNIPPET</a>

    result_blocks = re.findall(
        r'<h2[^>]*class="result__title"[^>]*>.*?<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?</h2>',
        html, re.DOTALL
    )

    snippets = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )

    # Also try backup parsing with simpler patterns
    if not result_blocks:
        result_blocks = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )

    for i, (url, title_html) in enumerate(result_blocks):
        # Clean HTML tags from title
        title = re.sub(r'<[^>]+>', '', title_html).strip()
        title = re.sub(r'\s+', ' ', title)

        # Get snippet
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            snippet = re.sub(r'\s+', ' ', snippet)

        if title and url:
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet,
            })

    # If still no results, try a broader pattern
    if not results:
        # Try to extract from result__body divs
        bodies = re.findall(
            r'class="result__body"[^>]*>(.*?)</div>\s*</div>',
            html, re.DOTALL
        )
        for body in bodies:
            url_match = re.search(r'href="(https?://[^"]+)"', body)
            title_match = re.search(r'<a[^>]*>(.*?)</a>', body)
            if url_match and title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                results.append({
                    "title": title,
                    "url": url_match.group(1),
                    "snippet": "",
                })

    return results


def search_duckduckgo(query, max_results=5):
    """Search using DuckDuckGo HTML endpoint. No API key needed."""
    url = "https://html.duckduckgo.com/html/"
    data = urllib.parse.urlencode({"q": query}).encode('utf-8')

    html = _make_request(url, data=data)
    if not html:
        return []

    results = _parse_duckduckgo_results(html)
    return results[:max_results]


def _parse_bing_results(html):
    """Parse Bing search results page."""
    results = []

    # Bing result pattern: <li class="b_algo"> ... <h2><a href="URL">TITLE</a></h2> ... <p>SNIPPET</p>
    algo_blocks = re.findall(
        r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>',
        html, re.DOTALL
    )

    for block in algo_blocks:
        link_match = re.search(r'<a[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        p_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)

        if link_match:
            title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()
            url = link_match.group(1)
            snippet = ""
            if p_match:
                snippet = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
                snippet = re.sub(r'\s+', ' ', snippet)

            if title and url:
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })

    return results


def search_bing(query, max_results=5):
    """Search using Bing. Free, no API key needed."""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&setlang=zh-cn"

    html = _make_request(url)
    if not html:
        return []

    results = _parse_bing_results(html)
    return results[:max_results]


def search_web(query, max_results=5, sources=None):
    """Search the web using available free search endpoints.

    Tries Bing first (better accessibility from China), then DuckDuckGo.
    Returns list of {title, url, snippet} dicts.
    """
    if sources is None:
        sources = ["bing", "duckduckgo"]

    for source in sources:
        if source == "duckduckgo":
            results = search_duckduckgo(query, max_results)
        elif source == "bing":
            results = search_bing(query, max_results)
        else:
            continue

        if results:
            return results

    return []


def fetch_page_content(url, max_chars=2000):
    """Fetch and extract readable text from a URL."""
    html = _make_request(url)
    if not html:
        return ""

    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)

    # Extract text
    text = re.sub(r'<[^>]+>', '\n', html)
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text[:max_chars]


def search_school_info(school_name, country=None, major=None):
    """Search for specific school/program information.

    Constructs targeted queries for university info.
    """
    parts = [school_name]
    if country:
        parts.append(country)
    if major:
        parts.append(major)
    parts.extend(["专业", "课程", "学费"])

    query = " ".join(parts)
    return search_web(query, max_results=5)
