/**
 * WikiSidebar — canonical local wiki navigation surface.
 */

import { memo, useCallback, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import type { WikiPageNode } from '../../api/wiki';
import {
  type WikiDomain,
  groupWikiPages,
  pageTypeLabel,
} from './wikiData';

interface WikiSidebarProps {
  pages: WikiPageNode[];
  activePath: string;
  isLoading: boolean;
  domain: WikiDomain;
  onSelect: (path: string) => void;
  /**
   * Public apex preview (`amprealize.ai`): show a single “Wiki” group with
   * domain links only — matches the marketing-site sidebar (no folder/page tree).
   */
  previewDomains?: { id: WikiDomain; label: string }[];
  onPreviewDomainNavigate?: (id: WikiDomain) => void;
}

const FolderChevron = ({ expanded }: { expanded: boolean }) => (
  <svg
    className={`wiki-sidebar-folder-chevron ${expanded ? 'expanded' : ''}`}
    viewBox="0 0 16 16"
    fill="none"
  >
    <path d="M6 3.5L10.5 8 6 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const PageIcon = ({ pageType }: { pageType: string }) => {
  const color = pageTypeColor(pageType);
  return (
    <svg className="wiki-sidebar-item-icon" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="1.5" width="11" height="13" rx="1.5" stroke={color} strokeWidth="1.2" />
      <path d="M5 5h6M5 7.5h6M5 10h4" stroke={color} strokeWidth="1" strokeLinecap="round" opacity="0.5" />
    </svg>
  );
};

function pageTypeColor(type: string): string {
  switch (type) {
    case 'concept': return 'var(--color-accent)';
    case 'reference': return 'var(--color-accent-secondary)';
    case 'howto': return 'var(--color-success)';
    case 'architecture': return 'var(--color-warning)';
    case 'practice': return 'var(--color-info)';
    case 'in-practice': return 'var(--color-accent-tertiary)';
    case 'technology': return 'var(--color-warning)';
    case 'path': return 'var(--color-accent)';
    case 'glossary': return 'var(--color-text-tertiary)';
    default: return 'var(--color-text-disabled)';
  }
}

const DomainRowIcon = () => (
  <svg className="wiki-sidebar-item-icon wiki-sidebar-item-icon--domain" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M3 4.5A1.5 1.5 0 0 1 4.5 3h3A1.5 1.5 0 0 1 9 4.5v11A1.5 1.5 0 0 1 7.5 17h-3A1.5 1.5 0 0 1 3 15.5v-11Z"
      stroke="currentColor"
      strokeWidth="1.2"
    />
    <path
      d="M9 5.5A1.5 1.5 0 0 1 10.5 4h5A1.5 1.5 0 0 1 17 5.5v10a1.5 1.5 0 0 1-1.5 1.5h-5A1.5 1.5 0 0 1 9 15.5v-10Z"
      stroke="currentColor"
      strokeWidth="1.2"
    />
  </svg>
);

export const WikiSidebar = memo(function WikiSidebar({
  pages,
  activePath,
  isLoading,
  domain,
  onSelect,
  previewDomains,
  onPreviewDomainNavigate,
}: WikiSidebarProps) {
  const groups = useMemo(() => groupWikiPages(pages), [pages]);
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const [previewWikiOpen, setPreviewWikiOpen] = useState(true);
  const activeFolder = pages.find((page) => page.path === activePath)?.folder;

  const toggleFolder = useCallback((folder: string) => {
    setCollapsedFolders((previous) => {
      const next = new Set(previous);
      if (next.has(folder)) next.delete(folder);
      else next.add(folder);
      return next;
    });
  }, []);

  if (isLoading) {
    return (
      <div className="wiki-sidebar">
        <div className="wiki-sidebar-hero">
          <div className="wiki-skeleton wiki-skeleton-title" />
          <div className="wiki-skeleton wiki-skeleton-line wide" />
        </div>
        <div className="wiki-sidebar-section">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="wiki-sidebar-item">
              <div className={`wiki-skeleton wiki-skeleton-line ${index % 3 === 0 ? 'wide' : index % 3 === 1 ? 'medium' : 'narrow'}`} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (previewDomains?.length && onPreviewDomainNavigate) {
    const goDomain = onPreviewDomainNavigate;
    return (
      <div className="wiki-sidebar wiki-sidebar--preview-domains">
        <div className="wiki-sidebar-folder wiki-sidebar-folder--preview-root">
          <button
            type="button"
            className="wiki-sidebar-folder-toggle"
            onClick={() => setPreviewWikiOpen((open) => !open)}
          >
            <FolderChevron expanded={previewWikiOpen} />
            Wiki
          </button>
          <div
            className={`wiki-sidebar-folder-body ${previewWikiOpen ? '' : 'collapsed'}`}
            style={
              previewWikiOpen
                ? ({ maxHeight: previewDomains.length * 80 + 24 } as CSSProperties)
                : { maxHeight: 0 }
            }
          >
            {previewDomains.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`wiki-sidebar-item wiki-sidebar-item--domain ${domain === item.id ? 'active' : ''}`}
                onClick={() => goDomain(item.id)}
              >
                <DomainRowIcon />
                <span className="wiki-sidebar-item-copy">
                  <span>{item.label}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="wiki-sidebar">
      {groups.length === 0 ? (
        <div className="wiki-sidebar-empty">No pages yet</div>
      ) : (
        groups.map((group) => {
          const isCollapsed = collapsedFolders.has(group.folder) && group.folder !== activeFolder;

          return (
            <div key={group.folder} className="wiki-sidebar-folder">
              <button
                type="button"
                className="wiki-sidebar-folder-toggle"
                onClick={() => toggleFolder(group.folder)}
              >
                <FolderChevron expanded={!isCollapsed} />
                {group.label}
              </button>
              <div
                className={`wiki-sidebar-folder-body ${isCollapsed ? 'collapsed' : ''}`}
                style={isCollapsed ? { maxHeight: 0 } : { maxHeight: group.pages.length * 80 + 24 } as CSSProperties}
              >
                {group.pages.map((page) => (
                  <button
                    key={page.path}
                    type="button"
                    className={`wiki-sidebar-item ${activePath === page.path ? 'active' : ''}`}
                    style={{ '--indent': group.folder ? '12px' : '0px' } as CSSProperties}
                    onClick={() => onSelect(page.path)}
                  >
                    <PageIcon pageType={page.page_type} />
                    <span className="wiki-sidebar-item-copy">
                      <span>{page.title}</span>
                      <span className="wiki-sidebar-item-meta">{pageTypeLabel(page.page_type)}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
});
