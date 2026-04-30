import { memo, useCallback, useMemo, useState } from 'react';
import { ConversationScope, type Conversation } from '../../lib/collab-client';
import { useConversations, useCreateConversation, useEnsureGlobalHomeConversation } from '../../api/conversations';
import { UnifiedConversationWindow, type UnifiedConversationInitialTarget } from './UnifiedConversationWindow';
import './AmprealizeChatDock.css';

type ChatContextKind = 'global' | 'project';

interface OpenChatState {
  contextKind: ChatContextKind;
  initialTarget: UnifiedConversationInitialTarget;
  key: number;
}

export interface AmprealizeChatDockProps {
  projectId?: string | null;
  orgId?: string | null;
  projectName?: string | null;
  currentUserId?: string;
}

function ChatDockIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4.2 14.7A7 7 0 1117 10.8c0 3.4-3.1 6.2-7 6.2a8 8 0 01-2.7-.5L3 17.2l1.2-2.5z" />
      <path d="M7 9.5h6M7 12h4" />
    </svg>
  );
}

function getProjectRoom(items: Conversation[]): Conversation | null {
  return (
    items.find((item) => item.scope === ConversationScope.ProjectRoom || item.scope === ConversationScope.ProjectSpace) ?? null
  );
}

export const AmprealizeChatDock = memo(function AmprealizeChatDock({
  projectId,
  orgId,
  projectName,
  currentUserId,
}: AmprealizeChatDockProps) {
  const [openChat, setOpenChat] = useState<OpenChatState | null>(null);
  const ensureGlobalHome = useEnsureGlobalHomeConversation();
  const createConversation = useCreateConversation();
  const projectConversations = useConversations({ projectId, enabled: !!projectId });

  const activeContextKind: ChatContextKind = projectId ? 'project' : 'global';
  const contextLabel = useMemo(() => {
    if (activeContextKind === 'project') {
      return projectName ? `${projectName} chat` : 'Project chat';
    }
    return 'Global chat';
  }, [activeContextKind, projectName]);

  const openGlobalChat = useCallback(() => {
    setOpenChat({
      contextKind: 'global',
      initialTarget: { mode: 'none' },
      key: Date.now(),
    });
    ensureGlobalHome.mutate(undefined, {
      onSuccess: (conversation) => {
        setOpenChat({
          contextKind: 'global',
          initialTarget: { mode: 'conversation', conversationId: conversation.id },
          key: Date.now(),
        });
      },
    });
  }, [ensureGlobalHome]);

  const openProjectChat = useCallback(() => {
    if (!projectId) {
      openGlobalChat();
      return;
    }

    const existingRoom = getProjectRoom(projectConversations.data?.items ?? []);
    if (existingRoom) {
      setOpenChat({
        contextKind: 'project',
        initialTarget: { mode: 'conversation', conversationId: existingRoom.id },
        key: Date.now(),
      });
      return;
    }

    createConversation.mutate(
      { projectId, scope: ConversationScope.ProjectRoom, title: 'Project room' },
      {
        onSuccess: (conversation) => {
          setOpenChat({
            contextKind: 'project',
            initialTarget: { mode: 'conversation', conversationId: conversation.id },
            key: Date.now(),
          });
        },
      },
    );
  }, [createConversation, openGlobalChat, projectConversations.data?.items, projectId]);

  const handleDockOpen = activeContextKind === 'project' ? openProjectChat : openGlobalChat;
  const isBusy = ensureGlobalHome.isPending || createConversation.isPending || projectConversations.isFetching;

  return (
    <div className="amp-chat-root" aria-live="polite">
      {openChat && (
        <div className="amp-chat-window-anchor">
          <UnifiedConversationWindow
            projectId={openChat.contextKind === 'project' ? projectId : null}
            orgId={orgId}
            currentUserId={currentUserId}
            contextKind={openChat.contextKind}
            contextLabel={openChat.contextKind === 'project' ? contextLabel : 'Global chat'}
            initialTarget={openChat.initialTarget}
            initialTargetKey={openChat.key}
            onClose={() => setOpenChat(null)}
          />
        </div>
      )}

      <button
        type="button"
        className={`amp-chat-dock pressable amp-chat-dock--${activeContextKind}`}
        onClick={handleDockOpen}
        disabled={isBusy}
        aria-label={`Open ${contextLabel}`}
        data-haptic="medium"
      >
        <span className="amp-chat-dock__icon"><ChatDockIcon /></span>
        <span className="amp-chat-dock__copy">
          <span className="amp-chat-dock__eyebrow">Amprealize Chat</span>
          <span className="amp-chat-dock__label">{contextLabel}</span>
        </span>
      </button>
    </div>
  );
});
