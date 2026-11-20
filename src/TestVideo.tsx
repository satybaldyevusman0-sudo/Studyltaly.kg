import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

// Коопсуз аймак: Instagram четин кесет, ошондуктан жазуулар четтен 100px ичкери
const SAFE = 100;

export const TestVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scale = spring({frame, fps, config: {damping: 12}});
  const opacity = interpolate(frame, [0, 15], [0, 1], {extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill
      style={{
        background: 'linear-gradient(160deg, #1d2b64 0%, #f8cdda 100%)',
        fontFamily: 'Arial, sans-serif',
      }}
    >
      <AbsoluteFill style={{padding: SAFE, justifyContent: 'center', alignItems: 'center'}}>
        <div
          style={{
            color: 'white',
            fontSize: 110,
            fontWeight: 800,
            textAlign: 'center',
            transform: `scale(${scale})`,
            opacity,
          }}
        >
          Салам!
        </div>
        <div style={{color: 'white', fontSize: 56, marginTop: 40, textAlign: 'center', opacity}}>
          Тест видео — баары иштеп жатат
        </div>
      </AbsoluteFill>
      {/* Субтитр орду: асты жагынан 100px+ ичкери */}
      <div
        style={{
          position: 'absolute',
          left: SAFE,
          right: SAFE,
          bottom: SAFE + 250,
          textAlign: 'center',
          color: 'white',
          fontSize: 60,
          fontWeight: 700,
          background: 'rgba(0,0,0,0.55)',
          borderRadius: 20,
          padding: '20px 30px',
          opacity,
        }}
      >
        Бул жерде субтитр турат
      </div>
    </AbsoluteFill>
  );
};
