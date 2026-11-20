import React from 'react';
import {Composition} from 'remotion';
import {TestVideo} from './TestVideo';

// Instagram Reels: вертикал 1080×1920, 30 кадр/сек
export const WIDTH = 1080;
export const HEIGHT = 1920;
export const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TestVideo"
        component={TestVideo}
        durationInFrames={5 * FPS}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
};
