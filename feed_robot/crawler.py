# -*- coding: utf-8 -*-
"""Catalog crawler for demo-academy.example-style Bitrix course listings.

Collects every program from the configured catalog sections: Bitrix element id,
title, url, current and old price, duration and program kind. The element id is
the same id the client's own feed uses, which is what lets us match our data to
the existing offers.
"""
import re
import json
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
    """demo-academy.example layout: <div class="dir_item" id="bx_<hash>_<id>">."""
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
    """second-academy.example layout: <div id="bx_<hash>_<id>" class="bx_elem"> with an
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


# --- Tilda store ----------------------------------------------------------
#
# A Tilda catalogue ships no cards. The section page contains empty skeletons
# and the products arrive in the browser from the store API, so a parser over
# that markup finds nothing at all -- which the minimum-offers guard would then
# report as «сайт лежит». This profile reads the same API the page reads.
#
# The two ids the API needs are printed into the page's own init call, so they
# are discovered per section instead of being written into the config: a
# section rebuilt in Tilda gets new ids, and a config holding the old ones
# would crawl an empty catalogue every morning.
TILDA_STORE_API = 'https://store.tildacdn.com/api/getproductslist/'
TILDA_OPTIONS = re.compile(r"recid:'(\d+)',storepart:'(\d+)'")
TILDA_SLICE = 500


def _int_or_none(value):
    """Tilda writes a price as «20000.0000» and an absent price as «»."""
    digits = re.sub(r'\D', '', str(value or '').split('.')[0])
    return int(digits) if digits else None


def _first_picture(gallery):
    """First image of the product gallery, which Tilda stores as JSON text."""
    try:
        items = json.loads(gallery or '[]')
    except ValueError:
        return ''
    return (items[0].get('img') or '') if items else ''


def _path_of(url, base_url):
    return '/' + (url or '').replace(base_url, '').split('?')[0].strip('/')


def crawl_tilda_store(session, base_url, section):
    """Every product of one Tilda store section, through the store API."""
    html = _get(session, base_url + section).text
    found = TILDA_OPTIONS.search(html)
    if not found:
        raise RuntimeError('раздел %s: не нашли recid/storepart магазина Tilda' % section)
    recid, part = found.group(1), found.group(2)
    items, page = [], 1
    while page <= MAX_PAGES:
        url = ('%s?storepartuid=%s&recid=%s&c=1&getparts=true&getoptions=true'
               '&slice=%d&size=%d' % (TILDA_STORE_API, part, recid, page, TILDA_SLICE))
        data = _get(session, url).json()
        products = data.get('products') or []
        for p in products:
            items.append(dict(
                id=str(p.get('uid')),
                url=_path_of(p.get('url'), base_url),
                name=re.sub(r'\s+', ' ', p.get('title') or '').strip(),
                price=_int_or_none(p.get('price')),
                oldprice=_int_or_none(p.get('priceold')),
                section=section,
                picture=_first_picture(p.get('gallery')),
                # The store keeps the duration and the speciality as labelled
                # characteristics; handed over as hints they are reachable by
                # the client's extraction rules like any other source.
                hints=['%s: %s' % (c.get('title', ''), c.get('value', ''))
                       for c in (p.get('characteristics') or [])],
            ))
        if not products or len(items) >= int(data.get('total') or 0):
            break
        page += 1
    return items


# Profiles that fetch their own listing instead of parsing the section page.
SECTION_PROFILES = {'tilda_store': crawl_tilda_store}


# --- Landing pages --------------------------------------------------------
#
# third-academy.example keeps two parallel catalogues: the store, which holds the prices
# and the pictures, and a set of hand-built SEO pages, which is where the ads
# have always pointed. Neither side links to the other, so the two are joined by
# the programme name -- first on the url slug, then on the slug with the
# transliteration flattened («psihiatriya» and «psikhiatriya» are the same word
# spelled by two different tools), and only then on the heading of the few pages
# still unclaimed, which is the one stage that costs requests.
#
# A programme that cannot be joined keeps its store url and is reported. An ugly
# landing page is recoverable; ads pointing at another programme's page are not,
# so every stage takes a candidate only when exactly one of them is left.
MIN_SKELETON = 10
_VOWELS = re.compile(r'[aeiouy]')
_NAME_STOP = {'и', 'с', 'в', 'по', 'для', 'на', 'от', 'к', 'о', 'об', 'при', 'у', 'за', 'из', 'а'}


def _slug(path):
    return path.rstrip('/').rsplit('/', 1)[-1].strip('-').lower()


def _store_slug(path):
    """A product url is /<section>/tproduct/<recid>-<uid>-<slug>."""
    slug = _slug(path)
    m = re.match(r'^\d+-\d+-(.+)$', slug)
    return (m.group(1) if m else slug).strip('-')


def _skeleton(slug):
    """What is left of a slug once the transliteration choices are gone."""
    s = slug.lower().replace('kh', 'h').replace('ye', 'e').replace('yi', 'i').replace('iy', 'i')
    s = re.sub(r'[^a-z0-9]+', '', s)
    return re.sub(r'(.)\1+', r'\1', _VOWELS.sub('', s))


def _name_key(text):
    """A programme name reduced to its significant words.

    The store calls it «Анестезиология и реаниматология» and the page heading
    «Анестезиология - реаниматология: профессиональная переподготовка»; what
    survives here is the same string in both.
    """
    text = (text or '').lower().replace('ё', 'е').split(':')[0]
    text = re.sub(r'\(\d+\)', ' ', text)
    text = re.sub(r'[^а-я0-9]+', ' ', text)
    return ' '.join(w for w in text.split() if w not in _NAME_STOP)


def sitemap_paths(session, base_url):
    xml = _get(session, base_url + '/sitemap.xml').text
    return [_path_of(u, base_url) for u in re.findall(r'<loc>([^<]+)</loc>', xml)]


def _headings(session, base_url, paths, workers=6):
    def grab(path):
        try:
            return path, parse_details(_get(session, base_url + path).text).get('h1', '')
        except requests.RequestException:
            return path, ''
    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(grab, paths))


def resolve_landings(items, base_url, session, overrides=None):
    """Repoint every product at its SEO landing page where one exists."""
    overrides = overrides or {}
    sections = sorted(set(it['section'] for it in items), key=len, reverse=True)
    pool = dict((section, []) for section in sections)
    for path in sitemap_paths(session, base_url):
        for section in sections:
            if path.startswith(section) and path.rstrip('/') != section.rstrip('/'):
                pool[section].append(path)
                break

    taken, resolved = set(), {}

    def claim(item_id, path):
        resolved[item_id] = path
        taken.add(path)

    for it in items:
        if overrides.get(it['id']):
            claim(it['id'], overrides[it['id']])

    def candidates(stage, it):
        free = [p for p in pool.get(it['section'], []) if p not in taken]
        want = _store_slug(it['url'])
        if stage == 'slug':
            return [p for p in free if _slug(p) == want]
        if stage == 'skeleton':
            return [p for p in free if _skeleton(_slug(p)) == _skeleton(want)]
        # A slug Tilda cut short -- «...-i-obsches» -- against the full one.
        key = _skeleton(want)
        if len(key) < MIN_SKELETON:
            return []
        out = []
        for p in free:
            other = _skeleton(_slug(p))
            if other.startswith(key) or (len(other) >= MIN_SKELETON and key.startswith(other)):
                out.append(p)
        return out

    for stage in ('slug', 'skeleton', 'prefix'):
        for it in items:
            if it['id'] in resolved:
                continue
            found = candidates(stage, it)
            if len(found) == 1:
                claim(it['id'], found[0])

    left = [it for it in items if it['id'] not in resolved]
    if left:
        free = [p for section in sections for p in pool[section] if p not in taken]
        headings = _headings(session, base_url, free)
        for it in left:
            found = [p for p in free if p not in taken and p.startswith(it['section'])
                     and _name_key(headings.get(p, '')) == _name_key(it['name'])]
            if len(found) == 1:
                claim(it['id'], found[0])

    for it in items:
        if it['id'] in resolved:
            it['url'] = resolved[it['id']]
        else:
            it['landing_missing'] = True
    return items


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
    loop exits after the first request. A profile that fetches its own listing
    -- a catalogue rendered in the browser -- is dispatched before any of this.
    """
    if profile in SECTION_PROFILES:
        return SECTION_PROFILES[profile](session, base_url, section)
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
    items = []
    for section in (cfg['sections'] if sections is None else sections):
        items += crawl_section(session, base, section, profile)
    # Resolved over the whole catalogue rather than per section: a programme is
    # joined to a landing page only when it is the one candidate left, and the
    # sections draw from a single pool of pages.
    if cfg.get('landing_pages') == 'sitemap':
        resolve_landings(items, base, session, cfg.get('landing_overrides'))
    # Pages that exist only as landings. third-academy.example advertises whole directions
    # -- pedagogy, nutrition, cosmetology -- that were never put into the store,
    # so the catalogue crawl cannot see them at all. They are declared in the
    # config and joined here, after the landing resolution, so that nothing
    # repoints them: their url already is the page the ad points at.
    for extra in (cfg.get('extra_programs') or []):
        items.append(dict(
            id=str(extra['id']),
            url=extra['path'],
            name=extra.get('name', ''),
            # A fallback only: build_offers runs the client's price rules over
            # the fetched page first, and the page wins wherever it states one.
            price=extra.get('price'),
            oldprice=extra.get('oldprice'),
            section=extra.get('section', 'extra'),
            picture=extra.get('picture'),
            categoryId=extra.get('categoryId'),
            hints=list(extra.get('hints') or []),
        ))
    # Pages the client does not advertise: a programme sold only as a store card
    # with no landing of its own, or a specialty the catalogue duplicates under a
    # second url. Matched on the resolved url, so a card repointed at its landing
    # is judged by the page the ad would actually open.
    drop = cfg.get('exclude_paths') or []
    if drop:
        items = [it for it in items
                 if not any(frag in it['url'] for frag in drop)]
    programs = {}
    for item in items:
        key = norm_url(item['url'], base)
        if key in programs:
            programs[key]['sections'].append(item['section'])
        else:
            item['sections'] = [item['section']]
            programs[key] = item
    return programs


