# -*- coding: utf-8 -*-
"""Generate course creatives through OpenRouter's image API.

Reads the program list, skips programs that already have a file, generates the
rest and saves them as <offer_id>.jpg ready for upload_images.py.

    venv\\Scripts\\python.exe Scripts\\feeds\\feed_builder\\generate_images.py \\
        --client demo --limit 2 --model google/gemini-3.1-flash-image

Always run with --limit first: the script reports the real cost per image so
you can decide before spending the whole balance.
"""
import os
import io
import csv
import sys
import time
import json
import base64
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

API_URL = 'https://openrouter.ai/api/v1/images'
CREDITS_URL = 'https://openrouter.ai/api/v1/credits'
SIZE = (1080, 607)
MAX_BYTES = 700 * 1024

STYLE = (
    'Photorealistic editorial photograph, candid documentary style. '
    'Natural daylight, real workplace or classroom interior, shallow depth of field, '
    'warm neutral colour grading, calm professional mood. '
    'Adults aged 25-50 working or studying, natural poses, no posing for camera. '
    'Horizontal 16:9 composition with clear empty space in the upper third. '
    'STRICTLY NO text, no letters, no words, no numbers, no signage, no logos, '
    'no watermarks, no diplomas or certificates in frame, no national symbols or flags.'
)


def build_prompt(row):
    """One scene per program: the topic in Russian plus a fixed style block."""
    topic = row['name']
    for junk in ('Обучение: ', 'Дистанционное обучение: ', '. Диплом!',
                 '. Курс повышения квалификации', '. Документ о квалификации'):
        topic = topic.replace(junk, '')
    topic = topic.split(' (')[0].strip(' .')
    return ('Scene illustrating the professional field: "%s". '
            'Show the real working environment and tools of this profession. %s'
            % (topic, STYLE))


def build_cluster_prompt(scene):
    """One scene per micro-category — reused by every program in the cluster."""
    return '%s. %s' % (scene.strip().rstrip('.'), STYLE)


def credits(api_key):
    r = requests.get(CREDITS_URL, headers={'Authorization': 'Bearer %s' % api_key}, timeout=30)
    d = r.json()['data']
    return d['total_credits'] - d['total_usage']


def to_jpeg(raw):
    """Normalise whatever the model returns into a feed-ready JPEG."""
    img = Image.open(io.BytesIO(raw)).convert('RGB')
    img = img.resize(SIZE, Image.LANCZOS)
    for quality in (90, 85, 80, 75, 70):
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=quality, optimize=True, progressive=True)
        if buf.tell() <= MAX_BYTES:
            return buf.getvalue()
    return buf.getvalue()


def generate_one(api_key, model, row, out_dir, attempts=3):
    """row: {'id': file stem, 'prompt': ready prompt} or a program CSV row."""
    offer_id = row['id']
    prompt = row.get('prompt') or build_prompt(row)
    payload = {'model': model, 'prompt': prompt,
               'aspect_ratio': '16:9', 'resolution': '1K'}
    headers = {'Authorization': 'Bearer %s' % api_key,
               'Content-Type': 'application/json',
               'X-Title': 'feed-creatives'}
    for attempt in range(attempts):
        try:
            r = requests.post(API_URL, headers=headers,
                              data=json.dumps(payload).encode('utf-8'), timeout=180)
            if r.status_code != 200:
                if r.status_code in (402, 403):
                    return offer_id, 'нет средств или доступа: %s' % r.text[:160], 0.0
                raise RuntimeError('HTTP %s %s' % (r.status_code, r.text[:200]))
            body = r.json()
            data = body.get('data') or []
            if not data:
                raise RuntimeError('пустой ответ: %s' % json.dumps(body)[:200])
            raw = base64.b64decode(data[0]['b64_json'])
            path = os.path.join(out_dir, '%s.jpg' % offer_id)
            with open(path, 'wb') as f:
                f.write(to_jpeg(raw))
            # The credits endpoint lags behind, so bill from the response itself.
            return offer_id, None, float(body.get('usage', {}).get('cost') or 0)
        except Exception as exc:
            if attempt == attempts - 1:
                return offer_id, str(exc)[:200], 0.0
            time.sleep(3 * (attempt + 1))


def load_rows(csv_path):
    with open(csv_path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f, delimiter=';'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', default='demo')
    parser.add_argument('--csv', default=r'data\programs.csv')
    parser.add_argument('--out', default=r'data\creatives')
    parser.add_argument('--model', default='google/gemini-3.1-flash-image')
    parser.add_argument('--limit', type=int, help='generate at most N images')
    parser.add_argument('--ids', help='comma-separated offer ids to (re)generate')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--clusters', action='store_true',
                        help='generate one image per micro-category instead of per program')
    parser.add_argument('--dry-run', action='store_true', help='only print prompts')
    args = parser.parse_args()

    from dotenv import load_dotenv
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    load_dotenv(os.path.join(root, 'Credentials.env'))
    api_key = os.environ['OPENROUTER_API_KEY']

    out_dir = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
    csv_path = args.csv if os.path.isabs(args.csv) else os.path.join(root, args.csv)
    os.makedirs(out_dir, exist_ok=True)

    have = {os.path.splitext(n)[0] for n in os.listdir(out_dir)}

    if args.clusters:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import clusters as clusters_mod
        rows = [{'id': 'cluster_%s' % key,
                 'name': title,
                 'prompt': build_cluster_prompt(scene)}
                for key, (title, scene) in sorted(clusters_mod.catalog().items())]
    else:
        rows = load_rows(csv_path)

    if args.ids:
        wanted = {i.strip() for i in args.ids.split(',')}
        todo = [r for r in rows if r['id'] in wanted or r['id'].replace('cluster_', '') in wanted]
    else:
        todo = [r for r in rows if r['id'] not in have]
    if args.limit:
        todo = todo[:args.limit]

    print('всего позиций: %d | уже есть картинок: %d | к генерации: %d'
          % (len(rows), len(have), len(todo)))
    print('модель: %s' % args.model)

    if args.dry_run:
        for r in todo[:5]:
            print('\n--- %s | %s\n%s' % (r['id'], r['name'], r.get('prompt') or build_prompt(r)))
        return

    if not todo:
        print('нечего генерировать')
        return

    balance = credits(api_key)
    print('баланс на счету: $%.2f' % balance)

    ok, failed, spent = [], [], 0.0
    started = time.time()
    with ThreadPoolExecutor(args.workers) as ex:
        for offer_id, err, cost in ex.map(
                lambda r: generate_one(api_key, args.model, r, out_dir), todo):
            spent += cost
            if err:
                failed.append((offer_id, err))
                print('  [x] %s — %s' % (offer_id, err))
            else:
                ok.append(offer_id)
                if len(ok) % 10 == 0:
                    print('  готово %d/%d, потрачено $%.2f' % (len(ok), len(todo), spent))

    print('\nсгенерировано: %d | ошибок: %d | время: %.0f с'
          % (len(ok), len(failed), time.time() - started))
    print('потрачено: $%.4f | осталось примерно: $%.2f' % (spent, balance - spent))
    if ok:
        per = spent / len(ok)
        left = len([r for r in rows if r['id'] not in have]) - len(ok)
        print('цена за картинку: $%.4f' % per)
        if left > 0 and per:
            print('на оставшиеся %d нужно ещё $%.2f (текущего баланса хватит на %d штук)'
                  % (left, per * left, int((balance - spent) / per)))
    for offer_id, err in failed[:10]:
        print('  ошибка %s: %s' % (offer_id, err))


if __name__ == '__main__':
    main()
