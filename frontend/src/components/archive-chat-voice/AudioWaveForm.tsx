interface AudioWaveformProps {
  level: number;
}

export const AudioWaveform: React.FC<AudioWaveformProps> = ({ level }) => {
  return (
    <div className="flex items-center gap-1 h-8">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="w-1 bg-orange-500 rounded-full transition-all duration-150"
          style={{
            height: `${Math.min(100, level * (i + 1) * 20)}%`,
          }}
        />
      ))}
    </div>
  );
};
