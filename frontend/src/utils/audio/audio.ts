// Define types for audio handling
type AudioDataCallback = (data: Blob) => void;
type AudioLevelCallback = (level: number) => void;

interface AudioRecordingOptions {
  onDataAvailable?: AudioDataCallback;
  onAudioLevel?: AudioLevelCallback;
  silenceThreshold?: number; // in dB
  timeSlice?: number; // in ms
}

export const setupAudioRecording = ({
  onDataAvailable,
  onAudioLevel,
  silenceThreshold = -50,
  timeSlice = 1000,
}: AudioRecordingOptions = {}) => {
  let mediaRecorder: MediaRecorder | null = null;
  let audioContext: AudioContext | null = null;
  let analyser: AnalyserNode | null = null;

  const start = async (): Promise<void> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Set up audio context and analyzer
      audioContext = new AudioContext();
      analyser = audioContext.createAnalyser();
      const microphone = audioContext.createMediaStreamSource(stream);
      microphone.connect(analyser);

      analyser.fftSize = 256;
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);

      // Set up media recorder
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0 && onDataAvailable) {
          onDataAvailable(event.data);
        }
      };

      // Start audio level monitoring
      const monitorAudioLevel = () => {
        if (!analyser) return;

        analyser.getByteFrequencyData(dataArray);
        const average = dataArray.reduce((a, b) => a + b) / bufferLength;
        const normalizedLevel = average / 256; // normalize to 0-1 range

        if (onAudioLevel) {
          onAudioLevel(normalizedLevel);
        }

        if (mediaRecorder?.state === "recording") {
          requestAnimationFrame(monitorAudioLevel);
        }
      };

      mediaRecorder.start(timeSlice);
      monitorAudioLevel();
    } catch (error) {
      console.error("Error starting audio recording:", error);
      throw error;
    }
  };

  const stop = (): void => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
    }

    if (audioContext) {
      audioContext.close();
    }

    mediaRecorder = null;
    audioContext = null;
    analyser = null;
  };

  return {
    start,
    stop,
  };
};

// Helper function to convert audio blob to base64
export const audioToBase64 = (blob: Blob): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const base64String = reader.result as string;
      resolve(base64String.split(",")[1]); // Remove data URL prefix
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
};

// Helper function to check audio level
export const getAudioLevel = (analyser: AnalyserNode): number => {
  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);
  analyser.getByteFrequencyData(dataArray);
  const average = dataArray.reduce((a, b) => a + b) / bufferLength;
  return average / 256; // normalize to 0-1
};
