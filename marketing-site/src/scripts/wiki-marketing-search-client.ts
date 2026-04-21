/**
 * Client wiki search — scoring/snippet behavior aligned with web-console `fetchStaticSearch`.
 */

export interface WikiSearchScope {
  id: string;
  label: string;
}

export interface MountWikiSearchOptions {
  scopes: WikiSearchScope[];
}

interface SearchIndexEntry {
  domain: string;
  page_path: string;
  title: string;
  page_type: string;
  body: string;
}

interface SearchHit {
  domain: string;
  page_path: string;
  title: string;
  page_type: string;
  score: number;
  snippet: string;
}

let indexPromise: Promise<SearchIndexEntry[]> | null = null;

function loadIndex(): Promise<SearchIndexEntry[]> {
  indexPromise ??= fetch('/wiki-search-index.json')
    .then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json() as Promise<{ entries: SearchIndexEntry[] }>;
    })
    .then((j) => j.entries ?? []);
  return indexPromise;
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let idx = 0;
  while ((idx = haystack.indexOf(needle, idx)) !== -1) {
    count += 1;
    idx += needle.length;
  }
  return count;
}

function snippetAround(body: string, needle: string, radius = 120): string {
  const lower = body.toLowerCase();
  const idx = lower.indexOf(needle);
  if (idx === -1) {
    return body.slice(0, radius).trim();
  }
  const start = Math.max(0, idx - radius / 2);
  const end = Math.min(body.length, idx + needle.length + radius / 2);
  const prefix = start > 0 ? '…' : '';
  const suffix = end < body.length ? '…' : '';
  return `${prefix}${body.slice(start, end).replace(/\s+/g, ' ').trim()}${suffix}`.slice(0, 200);
}

