import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface WhatsAppDisclaimerProps {
  onAccept: () => void;
}

export function WhatsAppDisclaimer({ onAccept }: WhatsAppDisclaimerProps) {
  const [accepted, setAccepted] = useState(false);

  return (
    <div className="rounded-lg border border-orange-500/30 bg-orange-500/10 p-5 space-y-4">
      <div className="flex items-center space-x-2 text-orange-600 dark:text-orange-500">
        <AlertTriangle className="h-5 w-5" />
        <h4 className="font-semibold text-lg">Important Disclaimer</h4>
      </div>
      
      <div className="text-sm text-muted-foreground space-y-2">
        <p>
          This method uses an unofficial WhatsApp Web emulation. It violates Meta's Terms of Service and may result in:
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>Permanent ban of the linked phone number</li>
          <li>Loss of WhatsApp account and chat history</li>
        </ul>
        <p className="pt-2">
          By proceeding, you acknowledge that you use this at your own risk and are solely responsible for any consequences. This is intended for development or testing purposes only.
        </p>
      </div>

      <div className="pt-4 flex items-center space-x-2">
        <input
          type="checkbox"
          id="accept-terms"
          checked={accepted}
          onChange={(e) => setAccepted(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
        />
        <label 
          htmlFor="accept-terms" 
          className="text-sm font-medium leading-none cursor-pointer text-foreground"
        >
          I understand and accept the risks
        </label>
      </div>

      <div className="pt-2">
        <Button 
          variant="default" 
          className="w-full sm:w-auto" 
          disabled={!accepted}
          onClick={onAccept}
        >
          Proceed
        </Button>
      </div>
    </div>
  );
}
