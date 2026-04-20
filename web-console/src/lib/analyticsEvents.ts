/**
 * Amprealize product analytics — typed event catalog (v1)
 *
 * Single source of truth for PostHog event names and their property shapes.
 * All consumers should import helpers from here rather than calling
 * `capture()` with ad-hoc strings.
 *
 * Ambient properties (tenant_id, edition, surface, git_sha) are merged in
 * automatically by posthog.ts — no need to pass them per-call.
 */

import { capture } from './posthog';

// ---------------------------------------------------------------------------
// Session / Auth
// ---------------------------------------------------------------------------

export function trackUserSignedIn(props: {
  method: 'device_flow' | 'oauth_github' | 'oauth_google' | 'client_credentials';
  userId: string;
}): void {
  capture('user_signed_in', props);
}

export function trackUserSignedOut(props: { userId: string }): void {
  capture('user_signed_out', props);
}

// ---------------------------------------------------------------------------
// Behavior system
// ---------------------------------------------------------------------------

export function trackBehaviorRetrieved(props: {
  behaviorSlug: string;
  behaviorId?: string;
  source: 'mcp' | 'rest' | 'web';
  topK?: number;
}): void {
  capture('behavior_retrieved', props);
}

export function trackBehaviorApplied(props: {
  behaviorSlug: string;
  behaviorId?: string;
  context: 'bci_panel' | 'plan_composer' | 'other';
}): void {
  capture('behavior_applied', props);
}

export function trackPlanCreated(props: {
  projectId?: string;
  hasChecklist: boolean;
  behaviorCount: number;
}): void {
  capture('plan_created', props);
}

export function trackPlanOpened(props: {
  projectId?: string;
  planId: string;
}): void {
  capture('plan_opened', props);
}

// ---------------------------------------------------------------------------
// Board / Work items
// ---------------------------------------------------------------------------

export function trackBoardOpened(props: {
  projectId: string;
  boardId: string;
  view: 'board' | 'outline' | 'gantt';
}): void {
  capture('board_opened', props);
}

export function trackBoardItemCreated(props: {
  projectId: string;
  boardId: string;
  itemType: string;
}): void {
  capture('board_item_created', props);
}

export function trackBoardItemMoved(props: {
  projectId: string;
  boardId: string;
  fromStatus: string;
  toStatus: string;
}): void {
  capture('board_item_moved', props);
}

export function trackBoardViewToggled(props: {
  projectId: string;
  boardId: string;
  view: 'board' | 'outline' | 'gantt';
}): void {
  capture('board_view_toggled', props);
}

// ---------------------------------------------------------------------------
// Wiki
// ---------------------------------------------------------------------------

export function trackWikiPageViewed(props: {
  domain: string;
  path: string;
}): void {
  capture('wiki_page_viewed', props);
}

export function trackWikiSearchSubmitted(props: {
  query: string;
  domain?: string;
  resultCount?: number;
}): void {
  // Strip PII: don't log the raw query if it contains an email pattern.
  const safeQuery = /\S+@\S+/.test(props.query) ? '[redacted:email]' : props.query;
  capture('wiki_search_submitted', { ...props, query: safeQuery });
}

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

export function trackWorkspaceSwitched(props: {
  fromOrgId?: string;
  toOrgId: string;
}): void {
  capture('workspace_switched', props);
}

export function trackEditionBannerCtaClicked(props: {
  currentEdition: string;
  targetEdition: string;
  ctaLabel: string;
}): void {
  capture('edition_banner_cta_clicked', props);
}
