import { useRef, useEffect, useState } from 'react';
import { useVoiceSession } from './hooks/useVoiceSession';
import ChatMessage from './components/ChatMessage';
import './styles/index.css';

export default function App() {
  const {
    connectionState,
    messages,
    isMuted,
    agentState,
    sessionId,
    error,
    connect,
    disconnect,
    toggleMute,
    sendTextMessage,
  } = useVoiceSession();

  const [customerName, setCustomerName] = useState('');
  const [inputText, setInputText] = useState('');
  const [callDuration, setCallDuration] = useState(0);
  const [ended, setEnded] = useState(false);

  const chatAreaRef = useRef(null);
  const timerRef = useRef(null);

  const isDisconnected = connectionState === 'disconnected';
  const isConnecting = connectionState === 'connecting';
  const isConnected = connectionState === 'connected';

  // Format duration as MM:SS
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Auto-scroll chat to bottom on new messages or typing indicator
  useEffect(() => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight;
    }
  }, [messages, agentState]);

  // Call duration timer
  useEffect(() => {
    if (isConnected && !ended) {
      timerRef.current = setInterval(() => {
        setCallDuration(prev => prev + 1);
      }, 1000);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isConnected, ended]);

  // Detect disconnect after being connected (call ended)
  useEffect(() => {
    if (isDisconnected && callDuration > 0) {
      setEnded(true);
    }
  }, [isDisconnected, callDuration]);

  const handleConnect = () => {
    connect(customerName || 'Customer');
  };

  const handleEndCall = async () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    await disconnect();
    setEnded(true);
  };

  const handleSendText = () => {
    if (!inputText.trim()) return;
    sendTextMessage(inputText.trim());
    setInputText('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendText();
    }
  };

  // ── Ended State ───────────────────────────────────────────────────
  if (ended) {
    return (
      <div className="vm-container">
        <div className="vm-header">
          <div className="vm-header-left"></div>
          <h1 className="vm-header-title">Customer Support</h1>
          <div className="vm-header-right"></div>
        </div>
        <div className="vm-ended">
          <div className="vm-ended-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </div>
          <h2 className="vm-ended-title">Call Complete</h2>
          <p className="vm-ended-message">
            Thank you for contacting us! We hope we were able to help. Don&apos;t hesitate to reach out again anytime.
          </p>
          {callDuration > 0 && (
            <p className="vm-duration">Duration: {formatDuration(callDuration)}</p>
          )}
        </div>
      </div>
    );
  }

  // ── Connect Screen (Pre-join) ─────────────────────────────────────
  if (isDisconnected || isConnecting) {
    return (
      <div className="vm-container">
        <div className="vm-header">
          <div className="vm-header-left"></div>
          <h1 className="vm-header-title">Customer Support</h1>
          <div className="vm-header-right"></div>
        </div>

        <div className="vm-prejoin">
          <h2 className="vm-prejoin-title">Start a Support Call</h2>
          <p className="vm-prejoin-subtitle">
            Connect with our AI voice assistant for instant help with your questions
          </p>

          {error && (
            <div className="vm-error-banner">{error}</div>
          )}

          <input
            type="text"
            className="vm-name-input"
            value={customerName}
            onChange={(e) => setCustomerName(e.target.value)}
            placeholder="Your name (optional)"
            onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
          />

          <button
            className="vm-join-btn"
            onClick={handleConnect}
            disabled={isConnecting}
          >
            {isConnecting ? (
              <>
                <span className="vm-btn-spinner"></span>
                Connecting...
              </>
            ) : (
              'Connect Now'
            )}
          </button>
        </div>
      </div>
    );
  }

  // ── Active Call — Chat Interface ──────────────────────────────────
  const showTypingIndicator = agentState === 'thinking';
  const showSpeakingPill = isConnected && (agentState === 'speaking' || agentState === 'listening');
  const speakingPillText = agentState === 'speaking' ? 'Agent is speaking...' : 'Listening...';

  return (
    <div className="vm-container">
      {/* Header */}
      <div className="vm-header">
        <div className="vm-header-left">
          {isConnected && (
            <span className="vm-connection-dot connected"></span>
          )}
          <span className="vm-timer">{formatDuration(callDuration)}</span>
        </div>
        <h1 className="vm-header-title">Customer Support</h1>
        <div className="vm-header-right">
          <span className="vm-menu-icon">&#8942;</span>
        </div>
      </div>

      {/* Chat Area */}
      <div className="vm-chat-area" ref={chatAreaRef}>
        {messages.length === 0 && !showTypingIndicator && (
          <div className="vm-chat-empty">
            <p>The conversation will begin shortly...</p>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {/* Typing indicator */}
        {showTypingIndicator && (
          <div className="vm-message vm-message-agent">
            <div className="vm-typing-indicator">
              <span className="vm-typing-dot"></span>
              <span className="vm-typing-dot"></span>
              <span className="vm-typing-dot"></span>
            </div>
          </div>
        )}
      </div>

      {/* Speaking indicator pill */}
      {showSpeakingPill && (
        <div className="vm-speaking-indicator">
          {speakingPillText}
        </div>
      )}

      {/* Input Bar */}
      <div className="vm-input-bar">
        <input
          type="text"
          className="vm-input-field"
          placeholder="Type a message..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        <button
          className={`vm-mic-btn ${!isMuted ? 'listening' : 'muted'}`}
          onClick={toggleMute}
          title={isMuted ? 'Unmute' : 'Mute'}
        >
          {isMuted ? (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="1" y1="1" x2="23" y2="23"></line>
              <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"></path>
              <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"></path>
              <line x1="12" y1="19" x2="12" y2="23"></line>
              <line x1="8" y1="23" x2="16" y2="23"></line>
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
              <line x1="12" y1="19" x2="12" y2="23"></line>
              <line x1="8" y1="23" x2="16" y2="23"></line>
            </svg>
          )}
        </button>

        <button className="vm-end-btn" onClick={handleEndCall}>
          End
        </button>
      </div>
    </div>
  );
}
