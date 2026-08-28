# -*- coding: utf-8 -*-
"""Collect a reference set of live programs to evaluate prompts against.

Crawls the listings of every configured section, samples across all of them so
the awkward cases are represented, and fetches the detail pages only for the
sample. Costs nothing: no model is called here.

The result is the fixed input for eval_texts.py, so it is written once and
reused — comparing two prompt versions on two different samples would tell us
nothing.

    venv/Scripts/python.exe Scripts/feeds/feed_builder/eval/build_reference.py \
        --client demo --size 25
"""
import os
import sys
import json
import random
import argparse
from collections import defaultdict

BUILDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BUILDER)

import crawler  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, 'reference_set.json')


def load_config(client):
    with open(os.path.join(BUILDER, 'clients_config.json'), encoding='utf-8') as f:
        return json.load(f)[client]


def spread(programs, size, seed=7):
    """Take the sample evenly across sections rather than off the top.

    Catalogue order groups similar programmes together, so a head slice would
    be a dozen variations on one profession and would hide exactly the cases
    the prompt struggles with.
    """
    by_section = defaultdict(list)
    for key, program in programs.items():
        by_section[program['sections'][0]].append(key)
    rng = random.Random(seed)
    for keys in by_section.values():
        rng.shuffle(keys)

    picked, sections = [], sorted(by_section)
    while len(picked) < size and any(by_section[s] for s in sections):
        for section in sections:
            if by_section[section] and len(picked) < size:
                picked.append(by_section[section].pop())
    return picked


def collect(client, size):
    cfg = load_config(client)
    programs = crawler.crawl_catalog(cfg)
    print('  %s: в каталоге %d программ' % (client, len(programs)))
    keys = spread(programs, size)
    sample = {k: programs[k] for k in keys}
    pages = crawler.fetch_details(sample, cfg['base_url'])

    rows = []
    for key in keys:
        p, page = sample[key], pages.get(key, {})
        if not p.get('price'):
            continue
        rows.append(dict(client=client, id=p['id'], url=key, listing_name=p['name'],
                         price=p['price'], oldprice=p['oldprice'], hints=p['hints'],
                         title=page.get('title', ''), h1=page.get('h1', ''),
                         meta=page.get('meta', ''),
                         # Facts like the duration live only here.
                         body=page.get('body', ''),
                         # Filled in by hand for the variants we consider right;
                         # the evaluation reports agreement where it is present.
                         gold_title=''))
    print('  %s: в набор попало %d' % (client, len(rows)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--client', action='append', required=True,
                    help='repeatable: --client demo --client second')
    ap.add_argument('--size', type=int, default=25, help='programs per client')
    ap.add_argument('--out', default=DEFAULT_PATH)
    args = ap.parse_args()

    rows = []
    for client in args.client:
        rows += collect(client, args.size)

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print('эталонный набор: %d программ -> %s' % (len(rows), args.out))


if __name__ == '__main__':
    main()
