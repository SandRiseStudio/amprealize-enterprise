interface Env {
  SLACK_WEBHOOK_URL?: string;
  NOTIFY_EMAIL?: string;
}

type RequestBody = {
  name?: string;
  email?: string;
  message?: string;
};

function json(status: number, body: unknown, origin: string): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'access-control-allow-origin': origin,
      'access-control-allow-methods': 'POST, OPTIONS',
      'access-control-allow-headers': 'content-type',
      'access-control-max-age': '86400',
      'vary': 'Origin',
    },
  });
}

function getAllowedOrigin(req: Request): string {
  const origin = req.headers.get('origin');
  if (origin === 'https://amprealize.ai') return origin;
  // Local dev convenience:
  if (origin && origin.startsWith('http://localhost:')) return origin;
  return 'https://amprealize.ai';
}

function isEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export async function onRequest(context: { request: Request; env: Env }): Promise<Response> {
  const { request, env } = context;
  const origin = getAllowedOrigin(request);

  if (request.method === 'OPTIONS') {
    return json(204, { ok: true }, origin);
  }

  if (request.method !== 'POST') {
    return json(405, { ok: false, error: 'Method not allowed' }, origin);
  }

  let payload: RequestBody | null = null;
  try {
    payload = (await request.json()) as RequestBody;
  } catch {
    payload = null;
  }

  const name = String(payload?.name ?? '').trim();
  const email = String(payload?.email ?? '').trim();
  const messageRaw = String(payload?.message ?? '').trim();
  const message = messageRaw.length > 1200 ? `${messageRaw.slice(0, 1200)}…` : messageRaw;

  if (!name) return json(400, { ok: false, error: 'Missing name' }, origin);
  if (!email || !isEmail(email)) return json(400, { ok: false, error: 'Invalid email' }, origin);

  if (!env.SLACK_WEBHOOK_URL) {
    return json(500, { ok: false, error: 'Server not configured' }, origin);
  }

  const ts = new Date().toISOString();
  const url = request.headers.get('referer') || '';

  const slackBody = {
    blocks: [
      { type: 'header', text: { type: 'plain_text', text: 'Amprealize access request', emoji: false } },
      {
        type: 'section',
        fields: [
          { type: 'mrkdwn', text: `*Name*\n${name}` },
          { type: 'mrkdwn', text: `*Email*\n${email}` },
        ],
      },
      ...(message
        ? [
            {
              type: 'section',
              text: { type: 'mrkdwn', text: `*What they're building*\n${message}` },
            },
          ]
        : []),
      {
        type: 'context',
        elements: [
          { type: 'mrkdwn', text: `*Time*: ${ts}` },
          ...(url ? [{ type: 'mrkdwn', text: `*Source*: ${url}` }] : []),
        ],
      },
    ],
  };

  const slackRes = await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(slackBody),
  });

  if (!slackRes.ok) {
    return json(502, { ok: false, error: 'Failed to notify' }, origin);
  }

  return json(200, { ok: true }, origin);
}
