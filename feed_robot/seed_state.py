# -*- coding: utf-8 -*-
"""Seed the robot's state file from an existing YML feed.

Run once per client when onboarding: it carries the fields we cannot derive
from the site (pictures, custom_score, custom_label_*, sales_notes) into the
state the weekly job reads.

    venv\\Scripts\\python.exe Scripts\\feeds\\feed_builder\\seed_state.py \\
        --client demo --feed path\\to\\feed.yml
"""
import os
import sys
import argparse
import datetime
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage
from main import load_config


def _int(value):
    return int(value) if value else None


def text(node, tag):
    el = node.find(tag)
    return (el.text or '').strip() if el is not None else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', required=True)
    parser.add_argument('--feed', required=True, help='path to the existing YML feed')
    parser.add_argument('--only', help='file with urls to keep, one per line')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    import llm
    llm.load_environment()

    cfg = load_config(args.client)
    keep = None
    if args.only:
        with open(args.only, encoding='utf-8') as f:
            keep = {('/' + l.strip().split('://')[-1].split('/', 1)[-1].strip('/') + '/')
                    for l in f if l.strip()}
        print('оставляем только перечисленные url: %d' % len(keep))

    def url_key(u):
        return '/' + (u or '').split('://')[-1].split('/', 1)[-1].strip('/') + '/'

    shop = ET.parse(args.feed).getroot().find('shop')
    offers = {}
    for o in shop.find('offers'):
        if keep is not None and url_key(text(o, 'url')) not in keep:
            continue
        offers[o.get('id')] = {
            'name': text(o, 'name'),
            'description': text(o, 'description'),
            'categoryId': text(o, 'categoryId'),
            'url': text(o, 'url'),
            'picture': text(o, 'picture'),
            'price': _int(text(o, 'price')),
            # Not every catalogue runs a standing discount, so a feed without
            # crossed-out prices is normal and must not break the seeding.
            'oldprice': _int(text(o, 'oldprice')),
            'available': o.get('available'),
            'custom_label_0': text(o, 'custom_label_0') or 'False',
            'custom_label_1': text(o, 'custom_label_1') or 'False',
            'custom_label_2': text(o, 'custom_label_2') or 'False',
            'custom_score': text(o, 'custom_score'),
            'sales_notes': text(o, 'sales_notes'),
            'gone_cycles': 0,
        }

    state = {'updated_at': datetime.date.today().isoformat(), 'offers': offers}
    print('офферов в состоянии: %d' % len(offers))
    print('с картинками: %d' % sum(1 for v in offers.values() if v['picture']))
    print('с custom_score: %d' % sum(1 for v in offers.values() if v['custom_score']))

    if args.dry_run:
        print('dry-run, в облако не пишем')
        return

    s3 = storage.client()
    storage.put_json(s3, cfg['bucket'], cfg['state_key'], state)
    print('записано: %s' % storage.public_url(cfg['bucket'], cfg['state_key']))


if __name__ == '__main__':
    main()
