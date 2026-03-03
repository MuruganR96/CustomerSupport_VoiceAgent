import React from 'react';
import { Headphones, User, AlertCircle } from 'lucide-react';

/**
 * Single chat message bubble — agent, user, or system.
 */
export default function ChatMessage({ message }) {
  const { speaker, text, timestamp } = message;

  const isAgent = speaker === 'agent';
  const isSystem = speaker === 'system';

  const time = timestamp
    ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  if (isSystem) {
    return (
      <div className="flex justify-center my-3">
        <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-200 rounded-full text-amber-700 text-sm">
          <AlertCircle size={14} />
          <span>{text}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 mb-4 ${isAgent ? 'justify-start' : 'justify-end'}`}>
      {/* Agent avatar */}
      {isAgent && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center">
          <Headphones size={16} className="text-indigo-600" />
        </div>
      )}

      {/* Message bubble */}
      <div className={`max-w-[75%] ${isAgent ? '' : 'order-first'}`}>
        <div
          className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
            isAgent
              ? 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm'
              : 'bg-indigo-600 text-white rounded-tr-sm'
          }`}
        >
          {text}
        </div>
        <div className={`mt-1 text-xs text-gray-400 ${isAgent ? 'text-left' : 'text-right'}`}>
          {time}
        </div>
      </div>

      {/* User avatar */}
      {!isAgent && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
          <User size={16} className="text-gray-600" />
        </div>
      )}
    </div>
  );
}