# The page body is kept as plain text so extraction rules can reach the facts
# that live neither in the title nor in the meta description — the duration on
# both of our sites sits in a spec line halfway down the page. Capped because a
# rule that has not found its fact in the first sixty thousand characters is not
# going to find it further down, and every page is held in memory at once.
BODY_LIMIT = 60000

_TAGS = re.compile(r'<[^>]+>')
_SCRIPTS = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)


def parse_details(html):
    """Pull the page's facts out of its HTML.

    Split out from the fetching so the same HTML can be re-parsed offline — a
    change to these rules can then be compared against the old ones on
    byte-identical input instead of on two crawls of a moving site.
    """
    d = {}
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    d['h1'] = re.sub(r'\s+', ' ', _TAGS.sub('', m.group(1))).strip() if m else ''
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    d['title'] = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    m = re.search(r'<meta name="description" content="([^"]*)"', html)
    d['meta'] = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    text = _TAGS.sub(' ', _SCRIPTS.sub(' ', html))
    d['body'] = re.sub(r'\s+', ' ', text).strip()[:BODY_LIMIT]
    return d


def fetch_details(programs, base_url, workers=6):
    """Fetch and parse every program page."""
    session = _session()

    def grab(key):
        try:
            html = _get(session, base_url + key).text
        except requests.RequestException:
            return key, {}
        return key, parse_details(html)

    pages = {}
    with ThreadPoolExecutor(workers) as ex:
        for key, data in ex.map(grab, list(programs)):
            pages[key] = data
    return pages
