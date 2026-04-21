/**
 * Reverse-proxy public wiki SPA assets from the marketing apex to the wiki
 * Pages deployment so the browser stays on amprealize.ai while loading the
 * Vite bundle (same-origin /assets/* and /wiki/*).
 *
 * Set `WIKI_UPSTREAM` in the Cloudflare Pages project (e.g. https://amprealize-web.pages.dev).
 */
const DEFAULT_UPSTREAM = 'https://amprealize-web.pages.dev';

function upstreamBase(env) {
  const raw = env?.WIKI_UPSTREAM ?? DEFAULT_UPSTREAM;
  return raw.replace(/\/+$/, '');
}

function shouldProxy(pathname) {
  if (pathname === '/favicon.png') return true;
  if (pathname === '/wiki' || pathname.startsWith('/wiki/')) return true;
  if (pathname.startsWith('/assets/')) return true;
  return false;
}

function forwardableHeaders(src, targetUrl) {
  const out = new Headers();
  const skip = new Set([
    'host',
    'connection',
    'content-length',
    'transfer-encoding',
    'cf-connecting-ip',
    'cf-ray',
    'cf-visitor',
    'cf-ipcountry',
    'x-forwarded-host',
  ]);
  src.forEach((value, key) => {
    if (!skip.has(key.toLowerCase())) out.append(key, value);
  });
  out.set('host', targetUrl.host);
  return out;
}

function rewriteLocation(loc, requestOrigin, upstreamOrigin) {
  if (!loc) return null;
  if (loc.startsWith(upstreamOrigin)) {
    return loc.replace(upstreamOrigin, requestOrigin);
  }
  try {
    const u = new URL(loc);
    if (u.origin === new URL(upstreamOrigin).origin) {
      return `${requestOrigin}${u.pathname}${u.search}${u.hash}`;
    }
  } catch {
    /* ignore */
  }
  return loc;
}

/**
 * @param {{ request: Request; env: { WIKI_UPSTREAM?: string }; next: () => Promise<Response> }} context
 */
export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (!shouldProxy(url.pathname)) {
    return context.next();
  }

  const upstreamOrigin = upstreamBase(context.env);
  const target = new URL(url.pathname + url.search, upstreamOrigin);

  const init = {
    method: context.request.method,
    headers: forwardableHeaders(context.request.headers, target),
    redirect: 'manual',
  };
  if (context.request.method !== 'GET' && context.request.method !== 'HEAD') {
    init.body = context.request.body;
  }

  const res = await fetch(target.toString(), init);
  const headers = new Headers(res.headers);
  const requestOrigin = url.origin;

  const loc = headers.get('location');
  if (loc) {
    const nextLoc = rewriteLocation(loc, requestOrigin, upstreamOrigin);
    if (nextLoc) headers.set('location', nextLoc);
  }

  headers.delete('content-security-policy');
  headers.delete('content-security-policy-report-only');

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}
