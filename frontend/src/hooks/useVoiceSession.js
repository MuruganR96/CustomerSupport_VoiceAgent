/**
 * Custom React hook for managing a LiveKit voice session.
 * Handles room connection, audio, data channel, transcription accumulation,
 * and agent state tracking.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { Room, RoomEvent, ConnectionState, Track } from 'livekit-client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const LIVEKIT_URL = import.meta.env.VITE_LIVEKIT_URL || 'ws://localhost:7880';

export function useVoiceSession() {
  // State
  const [connectionState, setConnectionState] = useState('disconnected');
  const [messages, setMessages] = useState([]);
  const [isMuted, setIsMuted] = useState(false);
  const [agentState, setAgentState] = useState('idle'); // idle | listening | thinking | speaking
  const [sessionId, setSessionId] = useState(null);
  const [error, setError] = useState(null);

  // Refs
  const roomRef = useRef(null);
  const audioElementsRef = useRef([]);

  /**
   * Upsert a transcript message. Non-final segments update in-place,
   * final segments lock the text. This creates the "accumulation" effect.
   */
  const upsertTranscript = useCallback((speaker, text, id, isFinal) => {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === id);
      if (idx !== -1) {
        // Update existing message in-place
        const updated = [...prev];
        updated[idx] = { ...updated[idx], text, isFinal };
        return updated;
      }
      // New message
      return [
        ...prev,
        { id, speaker, text, timestamp: new Date(), isFinal },
      ];
    });
  }, []);

  /**
   * Add a one-shot message (system messages, typed text).
   */
  const addMessage = useCallback((speaker, text, id) => {
    const key = id || `${speaker}-${Date.now()}-${text.slice(0, 20)}`;
    setMessages(prev => {
      if (prev.some(m => m.id === key)) return prev;
      return [
        ...prev,
        { id: key, speaker, text, timestamp: new Date(), isFinal: true },
      ];
    });
  }, []);

  /**
   * Start a new voice session.
   */
  const connect = useCallback(async (customerName = 'Customer') => {
    try {
      setConnectionState('connecting');
      setError(null);
      setMessages([]);
      setAgentState('idle');

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

      // Agent audio track — subscribe for playback
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

      // Agent state — listen for participant attribute changes
      room.on(RoomEvent.ParticipantAttributesChanged, (changedAttrs, participant) => {
        if (participant.identity?.includes('agent')) {
          const state = participant.attributes?.['lk.agent.state'];
          if (state) {
            setAgentState(state);
          }
        }
      });

      // Data channel: transcripts + agent status
      room.on(RoomEvent.DataReceived, (payload) => {
        try {
          const data = JSON.parse(new TextDecoder().decode(payload));
          if (data.type === 'transcript') {
            addMessage(data.speaker, data.text, data.timestamp);
          }
        } catch (e) {
          console.warn('Failed to parse data message:', e);
        }
      });

      // Transcription events — accumulate word by word
      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        const speaker = participant?.identity?.includes('agent') ? 'agent' : 'user';
        segments.forEach(seg => {
          upsertTranscript(speaker, seg.text, seg.id, seg.final);
        });
      });

      // Participant disconnect
      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        if (participant.identity?.includes('agent')) {
          addMessage('system', 'The support agent has disconnected.', `sys-${Date.now()}`);
          setConnectionState('disconnected');
          setAgentState('idle');
        }
      });

      // 4. Connect to LiveKit
      await room.connect(LIVEKIT_URL, data.livekit_token);

      // 5. Enable microphone
      await room.localParticipant.setMicrophoneEnabled(true);

      setConnectionState('connected');
    } catch (err) {
      console.error('Connection error:', err);
      setError(err.message);
      setConnectionState('disconnected');
    }
  }, [addMessage, upsertTranscript]);

  /**
   * Disconnect from the session.
   */
  const disconnect = useCallback(async () => {
    try {
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

    if (roomRef.current) {
      roomRef.current.disconnect();
      roomRef.current = null;
    }

    audioElementsRef.current.forEach(el => el.remove());
    audioElementsRef.current = [];

    setConnectionState('disconnected');
    setSessionId(null);
    setAgentState('idle');
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
    agentState,
    sessionId,
    error,
    connect,
    disconnect,
    toggleMute,
    sendTextMessage,
  };
}
