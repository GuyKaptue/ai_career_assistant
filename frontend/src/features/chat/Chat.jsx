import React from 'react';
import ChatLayout from '../../components/ChatLayout';

/**
 * Chat Component - Main entry point for chat functionality
 * Uses the professional Claude-inspired layout.
 *
 * All session/completion state is owned by useChat inside
 * ChatLayout, which talks to the real /api/v1/chat endpoints.
 */
export default function Chat({ session }) {
  return <ChatLayout session={session} />;
}