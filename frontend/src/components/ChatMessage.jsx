/**
 * Single chat message bubble — agent, user, or system.
 * Uses vm- CSS classes matching the VoiceMeeting design system.
 */
export default function ChatMessage({ message }) {
  const { speaker, text, isFinal = true } = message;

  const isAgent = speaker === 'agent';
  const isSystem = speaker === 'system';

  if (isSystem) {
    return (
      <div className={`vm-message vm-message-system`}>
        <div className="vm-message-text">{text}</div>
      </div>
    );
  }

  const pendingClass = !isFinal ? ' vm-message-pending' : '';

  if (isAgent) {
    return (
      <div className={`vm-message vm-message-agent${pendingClass}`}>
        <div className="vm-message-text">{text}</div>
        {isFinal && (
          <div className="vm-message-actions">
            <button
              className="vm-action-btn"
              title="Copy"
              onClick={() => navigator.clipboard.writeText(text)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            </button>
            <button className="vm-action-btn" title="Good response">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
              </svg>
            </button>
            <button className="vm-action-btn" title="Poor response">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"></path>
              </svg>
            </button>
          </div>
        )}
      </div>
    );
  }

  // User (candidate) message
  return (
    <div className={`vm-message vm-message-candidate${pendingClass}`}>
      <div className="vm-message-bubble">
        <div className="vm-message-text">{text}</div>
      </div>
    </div>
  );
}
