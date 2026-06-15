import { useEffect, useRef, useState } from 'react';

interface WSMessage {
  type: string;
  data: unknown;
}

// Auto-reconnecting WebSocket hook. Returns the latest parsed message.
export function useWebSocket(path = '/ws'): WSMessage | null {
  const [message, setMessage] = useState<WSMessage | null>(null);
  const retry = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout>;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${proto}://${location.host}${path}`);
      ws.onopen = () => (retry.current = 0);
      ws.onmessage = (ev) => {
        try {
          setMessage(JSON.parse(ev.data));
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (closed) return;
        const delay = Math.min(1000 * 2 ** retry.current, 15000);
        retry.current += 1;
        timer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [path]);

  return message;
}
