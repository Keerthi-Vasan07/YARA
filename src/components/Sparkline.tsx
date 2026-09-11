/**
 * Sparkline - Mini chart for timeseries visualization
 * Used in SST info panel to show temperature history at a point
 */

import { useMemo } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';

interface SparklineProps {
  data: { date: string; value: number }[];
  currentDate?: string;
  width?: number;
  height?: number;
  color?: string;
  showStats?: boolean;
  loading?: boolean;
  unit?: string;
}

export function Sparkline({ 
  data, 
  currentDate,
  width = 280, 
  height = 50, 
  color = '#6EF2FC',
  showStats = true,
  loading = false,
  unit = '°C',
}: SparklineProps) {
  const { path, stats, currentPoint } = useMemo(() => {
    if (!data || data.length === 0) {
      return { path: '', points: [], stats: null, currentPoint: null };
    }

    const values = data.map(d => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;

    const padding = 4;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    // Generate path and points
    const pts: { x: number; y: number; date: string; value: number }[] = [];
    
    data.forEach((d, i) => {
      const x = padding + (i / (data.length - 1)) * chartWidth;
      const y = padding + chartHeight - ((d.value - min) / range) * chartHeight;
      pts.push({ x, y, date: d.date, value: d.value });
    });

    // Create smooth path
    const pathStr = pts.map((p, i) => {
      return i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`;
    }).join(' ');

    // Find current date point
    let currentPt = null;
    if (currentDate) {
      const idx = data.findIndex(d => d.date === currentDate);
      if (idx !== -1) {
        currentPt = pts[idx];
      }
    }

    return { 
      path: pathStr, 
      points: pts, 
      stats: { min, max, mean, count: data.length },
      currentPoint: currentPt,
    };
  }, [data, width, height, currentDate]);

  if (loading) {
    return (
      <Box sx={{ 
        width, 
        height: height + 20, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        bgcolor: 'rgba(0,0,0,0.2)',
        borderRadius: 0,
      }}>
        <CircularProgress size={20} sx={{ color: 'rgba(255,255,255,0.3)' }} />
      </Box>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Box sx={{ 
        width, 
        height: height + 20, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        bgcolor: 'rgba(0,0,0,0.2)',
        borderRadius: 0,
      }}>
        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.3)' }}>
          No timeseries data
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Chart */}
      <Box sx={{ 
        bgcolor: 'rgba(0,0,0,0.2)', 
        borderRadius: 0, 
        p: 0.5,
        position: 'relative',
      }}>
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          {/* Grid lines */}
          <line 
            x1={4} y1={height/2} x2={width-4} y2={height/2} 
            stroke="rgba(255,255,255,0.05)" 
            strokeDasharray="2,2"
          />
          
          {/* Mean line */}
          {stats && (
            <line 
              x1={4} 
              y1={4 + (height - 8) - ((stats.mean - stats.min) / (stats.max - stats.min || 1)) * (height - 8)} 
              x2={width - 4} 
              y2={4 + (height - 8) - ((stats.mean - stats.min) / (stats.max - stats.min || 1)) * (height - 8)} 
              stroke="rgba(255,255,255,0.15)" 
              strokeDasharray="4,2"
            />
          )}
          
          {/* Area fill */}
          <path
            d={`${path} L ${width - 4} ${height - 4} L 4 ${height - 4} Z`}
            fill={`${color}15`}
          />
          
          {/* Line */}
          <path
            d={path}
            fill="none"
            stroke={color}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          
          {/* Current date marker */}
          {currentPoint && (
            <>
              <circle
                cx={currentPoint.x}
                cy={currentPoint.y}
                r={4}
                fill={color}
                stroke="rgba(0,0,0,0.5)"
                strokeWidth={1}
              />
              <line
                x1={currentPoint.x}
                y1={4}
                x2={currentPoint.x}
                y2={height - 4}
                stroke={color}
                strokeWidth={1}
                strokeDasharray="2,2"
                opacity={0.5}
              />
            </>
          )}
        </svg>
      </Box>
      
      {/* Stats row */}
      {showStats && stats && (
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          mt: 0.5,
          px: 0.5,
        }}>
          <Typography variant="caption" sx={{ 
            color: 'rgba(255,255,255,0.4)', 
            fontSize: '0.6rem',
            fontFamily: '"JetBrains Mono", monospace',
          }}>
            min: {stats.min.toFixed(1)}{unit}
          </Typography>
          <Typography variant="caption" sx={{ 
            color: 'rgba(255,255,255,0.5)', 
            fontSize: '0.6rem',
            fontFamily: '"JetBrains Mono", monospace',
          }}>
            μ: {stats.mean.toFixed(1)}{unit}
          </Typography>
          <Typography variant="caption" sx={{ 
            color: 'rgba(255,255,255,0.4)', 
            fontSize: '0.6rem',
            fontFamily: '"JetBrains Mono", monospace',
          }}>
            max: {stats.max.toFixed(1)}{unit}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

export default Sparkline;
