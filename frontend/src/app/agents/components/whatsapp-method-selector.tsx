import React from 'react';
import { Label } from '@/components/ui/label';

interface WhatsAppMethodSelectorProps {
  selectedMethod: 'meta' | 'qr';
  onChange: (method: 'meta' | 'qr') => void;
}

export function WhatsAppMethodSelector({ selectedMethod, onChange }: WhatsAppMethodSelectorProps) {
  return (
    <div className="mb-6 space-y-4">
      <Label className="text-base font-semibold">WhatsApp Deployment Method</Label>
      <div className="flex flex-col space-y-3">
        <label 
          htmlFor="method-meta" 
          className={`flex items-start space-x-3 rounded-lg border p-4 transition-colors cursor-pointer hover:bg-muted/50 ${selectedMethod === 'meta' ? 'border-primary bg-muted/20' : ''}`}
        >
          <input
            type="radio"
            id="method-meta"
            name="whatsapp-method"
            value="meta"
            checked={selectedMethod === 'meta'}
            onChange={(e) => onChange(e.target.value as 'meta' | 'qr')}
            className="mt-1 h-4 w-4 text-primary focus:ring-primary border-gray-300"
          />
          <div className="space-y-1 font-normal flex-1">
            <div className="font-semibold text-foreground">Meta Developer Console (Official)</div>
            <div className="text-sm text-muted-foreground">
              Use the official WhatsApp Business API. Requires a Meta Developer account and app configuration.
            </div>
          </div>
        </label>

        <label 
          htmlFor="method-qr" 
          className={`flex items-start space-x-3 rounded-lg border p-4 transition-colors cursor-pointer hover:bg-muted/50 ${selectedMethod === 'qr' ? 'border-primary bg-muted/20' : ''}`}
        >
          <input
            type="radio"
            id="method-qr"
            name="whatsapp-method"
            value="qr"
            checked={selectedMethod === 'qr'}
            onChange={(e) => onChange(e.target.value as 'meta' | 'qr')}
            className="mt-1 h-4 w-4 text-primary focus:ring-primary border-gray-300"
          />
          <div className="space-y-1 font-normal flex-1">
            <div className="font-semibold text-foreground">QR Code Scan (Unofficial)</div>
            <div className="text-sm text-muted-foreground">
              Link your personal or business WhatsApp by scanning a QR code. No developer account needed.
            </div>
          </div>
        </label>
      </div>
    </div>
  );
}
