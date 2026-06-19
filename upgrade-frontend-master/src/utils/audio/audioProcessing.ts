export const setupAudioAnalyzer = (stream: MediaStream) => {
  const audioContext = new AudioContext();
  const analyzer = audioContext.createAnalyser();
  const microphone = audioContext.createMediaStreamSource(stream);
  microphone.connect(analyzer);
  return analyzer;
};

export const transcribeAudio = async (blob: Blob) => {
  // Audio transcription logic
  const formData = new FormData();
  formData.append("file", blob);
  const response = await fetch("/api/transcribe", {
    method: "POST",
    body: formData,
  });
  return response.text();
};

export const createAudioAnalyzer = (stream: MediaStream) => {
  const audioContext = new AudioContext();
  const analyser = audioContext.createAnalyser();
  const microphone = audioContext.createMediaStreamSource(stream);
  microphone.connect(analyser);

  analyser.fftSize = 256;
  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);

  return {
    analyser,
    dataArray,
    bufferLength,
  };
};
