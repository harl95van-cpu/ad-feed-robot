# -*- coding: utf-8 -*-
"""Catalog crawler for Bitrix-based course listings.

Collects every program from the configured catalog sections: Bitrix element id,
title, url, current and old price, duration and program kind. The element id is
the same id the client's own feed uses, which is what lets us match our data to
the existing offers.
"""
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
MAX_PAGES = 40


def _session():
    s = requests.Session()
    s.headers.update({'User-Agent': UA})
    return s


def norm_url(u, base_url):
    return '/' + u.replace(base_url, '').split('?')[0].strip('/') + '/'


def _prices(chunk):
    """Both listing layouts put prices in the same .course_full_price block.

    Multi-tariff courses print the value as «от 88 400 ₽», so the number is
    pulled out of the div text rather than matched right after the tag."""
    block = re.search(r'course_full_price">(.*?)course_price_desc', chunk, re.S)
    if not block:
        return None, None

    def value(cls):
        m = re.search(r'class="%s">(.*?)</div>' % cls, block.group(1), re.S)
        if not m:
            return None
        digits = re.sub(r'\D', '', m.group(1).split('₽')[0])
        return int(digits) if digits else None

    return value('course_price'), value('course_price_old')


def _parse_dir_item(html, section):
    """Default listing layout: <div class="dir_item" id="bx_<hash>_<id>">."""
    items = []
    for chunk in html.split('<div class="dir_item"')[1:]:
        m = re.search(r'id="bx_\d+_(\d+)"', chunk)
        title = re.search(r'<div class="ttl"><a href="([^"]+)">(.*?)</a>', chunk, re.S)
        if not title or not m:
            continue
        name = re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', title.group(2))).strip()
        cur, old = _prices(chunk)
        items.append(dict(id=m.group(1), url=title.group(1), name=name, price=cur,
                          oldprice=old, section=section,
                          hints=[h.strip() for h in
                                 re.findall(r'class="hint--intensive">([^<]*)<', chunk)]))
    return items


def _parse_bx_elem(html, section):
    """Alternative listing layout: <div id="bx_<hash>_<id>" class="bx_elem"> with an
    <a class="course_title"> link. Listing titles are truncated with an
    ellipsis, so the real name comes from the detail page."""
    items = []
    for chunk in re.split(r'(?=id="bx_\d+_\d+"\s+class="bx_elem")', html)[1:]:
        m = re.match(r'id="bx_\d+_(\d+)"', chunk)
        if not m:
            continue
        link = re.search(r'href="(/[^"]+)"[^>]*class="course_title"[^>]*>(.*?)</a>', chunk, re.S)
        if not link:
            continue
        name = re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', link.group(2))).strip()
        cur, old = _prices(chunk)
        items.append(dict(id=m.group(1), url=link.group(1), name=name, price=cur,
                          oldprice=old, section=section,
                          hints=[h.strip() for h in
                                 re.findall(r'class="hint--intensive">([^<]*)<', chunk)]))
    return items


PROFILES = {'dir_item': _parse_dir_item, 'bx_elem': _parse_bx_elem}


def _parse_listing(html, section, profile='dir_item'):
    return PROFILES[profile](html, section)


def _get(session, url, attempts=4):
    """GET with backoff — the site drops connections when crawled quickly."""
    last = None
    for i in range(attempts):
        try:
            r = session.get(url, timeout=40)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise last


def crawl_section(session, base_url, section, profile='dir_item'):
    """Walk one category section through its PAGEN_2 pagination.

    Sites that put every card on one page simply have no PAGEN links, so the
    loop exits after the first request."""
    found, page = [], 1
    while page <= MAX_PAGES:
        url = base_url + section + ('' if page == 1 else '?PAGEN_2=%d' % page)
        r = _get(session, url)
        items = _parse_listing(r.text, section, profile)
        if not items:
            break
        found += items
        pages = [int(x) for x in re.findall(r'PAGEN_2=(\d+)', r.text)]
        if not pages or page >= max(pages):
            break
        page += 1
    return found


def crawl_catalog(cfg, sections=None):
    """Crawl every configured section, deduplicated by program url.

    `sections` overrides the feed sections — used for catalogue-only parts of
    the site that are published to the database but never advertised.
    """
    session = _session()
    base = cfg['base_url']
    profile = cfg.get('listing_profile', 'dir_item')
    programs = {}
    for section in (cfg['sections'] if sections is None else sections):
        for item in crawl_section(session, base, section, profile):
            key = norm_url(item['url'], base)
            if key in programs:
                programs[key]['sections'].append(section)
            else:
                item['sections'] = [section]
                programs[key] = item
    return programs


def fetch_details(programs, base_url, workers=6):
    """Fetch title / h1 / meta description for every program page.

    The meta description is the client's own copy and is unique per program,
    which is what we use as the offer description.
    """
    session = _session()

    def grab(key):
        try:
            html = _get(session, base_url + key).text
        except requests.RequestException:
            return key, {}
        d = {}
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        d['h1'] = re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', m.group(1))).strip() if m else ''
        m = re.search(r'<title>(.*?)</title>', html, re.S)
        d['title'] = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
        m = re.search(r'<meta name="description" content="([^"]*)"', html)
        d['meta'] = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
        return key, d

    pages = {}
    with ThreadPoolExecutor(workers) as ex:
        for key, data in ex.map(grab, list(programs)):
            pages[key] = data
    return pages
