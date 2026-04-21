import { Marked } from 'marked';
import type { Tokens } from 'marked';
import { codeToHtml } from 'shiki';
import type { BundledLanguage } from 'shiki';
import { isWikiDomain, resolveWikiMarketingUrl, type WikiDomain } from './wikiLinkResolve';

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function stripLeadingTitle(markdown: string, title: string): string {
  const lines = markdown.split('\n');
  const firstContentIndex = lines.findIndex((line) => line.trim().length > 0);
  if (firstContentIndex === -1) return markdown;
  const firstLine = lines[firstContentIndex]!;
  const heading = firstLine.match(/^#\s+(.+)/);
  if (!heading) return markdown;
  if (heading[1]!.trim().toLowerCase() !== title.trim().toLowerCase()) return markdown;
  const nextLines = [...lines];
  nextLines.splice(firstContentIndex, 1);
  return nextLines.join('\n').trim();
}

const BT = '`';
const FENCE_RE = new RegExp(
  `^${BT}${BT}${BT}([\\w+-]*)\\r?\\n([\\s\\S]*?)^${BT}${BT}${BT}[ \\t]*$`,
  'gm',
);

type CodeSlot = { lang: string; code: string };

async function highlightCode(text: string, lang?: string | null): Promise<string> {
  const raw = (lang || 'plaintext').trim() || 'plaintext';
  try {
    return await codeToHtml(text, {
      lang: raw as BundledLanguage,
      theme: 'github-light',
    });
  } catch {
    try {
      return await codeToHtml(text, { lang: 'plaintext', theme: 'github-light' });
    } catch {
      return `<pre class="shiki"><code>${escapeHtml(text)}</code></pre>`;
    }
  }
}

// Replace fenced code blocks with HTML slots, run Marked, then splice Shiki output back in.
async function extractCodeFences(markdown: string): Promise<{ markdown: string; slots: CodeSlot[] }> {
  const slots: CodeSlot[] = [];
  let i = 0;
  const md = markdown.replace(FENCE_RE, (_full, lang: string, code: string) => {
    slots.push({
      lang: (lang || 'plaintext').trim() || 'plaintext',
      code: code.replace(/\s+$/, ''),
    });
    const id = i++;
    return `\n\n<div class="marketing-wiki-code-slot" data-slot="${id}"></div>\n\n`;
  });
  return { markdown: md, slots };
}

async function fillCodeSlots(html: string, slots: CodeSlot[]): Promise<string> {
  let out = html;
  for (let idx = 0; idx < slots.length; idx++) {
    const slot = slots[idx]!;
    const highlighted = await highlightCode(slot.code, slot.lang);
    const needle = `<div class="marketing-wiki-code-slot" data-slot="${idx}"></div>`;
    const wrapped = `<div class="marketing-wiki-code-wrap">${highlighted}</div>`;
    if (out.includes(needle)) {
      out = out.replace(needle, wrapped);
      continue;
    }
    const loose = new RegExp(
      `<div\\s+class="marketing-wiki-code-slot"\\s+data-slot="${idx}"\\s*>\\s*</div>`,
      'i',
    );
    out = out.replace(loose, wrapped);
  }
  return out;
}

// Markdown to HTML with Shiki code blocks and wiki-internal links resolved like WikiArticle.
export async function renderWikiMarkdownToHtml(
  domain: string,
  pagePath: string,
  markdown: string,
  title: string,
): Promise<string> {
  const body = stripLeadingTitle(markdown, title);
  const wikiDomain: WikiDomain = isWikiDomain(domain) ? domain : 'infra';

  const { markdown: mdWithSlots, slots } = await extractCodeFences(body);

  const md = new Marked();
  md.setOptions({ gfm: true });
  md.use({
    renderer: {
      link(token: Tokens.Link): string {
        const inner = this.parser.parseInline(token.tokens);
        const resolved = resolveWikiMarketingUrl(wikiDomain, pagePath, token.href);
        const href = resolved ?? token.href;
        const t = token.title ? ` title="${escapeHtml(token.title)}"` : '';
        return `<a href="${escapeHtml(href)}"${t}>${inner}</a>`;
      },
    },
  });

  const html = md.parse(mdWithSlots) as string;
  return fillCodeSlots(html, slots);
}
