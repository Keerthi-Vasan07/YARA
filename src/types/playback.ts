/**
 * Playback Engine Types for YARA.
 */

export type PlaybackSpeed = 0.5 | 1 | 2 | 5;

export interface PlaybackState {
  isPlaying: boolean;
  currentIndex: number;
  totalFrames: number;
  currentTimestamp?: string;
  speed: PlaybackSpeed;
  loop: boolean;
  isBuffering: boolean;
  bufferedFrames: number[];
}
