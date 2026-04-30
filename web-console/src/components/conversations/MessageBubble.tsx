/**
 * MessageBubble — Individual message display with structured cards and reactions.
 *
 * Supports text (react-markdown), StatusCard, BlockerCard, ProgressCard,
 * CodeBlock, and system messages. Includes ReactionBar and hover MessageActions.
 */

import { memo, useCallback, useMemo, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useDeleteMessage, useAddReaction, useRemoveReaction } from '../../api/conversations';
import { MessageType, ActorType, type ConversationMessage, type ConversationReaction } from '../../lib/collab-client';
import { buildExecutionControlModel } from '../../lib/executionControls';

// ── Types ────────────────────────────────────────────────────────────────────

export interface MessageBubbleProps {
  message: ConversationMessage;
  isFirstInGroup: boolean;
  isOwn: boolean;
  conversationId: string;
  currentUserId?: string;
  onReply?: (messageId: string) => void;
  onEdit?: (message: ConversationMessage) => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatTimestamp(isoStr: string | undefined | null): string {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function senderLabel(msg: ConversationMessage): string {
  if (msg.metadata?.display_name) return String(msg.metadata.display_name);
  if (msg.sender_type === ActorType.Agent) return 'Agent';
  if (msg.sender_type === ActorType.System) return 'System';
  return msg.sender_id?.slice(0, 8) ?? 'Unknown';
}

function senderInitials(msg: ConversationMessage): string {
  const name = senderLabel(msg);
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ''}${parts[1][0] ?? ''}`.toUpperCase();
}

const QUICK_EMOJIS = ['👍', '❤️', '🎉', '😂', '🤔', '👀'];

// ── Component ────────────────────────────────────────────────────────────────

export const MessageBubble = memo(function MessageBubble({
  message,
  isFirstInGroup,
  isOwn,
  conversationId,
  currentUserId,
  onReply,
  onEdit,
}: MessageBubbleProps) {
  const [showActions, setShowActions] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);

  const deleteMessage = useDeleteMessage();
  const addReaction = useAddReaction();
  const removeReaction = useRemoveReaction();

  const isDeleted = message.is_deleted;
  const isEdited = message.is_edited;

  const msgType = message.message_type ?? MessageType.Text;
  const isSystem = msgType === MessageType.System || message.sender_type === ActorType.System;

  const handleDelete = useCallback(() => {
    deleteMessage.mutate({ conversationId, messageId: message.id });
    setShowActions(false);
  }, [deleteMessage, conversationId, message.id]);

  const handleReaction = useCallback((emoji: string) => {
    const existing = message.reactions?.find(
      (r) => r.emoji === emoji && r.actor_id === currentUserId,
    );
    if (existing) {
      removeReaction.mutate({ conversationId, messageId: message.id, emoji });
    } else {
      addReaction.mutate({ conversationId, messageId: message.id, emoji });
    }
    setShowEmojiPicker(false);
  }, [addReaction, removeReaction, conversationId, message.id, message.reactions, currentUserId]);

  // ── System messages ──────────────────────────────────────────────────────

  if (isSystem) {
    return (
      <div className="msg-bubble msg-bubble--system">
        <span className="msg-system-text">{message.content ?? 'System event'}</span>
        <span className="msg-system-time">{formatTimestamp(message.created_at)}</span>
      </div>
    );
  }

  // ── Deleted messages ─────────────────────────────────────────────────────

  if (isDeleted) {
    return (
      <div className={`msg-bubble ${isOwn ? 'msg-bubble--own' : ''}`}>
        <span className="msg-deleted-text">This message was deleted</span>
      </div>
    );
  }

  // ── Main bubble ──────────────────────────────────────────────────────────

  return (
    <div
      className={`msg-bubble ${isOwn ? 'msg-bubble--own' : ''} ${isFirstInGroup ? 'msg-bubble--first' : ''}`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => { setShowActions(false); setShowEmojiPicker(false); }}
    >
      {/* Avatar + sender for first in group */}
      {isFirstInGroup && !isOwn && (
        <div className="msg-sender-row">
          <span className="msg-avatar" data-sender-type={message.sender_type}>
            {senderInitials(message)}
          </span>
          <span className="msg-sender-name">{senderLabel(message)}</span>
          <span className="msg-timestamp">{formatTimestamp(message.created_at)}</span>
        </div>
      )}
      {isFirstInGroup && isOwn && (
        <div className="msg-sender-row msg-sender-row--own">
          <span className="msg-timestamp">{formatTimestamp(message.created_at)}</span>
        </div>
      )}

      {/* Content */}
      <div className="msg-content">
        <MessageContent message={message} msgType={msgType} />
        {isEdited && <span className="msg-edited-label">(edited)</span>}
      </div>

      {/* Reactions */}
      {message.reactions && message.reactions.length > 0 && (
        <ReactionBar
          reactions={message.reactions}
          currentUserId={currentUserId}
          onToggle={handleReaction}
        />
      )}

      {/* Hover actions */}
      {showActions && (
        <div className={`msg-actions ${isOwn ? 'msg-actions--own' : ''}`}>
          {onReply && (
            <button
              type="button"
              className="msg-action-btn"
              onClick={() => onReply(message.id)}
              aria-label="Reply"
              title="Reply"
            >
              <ReplyIcon />
            </button>
          )}
          <button
            type="button"
            className="msg-action-btn"
            onClick={() => setShowEmojiPicker((v) => !v)}
            aria-label="Add reaction"
            title="React"
          >
            <EmojiIcon />
          </button>
          {isOwn && onEdit && (
            <button
              type="button"
              className="msg-action-btn"
              onClick={() => onEdit(message)}
              aria-label="Edit"
              title="Edit"
            >
              <EditIcon />
            </button>
          )}
          {isOwn && (
            <button
              type="button"
              className="msg-action-btn msg-action-btn--danger"
              onClick={handleDelete}
              aria-label="Delete"
              title="Delete"
            >
              <TrashIcon />
            </button>
          )}

          {/* Quick emoji picker */}
          {showEmojiPicker && (
            <div className="msg-emoji-picker">
              {QUICK_EMOJIS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  className="msg-emoji-btn"
                  onClick={() => handleReaction(emoji)}
                >
                  {emoji}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

// ── Message Content Router ───────────────────────────────────────────────────

function MessageContent({
  message,
  msgType,
}: {
  message: ConversationMessage;
  msgType: ConversationMessage['message_type'] | null | undefined;
}) {
  const cardKind = String(message.structured_payload?.card_kind ?? '');
  if (cardKind === 'work_item') {
    return <WorkItemArtifactCard payload={message.structured_payload} />;
  }
  if (cardKind === 'run') {
    return <RunArtifactCard payload={message.structured_payload} />;
  }
  if (cardKind === 'plan') {
    return <PlanArtifactCard payload={message.structured_payload} />;
  }
  if (cardKind === 'recovery') {
    return <RecoveryArtifactCard payload={message.structured_payload} />;
  }

  switch (msgType) {
    case MessageType.StatusCard:
      return <StatusCard payload={message.structured_payload} />;
    case MessageType.BlockerCard:
      return <BlockerCard payload={message.structured_payload} />;
    case MessageType.ProgressCard:
      return <ProgressCard payload={message.structured_payload} />;
    case MessageType.CodeBlock:
      return <CodeBlockCard content={message.content} payload={message.structured_payload} />;
    case MessageType.RunSummary:
      return <RunSummaryCard payload={message.structured_payload} />;
    default:
      return (
        <div className="msg-markdown">
          <Markdown remarkPlugins={[remarkGfm]}>
            {message.content ?? ''}
          </Markdown>
        </div>
      );
  }
}

// ── Structured Cards ─────────────────────────────────────────────────────────

interface CardPayload {
  title?: string;
  summary?: string;
  status?: string;
  icon?: string;
  run_id?: string;
  percentage?: number;
  step_current?: number;
  step_total?: number;
  eta?: string;
  language?: string;
  code?: string;
  card_kind?: string;
  priority?: string;
  assignee?: string;
  agent?: string;
  branch?: string;
  phase?: string;
  queue_state?: string;
  recent_activity?: string;
  progress_pct?: number;
  completion_summary?: string;
  plan_artifact_id?: string;
  work_item_id?: string;
  cta_label?: string;
  secondary_cta_label?: string;
  [key: string]: unknown;
}

function pctValue(value: unknown): number {
  return typeof value === 'number' ? Math.min(100, Math.max(0, value)) : 0;
}

function ArtifactProgress({ value }: { value: unknown }) {
  const pct = pctValue(value);
  return (
    <div className="msg-artifact-progress" aria-label={`Progress ${pct}%`}>
      <div className="msg-artifact-progress-track">
        <div className="msg-artifact-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="msg-artifact-progress-value">{pct}%</span>
    </div>
  );
}

function ArtifactActions({
  primary,
  secondary,
}: {
  primary?: string;
  secondary?: string;
}) {
  if (!primary && !secondary) return null;
  return (
    <div className="msg-artifact-actions">
      {primary && <button type="button" className="msg-card-cta pressable">{primary}</button>}
      {secondary && <button type="button" className="msg-card-cta msg-card-cta--secondary pressable">{secondary}</button>}
    </div>
  );
}

function WorkItemArtifactCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  return (
    <article className="msg-artifact-card msg-artifact-card--work-item" aria-label={`Work item ${p.title ?? p.work_item_id ?? ''}`}>
      <div className="msg-artifact-kicker">Work item</div>
      <div className="msg-artifact-title">{p.title ?? 'Untitled work item'}</div>
      <div className="msg-artifact-meta">
        {p.status && <span>Status: {p.status}</span>}
        {p.priority && <span>Priority: {p.priority}</span>}
        {p.assignee && <span>Assignee: {p.assignee}</span>}
        {p.agent && <span>Agent: {p.agent}</span>}
        {p.branch && <span>Branch: {p.branch}</span>}
      </div>
      {typeof p.progress_pct === 'number' && <ArtifactProgress value={p.progress_pct} />}
      {p.summary && <div className="msg-artifact-summary">{p.summary}</div>}
      {p.run_id && <span className="msg-card-link">Related run: {p.run_id}</span>}
      <ArtifactActions primary={p.cta_label ?? 'Open work item'} secondary={p.secondary_cta_label} />
    </article>
  );
}

function RunArtifactCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  const controls = buildExecutionControlModel({
    rawState: p.queue_state ?? p.status,
    hasExecution: true,
    hasAgentAssignment: true,
  });
  return (
    <article className="msg-artifact-card msg-artifact-card--run" aria-label={`Run ${p.run_id ?? p.title ?? ''}`}>
      <div className="msg-artifact-kicker">Run</div>
      <div className="msg-artifact-title">{p.title ?? p.run_id ?? 'Execution run'}</div>
      <div className="msg-artifact-meta">
        {p.queue_state && <span>Queue: {p.queue_state}</span>}
        {p.phase && <span>Phase: {p.phase}</span>}
        {p.recent_activity && <span>{p.recent_activity}</span>}
      </div>
      {typeof p.progress_pct === 'number' && <ArtifactProgress value={p.progress_pct} />}
      {(p.completion_summary || p.summary) && (
        <div className="msg-artifact-summary">{p.completion_summary ?? p.summary}</div>
      )}
      <ArtifactActions primary={p.cta_label ?? controls.openRunLabel} secondary={p.secondary_cta_label ?? controls.cancelLabel} />
    </article>
  );
}

function PlanArtifactCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  return (
    <article className="msg-artifact-card msg-artifact-card--plan" aria-label={`Plan ${p.plan_artifact_id ?? p.title ?? ''}`}>
      <div className="msg-artifact-kicker">Plan</div>
      <div className="msg-artifact-title">{p.title ?? 'Plan artifact'}</div>
      {p.summary && <div className="msg-artifact-summary">{p.summary}</div>}
      <div className="msg-artifact-meta">
        {p.status && <span>Status: {p.status}</span>}
        {p.plan_artifact_id && <span>{p.plan_artifact_id}</span>}
      </div>
      <ArtifactActions primary={p.cta_label ?? 'Review plan'} secondary={p.secondary_cta_label ?? 'Revise'} />
    </article>
  );
}

function RecoveryArtifactCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  return (
    <article className="msg-artifact-card msg-artifact-card--recovery" aria-label={`Recovery action ${p.title ?? ''}`}>
      <div className="msg-artifact-kicker">Needs attention</div>
      <div className="msg-artifact-title">{p.title ?? 'Action failed'}</div>
      {p.summary && <div className="msg-artifact-summary">{p.summary}</div>}
      <ArtifactActions primary={p.cta_label ?? 'Retry'} secondary={p.secondary_cta_label ?? 'Show details'} />
    </article>
  );
}

function StatusCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  return (
    <div className="msg-card msg-card--status">
      <div className="msg-card-accent msg-card-accent--green" />
      <div className="msg-card-body">
        <div className="msg-card-title">{p.title ?? 'Status update'}</div>
        {p.summary && <div className="msg-card-summary">{p.summary}</div>}
        {p.run_id && (
          <span className="msg-card-link">View run →</span>
        )}
      </div>
    </div>
  );
}

function BlockerCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  const isError = p.status === 'error' || p.status === 'blocked';
  return (
    <div className={`msg-card ${isError ? 'msg-card--error' : 'msg-card--warning'}`}>
      <div className={`msg-card-accent ${isError ? 'msg-card-accent--red' : 'msg-card-accent--amber'}`} />
      <div className="msg-card-body">
        <div className="msg-card-title">{p.title ?? 'Blocker'}</div>
        {p.summary && <div className="msg-card-summary">{p.summary}</div>}
        <button type="button" className="msg-card-cta pressable">Help resolve</button>
      </div>
    </div>
  );
}

function ProgressCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  const pct = typeof p.percentage === 'number' ? Math.min(100, Math.max(0, p.percentage)) : 0;
  return (
    <div className="msg-card msg-card--progress">
      <div className="msg-card-body">
        <div className="msg-card-title">{p.title ?? 'Progress'}</div>
        <div className="msg-progress-bar-track">
          <div className="msg-progress-bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="msg-progress-meta">
          <span>{pct}%</span>
          {p.step_current != null && p.step_total != null && (
            <span>Step {p.step_current}/{p.step_total}</span>
          )}
          {p.eta && <span>ETA: {p.eta}</span>}
        </div>
      </div>
    </div>
  );
}

function CodeBlockCard({ content, payload }: { content?: string | null; payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  const code = p.code ?? content ?? '';
  const lang = p.language ?? '';
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [code]);

  return (
    <div className="msg-code-block">
      <div className="msg-code-header">
        {lang && <span className="msg-code-lang">{lang}</span>}
        <button type="button" className="msg-code-copy pressable" onClick={handleCopy}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="msg-code-pre"><code>{code}</code></pre>
    </div>
  );
}

function RunSummaryCard({ payload }: { payload?: Record<string, unknown> | null }) {
  const p = (payload ?? {}) as CardPayload;
  return (
    <div className="msg-card msg-card--status">
      <div className="msg-card-accent msg-card-accent--blue" />
      <div className="msg-card-body">
        <div className="msg-card-title">{p.title ?? 'Run Summary'}</div>
        {p.summary && <div className="msg-card-summary">{p.summary}</div>}
        {p.run_id && (
          <span className="msg-card-link">View full run →</span>
        )}
      </div>
    </div>
  );
}

// ── ReactionBar ──────────────────────────────────────────────────────────────

function ReactionBar({
  reactions,
  currentUserId,
  onToggle,
}: {
  reactions: ConversationReaction[];
  currentUserId?: string;
  onToggle: (emoji: string) => void;
}) {
  const groups = useMemo(() => {
    const map = new Map<string, { emoji: string; count: number; hasOwn: boolean }>();
    for (const r of reactions) {
      const existing = map.get(r.emoji);
      if (existing) {
        existing.count++;
        if (r.actor_id === currentUserId) existing.hasOwn = true;
      } else {
        map.set(r.emoji, { emoji: r.emoji, count: 1, hasOwn: r.actor_id === currentUserId });
      }
    }
    return Array.from(map.values());
  }, [reactions, currentUserId]);

  return (
    <div className="msg-reaction-bar">
      {groups.map((g) => (
        <button
          key={g.emoji}
          type="button"
          className={`msg-reaction-chip ${g.hasOwn ? 'msg-reaction-chip--active' : ''}`}
          onClick={() => onToggle(g.emoji)}
        >
          <span className="msg-reaction-emoji">{g.emoji}</span>
          <span className="msg-reaction-count">{g.count}</span>
        </button>
      ))}
    </div>
  );
}

// ── Inline SVG Icons ─────────────────────────────────────────────────────────

function ReplyIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" className="msg-action-icon">
      <path d="M6 4L2 8l4 4" />
      <path d="M2 8h8a4 4 0 0 1 4 4v1" />
    </svg>
  );
}

function EmojiIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" className="msg-action-icon">
      <circle cx="8" cy="8" r="6" />
      <path d="M5.5 6.5v.5M10.5 6.5v.5" />
      <path d="M5.5 9.5a3 3 0 0 0 5 0" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" className="msg-action-icon">
      <path d="M11.5 2.5l2 2L5 13H3v-2l8.5-8.5z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" className="msg-action-icon">
      <path d="M3 4h10M6 4V3h4v1M5 4v8a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4" />
    </svg>
  );
}
