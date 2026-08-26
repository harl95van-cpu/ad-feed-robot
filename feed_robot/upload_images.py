# -*- coding: utf-8 -*-
"""Bulk-upload generated creatives to Object Storage.

Expects files named <offer_id>.jpg in the source folder. Reports which
programs still have no image of their own.

    venv\\Scripts\\python.exe Scripts\\feeds\\feed_builder\\upload_images.py \\
        --client demo --src "data/creatives"
"""
import os
import re
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage
from main import load_config

ALLOWED = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_BYTES = 5 * 1024 * 1024


def collect(src):
    """Return {offer_id: path} plus a list of files we refuse to upload."""
    good, bad = {}, []
    for name in sorted(os.listdir(src)):
        path = os.path.join(src, name)
        if not os.path.isfile(path):
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() not in ALLOWED:
            bad.append((name, 'неподдерживаемый формат'))
            continue
        if not re.fullmatch(r'\d+|cluster_[a-z0-9_]+', stem):
            bad.append((name, 'имя не равно ID программы или cluster_<ключ>'))
            continue
        if os.path.getsize(path) > MAX_BYTES:
            bad.append((name, 'больше 5 МБ'))
            continue
        good[stem] = path
    return good, bad


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', required=True)
    parser.add_argument('--src', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             '..', '..', '..', 'Credentials.env')))

    cfg = load_config(args.client)
    good, bad = collect(args.src)
    print('готовых картинок: %d' % len(good))
    if bad:
        print('пропущено файлов: %d' % len(bad))
        for name, why in bad[:15]:
            print('   %s — %s' % (name, why))

    if args.dry_run:
        print('dry-run, ничего не загружаем')
        return

    s3 = storage.client()
    prefix = cfg['image_prefix']

    def put(item):
        offer_id, path = item
        key = prefix + offer_id + os.path.splitext(path)[1].lower()
        storage.put_file(s3, cfg['bucket'], key, path)
        return offer_id

    done = 0
    with ThreadPoolExecutor(8) as ex:
        for _ in ex.map(put, good.items()):
            done += 1
            if done % 25 == 0:
                print('   загружено %d/%d' % (done, len(good)))
    print('загружено: %d' % done)

    state = storage.get_json(s3, cfg['bucket'], cfg['state_key'], default={'offers': {}})
    live = {oid for oid, o in state.get('offers', {}).items() if o.get('available') == 'true'}
    uploaded = set(storage.list_images(s3, cfg['bucket'], prefix))
    print('в хранилище: %d персональных, %d по микрокатегориям'
          % (len([k for k in uploaded if k.isdigit()]),
             len([k for k in uploaded if k.startswith('cluster_')])))
    missing = sorted(live - uploaded, key=int)
    print('программ без персональной картинки: %d (возьмут картинку своей микрокатегории)'
          % len(missing))
    print('\nдальше: пересобрать фид, чтобы подставились новые ссылки:')
    print('  venv\\Scripts\\python.exe Scripts\\feeds\\feed_builder\\main.py --client %s'
          % args.client)


if __name__ == '__main__':
    main()
