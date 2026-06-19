import { useState, useEffect, useRef, useCallback } from 'react';
import { startWhatsAppSession, stopWhatsAppSession } from '../lib/api/agent';
import { API_BASE_URL } from '../utils/api/api';

export type SessionState = 'idle' | 'initializing' | 'qr_ready' | 'connecting' | 'connected' | 'disconnected' | 'error';

export function useWhatsAppSession(agentId: string) {
  const [state, setState] = useState<SessionState>('idle');
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [phoneNumber, setPhoneNumber] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const startSession = useCallback(async () => {
    setState('initializing');
    setError(null);
    setQrCode(null);

    try {
      // 1. Call POST /start FIRST to initialize session and get session_id
      const response = await startWhatsAppSession(agentId);
      const sessionId = response.session_id || agentId;

      // 2. Open WebSocket using the session_id from response
      // Construct WebSocket URL from API_BASE_URL
      const baseURL = API_BASE_URL || window.location.origin;
      const wsProtocol = baseURL.startsWith('https') ? 'wss' : 'ws';
      
      let wsURL = "";
      if (baseURL.startsWith('http')) {
         const url = new URL(baseURL);
         wsURL = `${wsProtocol}://${url.host}/api/v1/whatsapp-session/ws/${sessionId}`;
      } else {
         // Fallback for relative paths
         wsURL = `${wsProtocol}://${window.location.host}/api/v1/whatsapp-session/ws/${sessionId}`;
      }

      console.log(`Connecting to WhatsApp WebSocket: ${wsURL}`);
      const ws = new WebSocket(wsURL);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          
          if (payload.event === "qr") {
            setState('qr_ready');
            let qrData = payload.data.qr_base64;
            if (qrData && !qrData.startsWith("data:image")) {
              qrData = "data:image/png;base64," + qrData;
            }
            setQrCode(qrData);
          } else if (payload.event === "status") {
            const currentState = payload.data.state;
            
            // IMPORTANT FIX: Prevent generic 'connecting' status from overwriting a visible QR code.
            // In Evolution API/Baileys, status is 'connecting' even when QR is ready for scanning.
            if (currentState === "connecting") {
              setState((prev) => (prev === 'qr_ready' ? prev : 'connecting'));
            } else if (currentState === "connected") {
              setState('connected');
              setQrCode(null);
              if (payload.data.phone_number) {
                 setPhoneNumber(payload.data.phone_number);
              }
            } else if (currentState === "disconnected") {
              setState('disconnected');
              setQrCode(null);
            } else if (currentState === "qr_ready") {
               setState('qr_ready');
            } else {
               // Map other backend states if any
               setState(currentState);
            }
          } else if (payload.event === "error") {
             setState('error');
             setError(payload.data.message || "An unknown error occurred.");
          }
        } catch (err) {
          console.error("Error parsing WS message:", err);
        }
      };

      ws.onerror = (event) => {
        console.error("WebSocket error:", event);
        setState('error');
        setError("Failed to connect to the WhatsApp update server.");
      };

      ws.onclose = () => {
        setState((prev) => {
            if (prev !== 'idle' && prev !== 'disconnected' && prev !== 'error' && prev !== 'connected') {
               return 'disconnected';
            }
            return prev;
        });
      };

    } catch (err: any) {
      console.error("Failed to start WhatsApp session:", err);
      setState('error');
      setError(err.response?.data?.message || err.message || "Failed to initialize session.");
    }
  }, [agentId]);

  const stopSession = useCallback(async () => {
    try {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      await stopWhatsAppSession(agentId);
      setState('disconnected');
      setQrCode(null);
      setPhoneNumber(null);
    } catch (err: any) {
      console.error("Failed to stop session:", err);
      setState('disconnected');
      setError(err.response?.data?.message || err.message || "Failed to stop session cleanly.");
    }
  }, [agentId]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return { state, qrCode, phoneNumber, error, startSession, stopSession };
}
