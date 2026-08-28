# -*- coding: utf-8 -*-
"""OpenRouter client for the text generator.

Separate from generate_images.py on purpose: that one talks to the images
endpoint, returns base64 and has no spending limit because it is run by hand
with --limit. This one runs unattended inside the daily job, so it counts every
cent, stops at a ceiling and never lets a model failure abort the feed.

Model, temperature, retry count and the spend ceiling come from the client
config — a colleague adapting this repo has a different provider and budget.
"""
import os
import json
import time
import requests

API_URL = 'https://openrouter.ai/api/v1/chat/completions'
CREDITS_URL = 'https://openrouter.ai/api/v1/credits'

DEFAULTS = {
    'model': 'google/gemini-3.1-flash-lite',
    'temperature': 0.3,
    'max_spend_usd': 1.0,
    'min_balance_usd': 1.0,
    'attempts': 3,
    'timeout': 90,
    'retries': 2,
    'enabled': True,
}

# Asking again will not help with these: the request or the account is wrong.
FATAL_STATUS = (400, 401, 402, 403, 404)


def settings(cfg):
    """Client config merged over the defaults."""
    merged = dict(DEFAULTS)
    merged.update(cfg.get('text_generation') or {})
    return merged


def _reason(response):
    """The error line itself, without the account details around it."""
    try:
        return str(response.json()['error']['message'])[:160]
    except Exception:
        return response.text[:160]


class BudgetExceeded(RuntimeError):
    """The run hit its spending ceiling — remaining offers keep their old copy."""


def load_environment():
    """Find the secrets file wherever this checkout happens to sit.

    The working copy keeps them in `Credentials.env` a few levels up; a clone of
    the public repository keeps a plain `.env` at its root. Walking up for both
    means the same scripts run in either layout without a path to edit.
    """
    from dotenv import load_dotenv
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        for name in ('Credentials.env', '.env'):
            candidate = os.path.join(here, name)
            if os.path.exists(candidate):
                load_dotenv(candidate)
                return candidate
        here = os.path.dirname(here)
    return ''


def relay_endpoint():
    """Where to send calls when the provider refuses this network.

    openrouter.ai answers 403 «Access denied by security policy» to the Yandex
    Cloud function — the same wall api.telegram.org puts up, and the same relay
    gets around it. Derived from RELAY_URL so there is one address to configure,
    overridable when the two endpoints ever live apart.
    """
    explicit = os.environ.get('OPENROUTER_RELAY_URL')
    if explicit:
        return explicit
    notify = os.environ.get('RELAY_URL') or ''
    return notify.rsplit('/', 1)[0] + '/openrouter' if notify else ''


