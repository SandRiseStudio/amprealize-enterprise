/**
 * MessageComposer — Text input with @mentions and typing indicator.
 *
 * Auto-resizing textarea, Enter to send, Shift+Enter newline,
 * @mention picker from conversation participants.
 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import {
  useConversation,
  useConversationParticipants,
  useModelReadiness,
  useProjectModels,
  useUserModels,
  useSendMessage,
} from '../../api/conversations';
import type { ConversationParticipant } from '../../lib/collab-client';

// ── Types ────────────────────────────────────────────────────────────────────

export interface MessageComposerProps {
  conversationId: string | null;
  currentUserId?: string;
  disabled?: boolean;
  placeholder?: string;
  onTyping?: (isTyping: boolean) => void;
  replyToMessageId?: string | null;
  onCancelReply?: () => void;
}

// ── Component ────────────────────────────────────────────────────────────────

export const MessageComposer = memo(function MessageComposer({
  conversationId,
  currentUserId,
  disabled = false,
  placeholder = 'Send a message...',
  onTyping,
  replyToMessageId,
  onCancelReply,
}: MessageComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [value, setValue] = useState('');
  const [mentionSearch, setMentionSearch] = useState<string | null>(null);
  const [mentionAnchor, setMentionAnchor] = useState<number | null>(null);
  const [selectedModelId, setSelectedModelId] = useState('');
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sendMessage = useSendMessage();
  const { data: conversation } = useConversation(conversationId ?? undefined);
  const { data: participantsData } = useConversationParticipants(conversationId ?? undefined);
  const projectId = conversation?.project_id ?? undefined;
  const globalUserId = projectId ? undefined : currentUserId ?? conversation?.created_by;
  const {
    data: projectModelAvailability,
    isError: projectModelsError,
    isLoading: projectModelsLoading,
  } = useProjectModels(projectId, {
    orgId: conversation?.org_id,
    userId: currentUserId ?? undefined,
  });
  const {
    data: userModelAvailability,
    isError: userModelsError,
    isLoading: userModelsLoading,
  } = useUserModels(globalUserId);
  const useReadinessGate = !!(conversationId && currentUserId);
  const {
    data: readiness,
    isLoading: readinessLoading,
    isError: readinessError,
  } = useModelReadiness({
    conversationId: conversationId ?? undefined,
    projectId,
    orgId: conversation?.org_id,
    userId: currentUserId,
    preferUser: !projectId,
    selectedModelId: selectedModelId || undefined,
    enabled: useReadinessGate,
  });
  const participants = participantsData?.items ?? [];
  const modelAvailability = projectModelAvailability ?? userModelAvailability;
  const availableModels =
    readiness?.models?.length ? readiness.models : (modelAvailability?.models ?? []);
  const modelsLoading = projectId ? projectModelsLoading : userModelsLoading;
  const modelsError = projectId ? projectModelsError : userModelsError;
  const selectedModel = availableModels.find((model) => model.model_id === selectedModelId);

  // ── Auto-resize textarea ─────────────────────────────────────────────────

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  useEffect(() => {
    if (availableModels.length === 0) {
      if (selectedModelId) setSelectedModelId('');
      return;
    }
    if (selectedModelId && availableModels.some((model) => model.model_id === selectedModelId)) return;
    const defaultModel = availableModels.find((model) => model.is_default) ?? availableModels[0];
    setSelectedModelId(defaultModel.model_id);
  }, [availableModels, selectedModelId]);

  // ── Typing indicator ─────────────────────────────────────────────────────

  const emitTyping = useCallback((isTyping: boolean) => {
    onTyping?.(isTyping);
  }, [onTyping]);

  const handleTypingDebounce = useCallback(() => {
    emitTyping(true);
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    typingTimeoutRef.current = setTimeout(() => {
      emitTyping(false);
    }, 2000);
  }, [emitTyping]);

  // ── Mention handling ─────────────────────────────────────────────────────

  const checkForMention = useCallback((text: string, cursorPos: number) => {
    // Find @ before cursor position
    const beforeCursor = text.slice(0, cursorPos);
    const lastAtIndex = beforeCursor.lastIndexOf('@');

    if (lastAtIndex === -1) {
      setMentionSearch(null);
      setMentionAnchor(null);
      return;
    }

    // Check if @ is at start or after whitespace
    if (lastAtIndex > 0 && !/\s/.test(beforeCursor[lastAtIndex - 1])) {
      setMentionSearch(null);
      setMentionAnchor(null);
      return;
    }

    const searchText = beforeCursor.slice(lastAtIndex + 1);
    // No whitespace in mention search
    if (/\s/.test(searchText)) {
      setMentionSearch(null);
      setMentionAnchor(null);
      return;
    }

    setMentionSearch(searchText.toLowerCase());
    setMentionAnchor(lastAtIndex);
  }, []);

  const filteredParticipants = participants.filter((p) => {
    if (mentionSearch === null) return false;
    return p.actor_id.toLowerCase().includes(mentionSearch);
  }).slice(0, 6);

  const insertMention = useCallback((participant: ConversationParticipant) => {
    if (mentionAnchor === null) return;
    const before = value.slice(0, mentionAnchor);
    const after = value.slice(textareaRef.current?.selectionStart ?? value.length);
    setValue(`${before}@${participant.actor_id} ${after}`);
    setMentionSearch(null);
    setMentionAnchor(null);
    textareaRef.current?.focus();
  }, [mentionAnchor, value]);

  // ── Input handling ───────────────────────────────────────────────────────

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setValue(newValue);
    handleTypingDebounce();
    checkForMention(newValue, e.target.selectionStart);
  }, [handleTypingDebounce, checkForMention]);

  const sendBlockedByReadiness =
    useReadinessGate && (readinessLoading || (readiness && !readiness.can_send));

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || !conversationId || disabled || sendMessage.isPending || sendBlockedByReadiness) return;

    // Clear typing indicator
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    emitTyping(false);

    // Resolve model at send time so we still attach llm_model_id if the user sends
    // before the default-model useEffect runs (otherwise the API never schedules a reply).
    const modelForMetadata =
      selectedModel ??
      (availableModels.length > 0
        ? (availableModels.find((m) => m.model_id === selectedModelId) ??
            availableModels.find((m) => m.is_default) ??
            availableModels[0])
        : undefined);

    if (!modelForMetadata) {
      return;
    }

    sendMessage.mutate({
      conversationId,
      content: trimmed,
      senderId: currentUserId,
      parentId: replyToMessageId ?? undefined,
      metadata: {
        llm_model_id: modelForMetadata.model_id,
        llm_provider: modelForMetadata.provider,
        credential_scope: modelForMetadata.credential_source,
      },
    });

    setValue('');
    onCancelReply?.();
    textareaRef.current?.focus();
  }, [
    value,
    conversationId,
    disabled,
    sendMessage,
    emitTyping,
    currentUserId,
    replyToMessageId,
    onCancelReply,
    selectedModel,
    availableModels,
    selectedModelId,
    sendBlockedByReadiness,
  ]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle mention picker navigation
    if (mentionSearch !== null && filteredParticipants.length > 0) {
      if (e.key === 'Escape') {
        e.preventDefault();
        setMentionSearch(null);
        setMentionAnchor(null);
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        insertMention(filteredParticipants[0]);
        return;
      }
    }

    // Enter to send, Shift+Enter for newline
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }

    // Cmd/Ctrl+Enter always sends
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  }, [mentionSearch, filteredParticipants, insertMention, handleSend]);

  // ── Render ───────────────────────────────────────────────────────────────

  const isDisabled = disabled || !conversationId;

  const readinessStatusText = (() => {
    if (!useReadinessGate) return null;
    if (readinessLoading) return 'Checking model readiness…';
    if (readinessError) return 'Could not verify model readiness.';
    if (readiness && !readiness.can_send) {
      return readiness.detail || `Chat setup required (${readiness.state}).`;
    }
    return null;
  })();

  return (
    <div className="msg-composer">
      {/* Reply banner */}
      {replyToMessageId && (
        <div className="msg-composer-reply-banner">
          <span className="msg-composer-reply-label">Replying to message</span>
          <button
            type="button"
            className="msg-composer-reply-cancel"
            onClick={onCancelReply}
            aria-label="Cancel reply"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      )}

      <div className="msg-composer-input-row">
        <textarea
          ref={textareaRef}
          className="msg-composer-textarea"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isDisabled}
          rows={1}
          aria-label="Message input"
        />
        <button
          type="button"
          className="msg-composer-send-btn pressable"
          onClick={handleSend}
          disabled={
            isDisabled || !value.trim() || sendMessage.isPending || sendBlockedByReadiness
          }
          aria-label="Send message"
          data-haptic="light"
        >
          {sendMessage.isPending ? (
            <span className="msg-composer-sending-spinner" />
          ) : (
            <SendIcon />
          )}
        </button>
      </div>

      {(availableModels.length > 0 ||
        modelsLoading ||
        modelsError ||
        modelAvailability ||
        readinessLoading ||
        readinessError ||
        readinessStatusText) && (
        <div className="msg-composer-model-row">
          <label className="msg-composer-model-label" htmlFor="msg-composer-model-select">
            Model
          </label>
          {availableModels.length > 0 ? (
            <select
              id="msg-composer-model-select"
              className="msg-composer-model-select"
              value={selectedModelId}
              disabled={isDisabled || sendMessage.isPending || readinessLoading}
              onChange={(event) => setSelectedModelId(event.target.value)}
              aria-label="Choose chat model"
            >
              {availableModels.map((model) => (
                <option key={model.model_id} value={model.model_id}>
                  {model.display_name} ({model.provider}/{model.credential_source})
                </option>
              ))}
            </select>
          ) : (
            <span className="msg-composer-model-status">
              {readinessStatusText
                ? readinessStatusText
                : modelsLoading || readinessLoading
                  ? 'Loading available models…'
                  : modelsError || readinessError
                    ? 'Could not load models for this chat.'
                    : 'No models available. Configure a platform API key or BYOK for this scope.'}
            </span>
          )}
        </div>
      )}

      {/* Mention picker */}
      {mentionSearch !== null && filteredParticipants.length > 0 && (
        <div className="msg-mention-picker" role="listbox" aria-label="Mention suggestions">
          {filteredParticipants.map((p, idx) => (
            <button
              key={p.actor_id}
              type="button"
              className={`msg-mention-option ${idx === 0 ? 'msg-mention-option--highlighted' : ''}`}
              onClick={() => insertMention(p)}
              role="option"
              aria-selected={idx === 0}
            >
              <span className="msg-mention-avatar">
                {p.actor_id.slice(0, 2).toUpperCase()}
              </span>
              <span className="msg-mention-name">{p.actor_id}</span>
            </button>
          ))}
        </div>
      )}

      {/* Keyboard hint */}
      {!isDisabled && (
        <div className="msg-composer-hint">
          <kbd>Enter</kbd> to send, <kbd>Shift</kbd>+<kbd>Enter</kbd> for newline
        </div>
      )}
    </div>
  );
});

// ── Send Icon ────────────────────────────────────────────────────────────────

function SendIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" className="msg-send-icon">
      <path d="M14 2L7 9" />
      <path d="M14 2L9 14l-2-5-5-2z" />
    </svg>
  );
}
