import { useState, useEffect, useRef } from 'react';
import { Box, IconButton, Typography, Button, Tooltip } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import SkipPreviousIcon from '@mui/icons-material/SkipPrevious';
import RepeatIcon from '@mui/icons-material/Repeat';
import SpeedIcon from '@mui/icons-material/Speed';

import { PlaybackSpeed } from '../../types/playback';
import { prefetchLocalFrames } from '../../services/localDatasetApi';

interface PlaybackControlsProps {
  timestamps: string[];
  currentIndex: number;
  onIndexChange: (index: number) => void;
  datasetId?: string;
  variable?: string;
  resolution?: string;
}

export function PlaybackControls({
  timestamps,
  currentIndex,
  onIndexChange,
  datasetId,
  variable,
  resolution,
}: PlaybackControlsProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [loop, setLoop] = useState(true);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const totalFrames = timestamps.length;
  const isMultiFrame = totalFrames > 1;

  // Trigger prefetch when index changes during playback
  useEffect(() => {
    if (datasetId && isPlaying && totalFrames > 1) {
      prefetchLocalFrames(datasetId, variable, currentIndex, 10).catch(() => {});
    }
  }, [currentIndex, isPlaying, datasetId, variable, totalFrames]);

  const currentIndexRef = useRef(currentIndex);
  currentIndexRef.current = currentIndex;

  // Playback timer
  useEffect(() => {
    if (!isPlaying || !isMultiFrame) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }

    const intervalMs = Math.round(1000 / speed);
    intervalRef.current = setInterval(() => {
      const current = currentIndexRef.current;
      if (current + 1 < totalFrames) {
        onIndexChange(current + 1);
      } else if (loop) {
        onIndexChange(0);
      } else {
        setIsPlaying(false);
      }
    }, intervalMs);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, speed, loop, totalFrames, isMultiFrame, onIndexChange]);

  if (!isMultiFrame) return null;

  const handleTogglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      onIndexChange(currentIndex - 1);
    } else if (loop) {
      onIndexChange(totalFrames - 1);
    }
  };

  const handleNext = () => {
    if (currentIndex + 1 < totalFrames) {
      onIndexChange(currentIndex + 1);
    } else if (loop) {
      onIndexChange(0);
    }
  };

  const cycleSpeed = () => {
    const speeds: PlaybackSpeed[] = [0.5, 1, 2, 5];
    const nextIdx = (speeds.indexOf(speed) + 1) % speeds.length;
    setSpeed(speeds[nextIdx]);
  };

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        bgcolor: 'rgba(8, 12, 18, 0.88)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(255,255,255,0.08)',
        px: 1.5,
        py: 0.5,
      }}
    >
      <Tooltip title="Previous Frame">
        <IconButton size="small" onClick={handlePrev} sx={{ color: 'rgba(255,255,255,0.7)' }}>
          <SkipPreviousIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      <Tooltip title={isPlaying ? 'Pause' : 'Play'}>
        <IconButton
          size="small"
          onClick={handleTogglePlay}
          sx={{
            color: '#000000',
            bgcolor: '#00e5ff',
            '&:hover': { bgcolor: '#33ebff' },
            width: 28,
            height: 28,
          }}
        >
          {isPlaying ? <PauseIcon fontSize="small" /> : <PlayArrowIcon fontSize="small" />}
        </IconButton>
      </Tooltip>

      <Tooltip title="Next Frame">
        <IconButton size="small" onClick={handleNext} sx={{ color: 'rgba(255,255,255,0.7)' }}>
          <SkipNextIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      <Box sx={{ mx: 1, height: 16, width: 1, bgcolor: 'rgba(255,255,255,0.1)' }} />

      <Typography sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.6)', minWidth: 65, textAlign: 'center' }}>
        {currentIndex + 1} / {totalFrames}
      </Typography>

      <Tooltip title={`Speed: ${speed}x`}>
        <Button
          size="small"
          onClick={cycleSpeed}
          startIcon={<SpeedIcon sx={{ fontSize: '14px !important' }} />}
          sx={{
            color: '#00e5ff',
            fontSize: '0.7rem',
            fontWeight: 600,
            minWidth: 50,
            p: 0.5,
          }}
        >
          {speed}x
        </Button>
      </Tooltip>

      <Tooltip title={loop ? 'Loop: On' : 'Loop: Off'}>
        <IconButton
          size="small"
          onClick={() => setLoop(!loop)}
          sx={{
            color: loop ? '#00e5ff' : 'rgba(255,255,255,0.3)',
          }}
        >
          <RepeatIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Tooltip>

      {resolution && (
        <Typography sx={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.4)', ml: 0.5, textTransform: 'uppercase' }}>
          [{resolution}]
        </Typography>
      )}
    </Box>
  );
}
