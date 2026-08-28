// OpenRouter relay.
//
// openrouter.ai answers «Access denied by security policy» to requests from
// Yandex Cloud, where the daily feed job runs — verified from inside the
// function, on the completions endpoint and on the balance endpoint alike. The
// job calls this instead and Vercel forwards the request.
//
// The API key lives here rather than in the cloud function on purpose: the
// function then has no way to spend money directly, and rotating the key means
// redeploying one small relay instead of two cloud functions.

const BASE = 'https://openrouter.ai/api/v1';

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  const expected = process.env.RELAY_SECRET;
  if (!expected || req.headers['x-relay-secret'] !== expected) {
    res.status(401).json({ error: 'unauthorized' });
    return;
  }

  const key = process.env.OPENROUTER_API_KEY;
  if (!key) {
    res.status(500).json({ error: 'relay is missing OPENROUTER_API_KEY' });
    return;
  }

  let body = req.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch (e) {
      res.status(400).json({ error: 'body is not valid json' });
      return;
    }
  }

  const op = (body && body.op) || 'chat';
  const headers = {
    Authorization: `Bearer ${key}`,
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://example.com',
    'X-Title': 'feed-ad-texts',
  };

  try {
    let upstream;
    if (op === 'credits') {
      upstream = await fetch(`${BASE}/credits`, { headers });
    } else if (op === 'chat') {
      if (!body.payload || typeof body.payload !== 'object') {
        res.status(400).json({ error: 'field "payload" is required for op=chat' });
        return;
      }
      upstream = await fetch(`${BASE}/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body.payload),
      });
    } else {
      // Deliberately not a general-purpose proxy: only the two calls the feed
      // job makes are forwarded.
      res.status(400).json({ error: `unknown op "${op}"` });
      return;
    }

    // The provider's status and body are passed through untouched, so the
    // caller's own error handling — which statuses are worth retrying, where
    // the cost of a call is read from — keeps working as if it had called
    // OpenRouter directly.
    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.send(text);
  } catch (e) {
    res.status(502).json({ error: 'openrouter unreachable', detail: String(e).slice(0, 300) });
  }
};
