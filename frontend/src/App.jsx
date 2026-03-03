import React, { useRef, useEffect, useState } from 'react';
import { Phone, Headphones, Wifi, WifiOff } from 'lucide-react';
import { useVoiceSession } from './hooks/useVoiceSession';
import ChatMessage from './components/ChatMessage';
import TypingIndicator from './components/TypingIndicator';
import ControlBar from './components/ControlBar';

export default function App() {
  const {
    connectionState,
    messages,
    isMuted,
    isAgentThinking,
    sessionId,
    error,
    connect,
    disconnect,
    toggleMute,
    sendTextMessage,
  } = useVoiceSession();

  const [customerName, setCustomerName] = useState('');
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAgentThinking]);

  const handleConnect = () => {
    connect(customerName || 'Customer');
  };

  const isDisconnected = connectionState === 'disconnected';
  const isConnecting = connectionState === 'connecting';
  const isConnected = connectionState === 'connected';

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* ─── Header ─────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center">
            <Headphones size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Customer Support</h1>
            <p className="text-xs text-gray-500">Voice Agent powered by AI</p>
          </div>
        </div>

        {/* Connection status */}
        <div className="flex items-center gap-2">
          {isConnected && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
              <div className="relative">
                <div className="w-2 h-2 bg-green-500 rounded-full" />
                <div className="absolute inset-0 w-2 h-2 bg-green-400 rounded-full animate-pulse-ring" />
              </div>
              <span className="text-xs font-medium text-green-700">Connected</span>
            </div>
          )}
          {isConnecting && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-full">
              <Wifi size={14} className="text-amber-600 animate-pulse" />
              <span className="text-xs font-medium text-amber-700">Connecting...</span>
            </div>
          )}
          {isDisconnected && !error && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 rounded-full">
              <WifiOff size={14} className="text-gray-400" />
              <span className="text-xs font-medium text-gray-500">Disconnected</span>
            </div>
          )}
        </div>
      </header>

      {/* ─── Main Content ───────────────────────────────────────────────── */}
      <main className="flex-1 overflow-hidden flex flex-col">
        {isDisconnected ? (
          /* ─── Connect Screen ────────────────────────────────────────── */
          <div className="flex-1 flex items-center justify-center p-6">
            <div className="w-full max-w-md text-center">
              <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-indigo-100 flex items-center justify-center">
                <Phone size={32} className="text-indigo-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                Start a Support Call
              </h2>
              <p className="text-gray-500 mb-8">
                Connect with our AI voice assistant for instant help
              </p>

              {error && (
                <div className="mb-6 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                  {error}
                </div>
              )}

              <div className="mb-4">
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  placeholder="Your name (optional)"
                  className="w-full px-4 py-3 bg-white border border-gray-300 rounded-xl text-center focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-transparent"
                  onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
                />
              </div>

              <button
                onClick={handleConnect}
                disabled={isConnecting}
                className="w-full py-3.5 bg-indigo-600 text-white font-medium rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-wait flex items-center justify-center gap-2"
              >
                {isConnecting ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Connecting...
                  </>
                ) : (
                  <>
                    <Phone size={18} />
                    Connect Now
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          /* ─── Chat Area ─────────────────────────────────────────────── */
          <>
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {messages.length === 0 && !isAgentThinking && (
                <div className="text-center text-gray-400 mt-12">
                  <Headphones size={40} className="mx-auto mb-3 opacity-50" />
                  <p className="text-sm">Waiting for the agent to start...</p>
                </div>
              )}

              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {isAgentThinking && <TypingIndicator />}

              <div ref={messagesEndRef} />
            </div>

            {/* ─── Control Bar ──────────────────────────────────────────── */}
            <ControlBar
              connectionState={connectionState}
              isMuted={isMuted}
              onToggleMute={toggleMute}
              onSendText={sendTextMessage}
              onEndCall={disconnect}
            />
          </>
        )}
      </main>
    </div>
  );
}
