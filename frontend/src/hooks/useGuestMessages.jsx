import { useState, useEffect, useCallback } from 'react';

const GUEST_MESSAGE_LIMIT = 5;
const STORAGE_KEY = 'aca-guest-messages';

/**
 * Hook to manage guest message count with localStorage persistence
 * Limits guests to 5 messages before requiring login
 */
export function useGuestMessages() {
  const [count, setCount] = useState(0);
  const [hasReachedLimit, setHasReachedLimit] = useState(false);

  // Load count from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY);
      const initialCount = stored ? parseInt(stored, 10) : 0;
      setCount(initialCount);
      setHasReachedLimit(initialCount >= GUEST_MESSAGE_LIMIT);
    }
  }, []);

  // Persist count to localStorage
  useEffect(() => {
    try {
      if (count > 0) {
        localStorage.setItem(STORAGE_KEY, count.toString());
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
      setHasReachedLimit(count >= GUEST_MESSAGE_LIMIT);
    } catch {
      // Storage may be unavailable (private mode); ignore.
    }
  }, [count]);

  /**
   * Increment message count and check if limit reached
   * Returns true if message was counted, false if limit reached
   */
  const increment = useCallback(() => {
    if (hasReachedLimit) {
      return false;
    }
    setCount((prev) => prev + 1);
    return true;
  }, [hasReachedLimit]);

  /**
   * Reset message count (call this on successful login)
   */
  const reset = useCallback(() => {
    setCount(0);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Storage may be unavailable
    }
  }, []);

  /**
   * Get remaining messages
   */
  const remaining = GUEST_MESSAGE_LIMIT - count;

  return {
    count,
    remaining,
    hasReachedLimit,
    increment,
    reset,
    limit: GUEST_MESSAGE_LIMIT,
  };
}

/**
 * Clear guest message count (utility function)
 */
export function clearGuestMessages() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage may be unavailable
  }
}