class Client(object):
    """Talks to OpenRouter directly, or through the relay when one is set.

    The relay holds the API key, so a client in relay mode has none: the machine
    running the daily job cannot spend money except through an endpoint that
    only forwards these two calls.
    """

    def __init__(self, api_key, opts, relay='', relay_secret=''):
        self.api_key = api_key
        self.relay = relay
        self.relay_secret = relay_secret
        self.model = opts['model']
        self.temperature = opts['temperature']
        self.max_spend = opts['max_spend_usd']
        self.attempts = opts['attempts']
        self.timeout = opts['timeout']
        self.spent = 0.0
        self.calls = 0
        self.failures = 0
        self.blocked = False

    # The bare python-requests user agent is what a lot of edge filters look at
    # first, and the cloud function's requests come back «Access denied by
    # security policy» while the same call succeeds from a laptop.
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

    def _headers(self):
        return {'Authorization': 'Bearer %s' % self.api_key,
                'Content-Type': 'application/json; charset=utf-8',
                'User-Agent': self.UA,
                'HTTP-Referer': 'https://example.com',
                'X-Title': 'feed-ad-texts'}

    def _relay_headers(self):
        return {'Content-Type': 'application/json; charset=utf-8',
                'x-relay-secret': self.relay_secret}

    def _post(self, op, payload=None):
        """One call, direct or relayed. The relay passes the provider's status
        and body through untouched, so everything downstream reads the same."""
        if self.relay:
            body = json.dumps({'op': op, 'payload': payload}, ensure_ascii=False)
            return requests.post(self.relay, headers=self._relay_headers(),
                                 data=body.encode('utf-8'), timeout=self.timeout)
        if op == 'credits':
            return requests.get(CREDITS_URL, headers=self._headers(), timeout=30)
        return requests.post(API_URL, headers=self._headers(),
                             data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                             timeout=self.timeout)

    def credits(self):
        """Balance left on the account, or None when the endpoint is unhappy.

        The figure lags behind actual usage, so it is only good for the
        pre-flight check — the per-call cost comes from the response itself.
        """
        try:
            r = self._post('credits')
        except Exception as exc:
            print('      [llm] баланс не прочитали, запрос не прошёл: %s' % str(exc)[:160])
            return None
        try:
            d = r.json()['data']
            return float(d['total_credits']) - float(d['total_usage'])
        except Exception:
            # What came back matters: the same call works from a laptop and
            # returned an unreadable body from the cloud function, and guessing
            # at the reason is how a silent pre-flight check stays silent.
            self.blocked = r.status_code == 403
            print('      [llm] баланс не прочитали: HTTP %s, ответ: %s'
                  % (r.status_code, _reason(r)))
            return None

    def chat(self, messages, temperature=None):
        """One completion. Returns the text; the cost lands in self.spent."""
        if self.max_spend and self.spent >= self.max_spend:
            raise BudgetExceeded('потрачено $%.4f при потолке $%.2f'
                                 % (self.spent, self.max_spend))
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature if temperature is None else temperature,
            'usage': {'include': True},
        }

        last = None
        for attempt in range(self.attempts):
            try:
                r = self._post('chat', payload)
                if r.status_code in FATAL_STATUS:
                    raise RuntimeError('HTTP %s %s' % (r.status_code, _reason(r)))
                if r.status_code != 200:
                    raise requests.RequestException('HTTP %s %s'
                                                    % (r.status_code, r.text[:160]))
                body = r.json()
                # Cost is billed even on a reply we end up rejecting, so it is
                # counted here rather than at the call site.
                self.spent += float((body.get('usage') or {}).get('cost') or 0)
                self.calls += 1
                return body['choices'][0]['message']['content']
            except RuntimeError:
                self.failures += 1
                raise
            except Exception as exc:
                last = exc
                if attempt < self.attempts - 1:
                    time.sleep(2 * (attempt + 1))
        self.failures += 1
        raise RuntimeError('OpenRouter не ответил: %s' % str(last)[:200])

    def report(self):
        return dict(calls=self.calls, failures=self.failures,
                    spent=round(self.spent, 5), model=self.model)


def open_client(cfg):
    """Build a client, or explain why generation is off this run.

    Returns (client, reason). A None client is not an error: the run simply
    keeps the copy it already has, which is always safer than publishing worse
    text or aborting the feed.
    """
    opts = settings(cfg)
    if not opts.get('enabled', True):
        return None, 'генерация текстов выключена в конфиге'
    # Either we hold the key ourselves, or the relay does. In the cloud it is
    # the relay, and the function is deployed without a key on purpose.
    relay = relay_endpoint() if os.environ.get('RELAY_SECRET') else ''
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key and not relay:
        return None, 'нет ни OPENROUTER_API_KEY, ни ретранслятора'
    if api_key and not os.environ.get('PREFER_RELAY'):
        relay = ''
    client = Client(api_key, opts, relay, os.environ.get('RELAY_SECRET', ''))
    balance = client.credits()
    if client.blocked:
        # Verified from inside the Yandex Cloud function: the provider answers
        # «Access denied by security policy» to this network, on the balance
        # endpoint and on the completions endpoint alike. Trying anyway would
        # burn three attempts per new programme and land in the fallback with a
        # message that reads like the model degraded.
        return None, 'провайдер отказал этой сети (403) — нужен ретранслятор'
    floor = opts.get('min_balance_usd') or 0
    if balance is not None and balance < floor:
        return None, ('на балансе OpenRouter $%.2f при пороге $%.2f' % (balance, floor))
    return client, ''
