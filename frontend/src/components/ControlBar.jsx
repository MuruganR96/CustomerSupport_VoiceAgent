import React, { useState } from 'react';
import { Mic, MicOff, PhoneOff, Send } from 'lucide-react';

/**
 * Bottom control bar with mute, text input, and end call.
 */
export default function ControlBar({
  connectionState,
  isMuted,
  onToggleMute,
  onSendText,
  onEndCall,
}) {
  const [textInput, setTextInput] = useState('');
  const isConnected = connectionState === 'connected';

  const handleSend = () => {
    if (textInput.trim() && isConnected) {
      onSendText(textInput.trim());
      setTextInput('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3">
        {/* Mute button */}
        <button
          onClick={onToggleMute}
          disabled={!isConnected}
          className={`p-2.5 rounded-full transition-colors ${
            isMuted
              ? 'bg-red-100 text-red-600 hover:bg-red-200'
              : 'bg-indigo-100 text-indigo-600 hover:bg-indigo-200'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
          title={isMuted ? 'Unmute' : 'Mute'}
        >
          {isMuted ? <MicOff size={20} /> : <Mic size={20} />}
        </button>

        {/* Text input */}
        <div className="flex-1 relative">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!isConnected}
            placeholder={isConnected ? 'Type a message...' : 'Connect to start'}
            className="w-full px-4 py-2.5 bg-gray-100 border border-gray-200 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-transparent disabled:opacity-50"
          />
          {textInput.trim() && (
            <button
              onClick={handleSend}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-indigo-600 hover:text-indigo-700"
            >
              <Send size={16} />
            </button>
          )}
        </div>

        {/* End call */}
        <button
          onClick={onEndCall}
          disabled={!isConnected}
          className="p-2.5 rounded-full bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          title="End call"
        >
          <PhoneOff size={20} />
        </button>
      </div>
    </div>
  );
}
