# -*- coding: utf-8 -*-
"""Telegram reporting for the weekly feed run."""
import os
import html
import requests

API = 'https://api.telegram.org/bot%s/sendMessage'
LIMIT = 4000


def _credentials():
    token = os.environ.get('TELEGRAM_BOT_TOKEN_FEEDS')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID_FEEDS')
    return token, chat_id


def _send_via_relay(text):
    """api.telegram.org is unreachable from Yandex Cloud, so the weekly job
    posts through a small Vercel relay instead."""
    url = os.environ.get('RELAY_URL')
    secret = os.environ.get('RELAY_SECRET')
    if not url or not secret:
        return None
    r = requests.post(url, json={'text': text},
                      headers={'x-relay-secret': secret}, timeout=30)
    if not r.ok:
        print('[notify] relay error %s: %s' % (r.status_code, r.text[:300]))
        return False
    return True


def _send_direct(text):
    token, chat_id = _credentials()
    if not token or not chat_id:
        print('[notify] telegram credentials missing, skipping')
        return False
    for chunk in [text[i:i + LIMIT] for i in range(0, len(text), LIMIT)] or ['']:
        r = requests.post(API % token,
                          json={'chat_id': chat_id, 'text': chunk,
                                'parse_mode': 'HTML', 'disable_web_page_preview': True},
                          timeout=20)
        if not r.ok:
            print('[notify] telegram error: %s' % r.text[:300])
            return False
    return True


def send(text):
    """Best-effort delivery: relay first, direct Telegram as a fallback.

    Never raises — the feed is already published by the time we report, so a
    broken notification channel must not fail the run.
    """
    try:
        via_relay = _send_via_relay(text)
        if via_relay:
            return True
    except Exception as exc:
        print('[notify] relay unreachable: %s' % str(exc)[:200])
    try:
        return _send_direct(text)
    except Exception as exc:
        print('[notify] telegram unreachable: %s' % str(exc)[:200])
        return False


def _money(n):
    return '{:,}'.format(int(n)).replace(',', ' ')


def format_report(client, diff, feed_url, problems, no_image):
    e = html.escape
    lines = ['<b>Фид %s обновлён</b>' % e(client),
             'Офферов в фиде: %d' % diff['total'],
             feed_url, '']

    if diff['price_changes']:
        lines.append('<b>Изменились цены: %d</b>' % len(diff['price_changes']))
        for c in diff['price_changes'][:15]:
            arrow = '↑' if c['new'] > c['old'] else '↓'
            lines.append('%s %s: %s → %s ₽ — %s'
                         % (arrow, e(c['id']), _money(c['old']), _money(c['new']), e(c['name'][:50])))
        if len(diff['price_changes']) > 15:
            lines.append('…и ещё %d' % (len(diff['price_changes']) - 15))
        lines.append('')

    if diff['added']:
        lines.append('<b>Новые программы: %d</b>' % len(diff['added']))
        for a in diff['added'][:15]:
            lines.append('+ %s — %s ₽ — %s' % (e(a['id']), _money(a['price']), e(a['name'][:50])))
        if len(diff['added']) > 15:
            lines.append('…и ещё %d' % (len(diff['added']) - 15))
        lines.append('')

    if diff['removed']:
        lines.append('<b>Пропали с сайта: %d</b> (помечены available=false)' % len(diff['removed']))
        for r in diff['removed'][:15]:
            lines.append('− %s — %s' % (e(r['id']), e(r['name'][:60])))
        if len(diff['removed']) > 15:
            lines.append('…и ещё %d' % (len(diff['removed']) - 15))
        lines.append('')

    if not (diff['price_changes'] or diff['added'] or diff['removed']):
        lines.append('Изменений на сайте нет.')
        lines.append('')

    if no_image:
        lines.append('Без своей картинки: %d офферов (стоят заглушки)' % no_image)

    if problems:
        lines.append('')
        lines.append('<b>Проблемы валидации: %d</b>' % len(problems))
        for p in problems[:10]:
            lines.append('• %s' % e(p))

    return '\n'.join(lines)


def format_alert(client, reason):
    return ('<b>Фид %s НЕ обновлён</b>\n\n%s\n\nСтарый фид оставлен без изменений.'
            % (html.escape(client), html.escape(reason)))
