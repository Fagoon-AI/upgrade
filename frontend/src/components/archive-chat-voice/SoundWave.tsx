export const SoundWave = ({ isSpeaking }: { isSpeaking: boolean }) => {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '3px',
          margin: '10px 0',
        }}
      >
        {Array.from({ length: 8 }).map((_, index) => (
          <div
            key={index}
            style={{
              width: '8px',
              height: isSpeaking
                ? `${Math.random() * 30 + 5}px` // Varying heights when speaking
                : '10px', // Small uniform size when silent
              backgroundColor: '#ED6A38',
              borderRadius: '4px',
              animation: isSpeaking
                ? 'bounce 0.5s infinite ease-in-out' // Continuous animation when speaking
                : 'none',
              transition: 'height 0.3s ease',
            }}
          />
        ))}
        <style>
          {`
            @keyframes bounce {
              0%, 100% {
                transform: scaleY(1);
              }
              50% {
                transform: scaleY(1.1); /* Making the wave bounce effect */
              }
            }
          `}
        </style>
      </div>
    );
  };
  