async function runSearch(query: string, scopeDomain: string | 'all'): Promise<SearchHit[]> {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return [];
  const entries = await loadIndex();
  const results: SearchHit[] = [];
  for (const e of entries) {
    if (scopeDomain !== 'all' && e.domain !== scopeDomain) continue;
    const titleHits = countOccurrences(e.title.toLowerCase(), q);
    const bodyHits = countOccurrences(e.body.toLowerCase(), q);
    if (titleHits + bodyHits === 0) continue;
    results.push({
      domain: e.domain,
      page_path: e.page_path,
      title: e.title,
      page_type: e.page_type,
      score: titleHits * 5 + bodyHits,
      snippet: snippetAround(e.body, q),
    });
  }
  results.sort((a, b) => b.score - a.score);
  return results.slice(0, 20);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightParts(text: string, query: string): string {
  const q = query.trim();
  if (!q) return escapeHtml(text);
  const pattern = new RegExp(`(${escapeRe(q)})`, 'ig');
  const parts = text.split(pattern);
  return parts
    .map((part, i) => (i % 2 === 1 ? `<mark>${escapeHtml(part)}</mark>` : escapeHtml(part)))
    .join('');
}

function pageTypeLabel(t: string): string {
  if (!t) return 'Page';
  return t.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function domainLabel(scopes: WikiSearchScope[], id: string): string {
  return scopes.find((s) => s.id === id)?.label ?? id;
}

function searchIconSvg(): string {
  return `<svg class="wiki-search-input-icon" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="4.5" stroke="currentColor" stroke-width="1.5"/><path d="M10.5 10.5L13.5 13.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;
}

export function mountWikiMarketingSearch(opts: MountWikiSearchOptions): void {
  const { scopes } = opts;
  const triggers = document.querySelectorAll<HTMLElement>('.marketing-wiki-search-open');

  let overlay: HTMLDivElement | null = null;
  let inputEl: HTMLInputElement | null = null;
  let resultsEl: HTMLDivElement | null = null;
  let scope = 'all';
  let query = '';
  let results: SearchHit[] = [];
  let focusIndex = 0;
  let loading = false;

  function close() {
    overlay?.remove();
    overlay = null;
    inputEl = null;
    resultsEl = null;
    document.body.style.overflow = '';
  }

  function navigateTo(domain: string, pagePath: string) {
    window.location.href = `/wiki/${domain}/${pagePath}`;
  }

  function clampFocus() {
    if (results.length === 0) focusIndex = 0;
    else focusIndex = Math.min(Math.max(focusIndex, 0), results.length - 1);
  }

  function updateFocusClass() {
    if (!resultsEl) return;
    resultsEl.querySelectorAll('.wiki-search-result-item').forEach((el, i) => {
      el.classList.toggle('focused', i === focusIndex);
    });
    const row = resultsEl.querySelector<HTMLElement>(`[data-search-index="${focusIndex}"]`);
    row?.scrollIntoView({ block: 'nearest' });
  }

  function placeholder(): string {
    if (scope === 'all') return 'Search across all wiki knowledge...';
    return `Search ${domainLabel(scopes, scope)}...`;
  }

  function renderScopeChips(container: HTMLElement) {
    container.innerHTML = scopes
      .map(
        (s) =>
          `<button type="button" class="wiki-search-scope-chip ${scope === s.id ? 'active' : ''}" data-scope="${escapeHtml(s.id)}" role="tab" aria-selected="${scope === s.id}">${escapeHtml(s.label)}</button>`,
      )
      .join('');
    container.querySelectorAll<HTMLButtonElement>('[data-scope]').forEach((btn) => {
      btn.addEventListener('click', () => {
        scope = btn.dataset.scope ?? 'all';
        focusIndex = 0;
        renderScopeChips(container);
        if (inputEl) inputEl.placeholder = placeholder();
        void refreshResults();
      });
    });
  }

  function renderResultsHtml(): string {
    if (query.length < 2) {
      return `<div class="wiki-search-empty">Search all domains, then jump straight into an article, path, or reference.</div>`;
    }
    if (loading) {
      return `<div class="wiki-search-empty">Searching the wiki…</div>`;
    }
    if (results.length === 0) {
      const scopeWord = scope === 'all' ? 'wiki' : domainLabel(scopes, scope).toLowerCase();
      return `<div class="wiki-search-empty">No ${scopeWord} results for "${escapeHtml(query)}".</div>`;
    }
    return results
      .map((r, index) => {
        const focused = index === focusIndex ? 'focused' : '';
        return `<button type="button" class="wiki-search-result-item ${focused}" data-search-index="${index}" data-domain="${escapeHtml(r.domain)}" data-path="${escapeHtml(r.page_path)}">
            <div class="wiki-search-result-topline">
              <span class="wiki-search-result-domain-badge">${escapeHtml(domainLabel(scopes, r.domain))}</span>
              <span class="wiki-search-result-type-badge">${escapeHtml(pageTypeLabel(r.page_type))}</span>
            </div>
            <span class="wiki-search-result-title">${highlightParts(r.title, query)}</span>
            <span class="wiki-search-result-snippet">${highlightParts(r.snippet, query)}</span>
            <span class="wiki-search-result-meta">
              <span>${escapeHtml(r.page_path)}</span>
              ${r.score > 0 ? `<span>•</span><span>${Math.round(r.score * 100)}% match</span>` : ''}
            </span>
          </button>`;
      })
      .join('');
  }

  function bindResultRows() {
    if (!resultsEl) return;
    resultsEl.querySelectorAll<HTMLButtonElement>('.wiki-search-result-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const d = btn.dataset.domain;
        const p = btn.dataset.path;
        if (d && p) navigateTo(d, p);
      });
      btn.addEventListener('mouseenter', () => {
        const idx = Number(btn.dataset.searchIndex);
        if (!Number.isNaN(idx)) {
          focusIndex = idx;
          updateFocusClass();
        }
      });
    });
  }

  async function refreshResults() {
    if (!resultsEl) return;
    loading = true;
    resultsEl.innerHTML = renderResultsHtml();
    bindResultRows();
    try {
      results = await runSearch(query, scope as 'all' | string);
      clampFocus();
    } catch {
      results = [];
    }
    loading = false;
    resultsEl.innerHTML = renderResultsHtml();
    bindResultRows();
    updateFocusClass();
  }

  function open() {
    if (overlay) return;
    scope = 'all';
    query = '';
    results = [];
    focusIndex = 0;
    loading = false;

    overlay = document.createElement('div');
    overlay.className = 'wiki-search-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Search wiki');

    const panel = document.createElement('div');
    panel.className = 'wiki-search-panel';

    const inputWrap = document.createElement('div');
    inputWrap.className = 'wiki-search-input-wrap';
    inputWrap.innerHTML = searchIconSvg();
    inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.className = 'wiki-search-input';
    inputEl.placeholder = placeholder();
    inputEl.setAttribute('aria-label', 'Search query');
    inputEl.autocomplete = 'off';
    inputWrap.appendChild(inputEl);

    const scopesRow = document.createElement('div');
    scopesRow.className = 'wiki-search-scopes';
    scopesRow.setAttribute('role', 'tablist');
    scopesRow.setAttribute('aria-label', 'Search scope');
    renderScopeChips(scopesRow);

    resultsEl = document.createElement('div');
    resultsEl.className = 'wiki-search-results';
    resultsEl.innerHTML = renderResultsHtml();

    const footer = document.createElement('div');
    footer.className = 'wiki-search-footer';
    footer.innerHTML =
      '<span><kbd>↑</kbd> <kbd>↓</kbd> navigate</span><span><kbd>↵</kbd> open</span><span><kbd>esc</kbd> close</span>';

    panel.append(inputWrap, scopesRow, resultsEl, footer);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';

    inputEl.addEventListener('input', () => {
      query = inputEl?.value ?? '';
      focusIndex = 0;
      void refreshResults();
    });

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });

    panel.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        focusIndex = Math.min(focusIndex + 1, Math.max(results.length - 1, 0));
        updateFocusClass();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        focusIndex = Math.max(focusIndex - 1, 0);
        updateFocusClass();
      } else if (e.key === 'Enter' && results[focusIndex]) {
        e.preventDefault();
        const r = results[focusIndex]!;
        navigateTo(r.domain, r.page_path);
      }
    });

    requestAnimationFrame(() => {
      inputEl?.focus();
    });
    void refreshResults();
  }

  triggers.forEach((el) => {
    el.addEventListener('click', () => open());
  });

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (overlay) close();
      else open();
    }
  });
}
