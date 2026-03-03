/**
 * Custom React hook for managing a LiveKit voice session.
 * Handles room connection, audio, data channel, and transcription.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { Room, RoomEvent, ConnectionState, Track } from 'livekit-client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export function useVoiceSession() {
  // State
  const [connectionState, setConnectionState] = useState('disconnected'); // disconnected | connecting | connected
  const [messages, setMessages] = useState([]);
  const [isMuted, setIsMuted] = useState(false);
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [error, setError] = useState(null);

  // Refs
  const roomRef = useRef(null);
  const seenIdsRef = useRef(new Set());
  const audioElementsRef = useRef([]);

  /**
   * Add a message to the chat, with deduplication.
   */
  const addMessage = useCallback((speaker, text, id) => {
    const key = id || `${speaker}-${Date.now()}-${text.slice(0, 20)}`;
    if (seenIdsRef.current.has(key)) return;
    seenIdsRef.current.add(key);

    setMessages(prev => [
      ...prev,
      {
        id: key,
        speaker,
        text,
        timestamp: new Date(),
      },
    ]);
    setIsAgentThinking(false);
  }, []);

  /**
   * Start a new voice session.
   */
  const connect = useCallback(async (customerName = 'Customer') => {
    try {
      setConnectionState('connecting');
      setError(null);
      setMessages([]);
      seenIdsRef.current.clear();

      // 1. Create session via backend API
      const res = await fetch(`${BACKEND_URL}/api/sessions/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_name: customerName }),
      });

      if (!res.ok) throw new Error(`Failed to create session: ${res.statusText}`);
      const data = await res.json();
      setSessionId(data.session_id);

      // 2. Create LiveKit room
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      roomRef.current = room;

      // 3. Set up event handlers

      // Connection state changes
      room.on(RoomEvent.ConnectionStateChanged, (state) => {
        if (state === ConnectionState.Connected) {
          setConnectionState('connected');
        } else if (state === ConnectionState.Disconnected) {
          setConnectionState('disconnected');
        }
      });

      // Agent audio playback
      room.on(RoomEvent.TrackSubscribed, (track, pub, participant) => {
        if (track.kind === Track.Kind.Audio) {
          const audio = document.createElement('audio');
          audio.autoplay = true;
          audio.id = `audio-${participant.identity}`;
          track.attach(audio);
          audioElementsRef.current.push(audio);
        }
      });

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach();
      });

      // Data channel: transcripts + agent status
      room.on(RoomEvent.DataReceived, (payload) => {
        try {
          const data = JSON.parse(new TextDecoder().decode(payload));
          if (data.type === 'transcript') {
            addMessage(data.speaker, data.text, data.timestamp);
          } else if (data.type === 'agent_thinking') {
            setIsAgentThinking(true);
          }
        } catch (e) {
          console.warn('Failed to parse data message:', e);
        }
      });

      // LiveKit built-in transcription events (if available)
      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        segments.forEach(seg => {
          if (seg.final) {
            const speaker = participant?.identity?.includes('agent') ? 'agent' : 'user';
            addMessage(speaker, seg.text, seg.id);
          }
        });
      });

      // Participant disconnect
      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        if (participant.identity?.includes('agent')) {
          addMessage('system', 'The support agent has disconnected.', `sys-${Date.now()}`);
          setConnectionState('disconnected');
        }
      });

      // 4. Connect to LiveKit
      const livekitUrl = data.livekit_url.replace('ws://', 'ws://').replace('wss://', 'wss://');
      await room.connect(livekitUrl, data.livekit_token);

      // 5. Enable microphone
      await room.localParticipant.setMicrophoneEnabled(true);

      setConnectionState('connected');
    } catch (err) {
      console.error('Connection error:', err);
      setError(err.message);
      setConnectionState('disconnected');
    }
  }, [addMessage]);

  /**
   * Disconnect from the session.
   */
  const disconnect = useCallback(async () => {
    try {
      // End session via API
      if (sessionId) {
        await fetch(`${BACKEND_URL}/api/sessions/end`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId }),
        });
      }
    } catch (e) {
      console.warn('Error ending session:', e);
    }

    // Disconnect room
    if (roomRef.current) {
      roomRef.current.disconnect();
      roomRef.current = null;
    }

    // Cleanup audio elements
    audioElementsRef.current.forEach(el => el.remove());
    audioElementsRef.current = [];

    setConnectionState('disconnected');
    setSessionId(null);
  }, [sessionId]);

  /**
   * Toggle microphone mute.
   */
  const toggleMute = useCallback(async () => {
    if (roomRef.current?.localParticipant) {
      const newMuted = !isMuted;
      await roomRef.current.localParticipant.setMicrophoneEnabled(!newMuted);
      setIsMuted(newMuted);
    }
  }, [isMuted]);

  /**
   * Send a text message through the data channel.
   */
  const sendTextMessage = useCallback(async (text) => {
    if (!roomRef.current?.localParticipant || !text.trim()) return;

    const payload = JSON.stringify({
      type: 'text_message',
      text: text.trim(),
    });

    await roomRef.current.localParticipant.publishData(
      new TextEncoder().encode(payload),
      { reliable: true }
    );

    // Add user message locally
    addMessage('user', text.trim(), `user-text-${Date.now()}`);
  }, [addMessage]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect();
      }
      audioElementsRef.current.forEach(el => el.remove());
    };
  }, []);

  return {
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
  };
}
