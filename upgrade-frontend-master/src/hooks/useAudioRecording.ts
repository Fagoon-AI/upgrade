import { useState, useRef, useCallback, useEffect } from "react";

interface AudioRecordingOptions {
  onTranscriptionComplete?: (transcript: string) => void;
  minAudioLevel?: number;
  stopAfterSilence?: number; // milliseconds
}

export const useAudioRecording = (options: AudioRecordingOptions = {}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const silenceTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const {
    onTranscriptionComplete,
    minAudioLevel = 10,
    stopAfterSilence = 2000, // 2 seconds of silence
  } = options;

  const cleanupAudio = useCallback(() => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
    }

    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current);
    }

    mediaRecorderRef.current = null;
    audioContextRef.current = null;
    analyserRef.current = null;
    audioChunksRef.current = [];
    setIsRecording(false);
    setAudioLevel(0);
  }, []);

  useEffect(() => {
    return () => {
      cleanupAudio();
    };
  }, [cleanupAudio]);

  const processAudioLevel = useCallback(() => {
    if (!analyserRef.current || !isRecording) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);
    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
    setAudioLevel(average);

    if (average < minAudioLevel) {
      // Reset silence timeout if already exists
      if (silenceTimeoutRef.current) {
        clearTimeout(silenceTimeoutRef.current);
      }

      // Set new silence timeout
      silenceTimeoutRef.current = setTimeout(() => {
        stopRecording();
      }, stopAfterSilence);
    } else if (silenceTimeoutRef.current) {
      // Clear silence timeout if audio level is above threshold
      clearTimeout(silenceTimeoutRef.current);
      silenceTimeoutRef.current = null;
    }

    if (isRecording) {
      requestAnimationFrame(processAudioLevel);
    }
  }, [isRecording, minAudioLevel, stopAfterSilence]);

  const startRecording = async () => {
    try {
      cleanupAudio(); // Cleanup any existing recording session

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Set up audio context and analyzer
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      const microphone = audioContext.createMediaStreamSource(stream);

      microphone.connect(analyser);
      analyser.fftSize = 256;

      audioContextRef.current = audioContext;
      analyserRef.current = analyser;

      // Set up media recorder
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        try {
          const audioBlob = new Blob(audioChunksRef.current, {
            type: "audio/mp3",
          });

          if (audioBlob.size > 0 && onTranscriptionComplete) {
            const transcript = await transcribeAudio(audioBlob);
            onTranscriptionComplete(transcript);
          }
        } catch (error) {
          console.error("Transcription error:", error);
        } finally {
          cleanupAudio();
        }
      };

      mediaRecorder.start(1000); // Collect data every second
      setIsRecording(true);
      processAudioLevel();
    } catch (error) {
      console.error("Recording error:", error);
      cleanupAudio();
    }
  };

  const stopRecording = useCallback(() => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
    }
  }, []);

  return {
    isRecording,
    audioLevel,
    startRecording,
    stopRecording,
  };
};

// Utility function to transcribe audio
async function transcribeAudio(audioBlob: Blob): Promise<string> {
  try {
    const formData = new FormData();
    formData.append("file", audioBlob, "recording.mp3");

    const response = await fetch("/api/transcribe", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error("Transcription failed");
    }

    const data = await response.json();
    return data.transcript;
  } catch (error) {
    console.error("Transcription error:", error);
    throw error;
  }
}
