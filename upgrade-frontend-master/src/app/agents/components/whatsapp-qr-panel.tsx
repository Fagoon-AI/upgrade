import React, { useEffect } from 'react';
import { useWhatsAppSession } from '@/hooks/useWhatsAppSession';
import { Button } from '@/components/ui/button';
import { Loader2, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';

interface WhatsAppQRPanelProps {
  agentId: string;
}

export function WhatsAppQRPanel({ agentId }: WhatsAppQRPanelProps) {
  const { state, qrCode, phoneNumber, error, startSession, stopSession } = useWhatsAppSession(agentId);

  // Auto-start session on mount if idle or disconnected (optional, but requested in flow)
  // Let's actually wait for user to click "Start" if idle, or just auto-start.
  // We'll auto-start since they already accepted the disclaimer.
  useEffect(() => {
    if (state === 'idle') {
      startSession();
    }
  }, [state, startSession]);

  return (
    <div className="rounded-lg border p-6 flex flex-col items-center justify-center min-h-[350px] space-y-6">
      <div className="text-center space-y-2 w-full">
        <h3 className="text-lg font-semibold">Link WhatsApp via QR Code</h3>
        
        {/* Status Badges */}
        <div className="flex justify-center mt-2">
          {state === 'idle' && <span className="inline-flex items-center text-sm text-muted-foreground">Waiting to start...</span>}
          {state === 'initializing' && <span className="inline-flex items-center text-sm text-blue-500"><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Preparing session...</span>}
          {state === 'connecting' && <span className="inline-flex items-center text-sm text-yellow-500"><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Handshake in progress...</span>}
          {state === 'connected' && <span className="inline-flex items-center text-sm text-green-500 font-medium"><CheckCircle2 className="w-4 h-4 mr-2" /> Connected as {phoneNumber}</span>}
          {state === 'error' && <span className="inline-flex items-center text-sm text-red-500"><AlertCircle className="w-4 h-4 mr-2" /> {error || 'An error occurred'}</span>}
          {state === 'disconnected' && <span className="inline-flex items-center text-sm text-orange-500"><AlertCircle className="w-4 h-4 mr-2" /> Session disconnected</span>}
        </div>
      </div>

      {/* QR Code Container */}
      {state === 'qr_ready' && qrCode && (
        <div className="p-4 bg-white rounded-xl border shadow-sm">
          <img src={qrCode} alt="WhatsApp QR Code" className="w-56 h-56 object-contain" />
        </div>
      )}

      {/* Instructions for QR Ready state */}
      {state === 'qr_ready' && (
        <div className="text-sm text-muted-foreground text-center space-y-1 max-w-sm">
          <p>1. Open WhatsApp on your phone</p>
          <p>2. Go to <strong>Settings &gt; Linked Devices</strong></p>
          <p>3. Tap <strong>"Link a Device"</strong></p>
          <p>4. Scan this QR code</p>
          <p className="text-xs mt-3 opacity-70 flex items-center justify-center">
             <RefreshCw className="w-3 h-3 mr-1" /> QR refreshes automatically
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-center gap-4 pt-4 w-full border-t border-border/50">
        {state === 'connected' && (
          <Button variant="destructive" onClick={stopSession}>
            Disconnect WhatsApp
          </Button>
        )}
        
        {(state === 'error' || state === 'disconnected') && (
          <Button variant="default" onClick={startSession}>
            Retry Connection
          </Button>
        )}
        
        {(state === 'qr_ready' || state === 'connecting' || state === 'initializing') && (
           <Button variant="outline" onClick={stopSession}>
             Cancel
           </Button>
        )}
      </div>
    </div>
  );
}
