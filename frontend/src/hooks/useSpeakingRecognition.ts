'use client'

import { useEffect, useState } from "react";

let recognition: any = null;
if (typeof window !== 'undefined' && "webkitSpeechRecognition" in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = true; // Allow continuous updates
    recognition.interimResults = true; // Allow interim (incomplete) results
    recognition.lang = "en-US";
}

const useSpeakingRecognition = () => {
    const [text, setText] = useState("");
    const [isListening, setIsListening] = useState(false);

    useEffect(() => {
        if(typeof window === 'undefined') return
        if (!recognition) return;

        recognition.onresult = (event: SpeechRecognitionEvent) => {
            let interimTranscript = "";
            let finalTranscript = "";

            // Iterate through the event results
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }

            // Update the text state
            setText(finalTranscript || interimTranscript);
        };

        recognition.onstart = () => {
            setIsListening(true);
        };

        recognition.onend = () => {
            setIsListening(false);
        };
    }, []);

    const startListening = () => {
        setText(""); // Clear text when starting to listen
        setIsListening(true);
        recognition.start();
    };

    const stopListening = () => {
        setIsListening(false);
        recognition.stop();
    };

    return {
        text,
        isListening,
        startListening,
        hasRecognitionSupport: !!recognition,
        stopListening,
    };
};

export default useSpeakingRecognition;
