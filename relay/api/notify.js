// Telegram relay.
//
// api.telegram.org is unreachable from Yandex Cloud, where the weekly feed job
// runs. The job posts its report here instead and this function forwards it.
// The shared secret keeps the endpoint from becoming an open spam relay.

const TELEGRAM_LIMIT = 4000;

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

  const token = process.env.TELEGRAM_BOT_TOKEN_FEEDS;
  const defaultChat = process.env.TELEGRAM_CHAT_ID_FEEDS;
  if (!token || !defaultChat) {
    res.status(500).json({ error: 'relay is missing telegram configuration' });
    return;
  }

  let payload = req.body;
  if (typeof payload === 'string') {
    try {
      payload = JSON.parse(payload);
    } catch (e) {
      res.status(400).json({ error: 'body is not valid json' });
      return;
    }
  }
  const text = payload && payload.text;
  if (!text || typeof text !== 'string') {
    res.status(400).json({ error: 'field "text" is required' });
    return;
  }
  const chatId = (payload && payload.chat_id) || defaultChat;

  const chunks = [];
  for (let i = 0; i < text.length; i += TELEGRAM_LIMIT) {
    chunks.push(text.slice(i, i + TELEGRAM_LIMIT));
  }

  try {
    for (const chunk of chunks) {
      const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text: chunk,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        }),
      });
      if (!r.ok) {
        const detail = await r.text();
        res.status(502).json({ error: 'telegram rejected', detail: detail.slice(0, 300) });
        return;
      }
    }
    res.status(200).json({ ok: true, chunks: chunks.length });
  } catch (e) {
    res.status(502).json({ error: 'telegram unreachable', detail: String(e).slice(0, 300) });
  }
};
