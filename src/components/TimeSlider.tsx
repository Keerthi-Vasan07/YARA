import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  IconButton,
  Typography,
  Stack,
  Tooltip,
  Fade,
  Slider,
  Chip,
  Collapse,
} from '@mui/material';
import {
  PlayArrow,
  Pause,
  SkipPrevious,
  SkipNext,
  FastForward,
  FastRewind,
  CalendarMonth,
  Speed,
  ExpandLess,
  ExpandMore,
  ChevronLeft,
  ChevronRight,
  Close,
} from '@mui/icons-material';

// Month names
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

// Animation speeds (ms per frame)
const SPEEDS = [
  { value: 2000, label: '0.5x' },
  { value: 1000, label: '1x' },
  { value: 500, label: '2x' },
  { value: 250, label: '4x' },
];

// Mock dates for development (if no real dates provided)
export const MOCK_DATES: string[] = [];
for (let year = 2020; year <= 2025; year++) {
  for (let month = 1; month <= 12; month++) {
    // Skip future months for 2025
    if (year === 2025 && month > 6) break;
    MOCK_DATES.push(`${year}-${String(month).padStart(2, '0')}-01`);
  }
}

// Mock SST stats for tooltips
const MOCK_STATS: Record<string, { min: number; max: number; mean: number; coverage: number }> = {};
MOCK_DATES.forEach((date, idx) => {
  const seasonalOffset = Math.sin((idx % 12) * Math.PI / 6) * 3;
  MOCK_STATS[date] = {
    min: -1.8 + Math.random() * 0.5,
    max: 31 + Math.random() * 3 + seasonalOffset,
    mean: 17 + Math.random() * 2 + seasonalOffset,
    coverage: 95 + Math.random() * 5,
  };
});

interface TimeSliderProps {
  availableDates: string[]; // ["2020-01-01", "2020-02-01", ...]
  selectedDate: string;
  onDateChange: (date: string) => void;
  isLoading: boolean;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

// Parse date string to components
function parseDate(dateStr: string): { year: number; month: number; day: number } {
  const [year, month, day] = dateStr.split('-').map(Number);
  return { year, month, day };
}

// Format date for display - includes day
function formatDate(dateStr: string): string {
  const { year, month, day } = parseDate(dateStr);
  return `${day} ${MONTHS_FULL[month - 1]} ${year}`;
}

// Format short date
function formatShortDate(dateStr: string): string {
  const { year, month, day } = parseDate(dateStr);
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

/*
// Detailed tooltip component for timeline points (prepared for future use)
function DateTooltipContent({ date, stats }: { date: string; stats?: { min: number; max: number; mean: number; coverage: number } }) {
  const { year, month } = parseDate(date);
  const defaultStats = MOCK_STATS[date] || { min: -1.8, max: 32, mean: 17.5, coverage: 98 };
  const s = stats || defaultStats;
  
  return (
    <Box sx={{ minWidth: 170, p: 0.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75, pb: 0.5, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <CalendarMonth sx={{ fontSize: 13, color: 'rgba(255,255,255,0.5)' }} />
        <Typography variant="body2" fontWeight={500} sx={{ color: 'rgba(255,255,255,0.9)' }}>
          {MONTHS_FULL[month - 1]} {year}
        </Typography>
      </Box>
      
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Thermostat sx={{ fontSize: 11, color: 'rgba(100,180,255,0.7)' }} />
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>
            Min:
          </Typography>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: 'rgba(255,255,255,0.8)' }}>
            {s.min.toFixed(1)}°C
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Thermostat sx={{ fontSize: 11, color: 'rgba(255,100,100,0.7)' }} />
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>
            Max:
          </Typography>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: 'rgba(255,255,255,0.8)' }}>
            {s.max.toFixed(1)}°C
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Public sx={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }} />
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>
            Mean:
          </Typography>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: 'rgba(255,255,255,0.8)' }}>
            {s.mean.toFixed(1)}°C
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Layers sx={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }} />
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem' }}>
            Coverage:
          </Typography>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: 'rgba(255,255,255,0.8)' }}>
            {s.coverage.toFixed(0)}%
          </Typography>
        </Box>
      </Box>
      
      <Box sx={{ mt: 0.75, pt: 0.5, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <Box
          sx={{
            height: 3,
            borderRadius: 0.25,
            background: 'linear-gradient(90deg, #042333, #0a4c6a, #2a7e8e, #3ca894, #8fd175, #faf541)',
            opacity: 0.8,
          }}
        />
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.25 }}>
          <Typography variant="caption" sx={{ fontSize: '0.5rem', color: 'rgba(255,255,255,0.35)' }}>
            {s.min.toFixed(0)}°
          </Typography>
          <Typography variant="caption" sx={{ fontSize: '0.5rem', color: 'rgba(255,255,255,0.35)' }}>
            {s.max.toFixed(0)}°C
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
*/

// Calendar view component for date selection
interface CalendarViewProps {
  year: number;
  availableDateSet: Set<string>;
  selectedDate: string;
  onDateSelect: (date: string) => void;
  onYearChange: (year: number) => void;
  yearRange: { min: number; max: number };
  onClose: () => void;
}

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

function CalendarView({ 
  year, 
  availableDateSet, 
  selectedDate, 
  onDateSelect, 
  onYearChange,
  yearRange,
  onClose,
}: CalendarViewProps) {
  // Generate calendar data for each month
  const monthsData = useMemo(() => {
    return MONTHS.map((monthName, monthIndex) => {
      const firstDay = new Date(year, monthIndex, 1);
      const lastDay = new Date(year, monthIndex + 1, 0);
      const daysInMonth = lastDay.getDate();
      const startDayOfWeek = firstDay.getDay();
      
      const days: { day: number; dateStr: string; hasData: boolean; isSelected: boolean }[] = [];
      
      for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${year}-${String(monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        days.push({
          day,
          dateStr,
          hasData: availableDateSet.has(dateStr),
          isSelected: dateStr === selectedDate,
        });
      }
      
      return {
        name: monthName,
        fullName: MONTHS_FULL[monthIndex],
        startDayOfWeek,
        days,
      };
    });
  }, [year, availableDateSet, selectedDate]);

  // Count days with data for this year
  const daysWithData = useMemo(() => {
    return monthsData.reduce((sum, m) => sum + m.days.filter(d => d.hasData).length, 0);
  }, [monthsData]);

  return (
    <Box
      sx={{
        bgcolor: 'rgba(8, 12, 18, 0.98)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderBottom: 'none',
        maxHeight: 320,
        overflowY: 'auto',
        overflowX: 'hidden',
        '&::-webkit-scrollbar': {
          width: 4,
        },
        '&::-webkit-scrollbar-track': {
          bgcolor: 'transparent',
        },
        '&::-webkit-scrollbar-thumb': {
          bgcolor: 'rgba(255,255,255,0.1)',
          borderRadius: 2,
        },
      }}
    >
      {/* Year navigation header */}
      <Box
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: 1,
          bgcolor: 'rgba(8, 12, 18, 0.98)',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          px: 1.5,
          py: 0.75,
        }}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <IconButton
              size="small"
              onClick={() => onYearChange(year - 1)}
              disabled={year <= yearRange.min}
              sx={{ 
                p: 0.25,
                color: 'rgba(255,255,255,0.5)',
                '&:hover': { color: 'rgba(255,255,255,0.8)' },
                '&.Mui-disabled': { color: 'rgba(255,255,255,0.15)' },
              }}
            >
              <ChevronLeft sx={{ fontSize: 18 }} />
            </IconButton>
            <Typography 
              variant="body2" 
              fontWeight={600} 
              sx={{ 
                color: 'rgba(255,255,255,0.9)', 
                minWidth: 50, 
                textAlign: 'center',
                fontSize: '0.875rem',
              }}
            >
              {year}
            </Typography>
            <IconButton
              size="small"
              onClick={() => onYearChange(year + 1)}
              disabled={year >= yearRange.max}
              sx={{ 
                p: 0.25,
                color: 'rgba(255,255,255,0.5)',
                '&:hover': { color: 'rgba(255,255,255,0.8)' },
                '&.Mui-disabled': { color: 'rgba(255,255,255,0.15)' },
              }}
            >
              <ChevronRight sx={{ fontSize: 18 }} />
            </IconButton>
          </Stack>
          
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.6rem' }}>
            {daysWithData} days with data
          </Typography>

          <IconButton
            size="small"
            onClick={onClose}
            sx={{ 
              p: 0.25,
              color: 'rgba(255,255,255,0.4)',
              '&:hover': { color: 'rgba(255,255,255,0.8)' },
            }}
          >
            <Close sx={{ fontSize: 16 }} />
          </IconButton>
        </Stack>
      </Box>

      {/* Months grid - 3 columns */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 0,
        }}
      >
        {monthsData.map((month, monthIdx) => (
          <Box
            key={month.name}
            sx={{
              p: 1,
              borderRight: (monthIdx + 1) % 3 !== 0 ? '1px solid rgba(255,255,255,0.04)' : 'none',
              borderBottom: monthIdx < 9 ? '1px solid rgba(255,255,255,0.04)' : 'none',
            }}
          >
            {/* Month name */}
            <Typography
              variant="caption"
              sx={{
                display: 'block',
                textAlign: 'center',
                color: 'rgba(255,255,255,0.6)',
                fontSize: '0.6rem',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                mb: 0.5,
              }}
            >
              {month.name}
            </Typography>

            {/* Weekday headers */}
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(7, 1fr)',
                gap: 0,
                mb: 0.25,
              }}
            >
              {WEEKDAYS.map((wd) => (
                <Typography
                  key={wd}
                  sx={{
                    fontSize: '0.45rem',
                    color: 'rgba(255,255,255,0.25)',
                    textAlign: 'center',
                    lineHeight: 1,
                  }}
                >
                  {wd}
                </Typography>
              ))}
            </Box>

            {/* Days grid */}
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(7, 1fr)',
                gap: '1px',
              }}
            >
              {/* Empty cells for offset */}
              {Array.from({ length: month.startDayOfWeek }).map((_, i) => (
                <Box key={`empty-${i}`} sx={{ aspectRatio: '1', minHeight: 12 }} />
              ))}
              
              {/* Day cells */}
              {month.days.map((dayData) => (
                <Tooltip
                  key={dayData.dateStr}
                  title={dayData.hasData ? formatShortDate(dayData.dateStr) : ''}
                  arrow
                  placement="top"
                  disableHoverListener={!dayData.hasData}
                >
                  <Box
                    onClick={() => dayData.hasData && onDateSelect(dayData.dateStr)}
                    sx={{
                      aspectRatio: '1',
                      minHeight: 12,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.5rem',
                      borderRadius: 0.5,
                      cursor: dayData.hasData ? 'pointer' : 'default',
                      color: dayData.hasData 
                        ? dayData.isSelected 
                          ? '#fff' 
                          : 'rgba(255,255,255,0.85)'
                        : 'rgba(255,255,255,0.15)',
                      bgcolor: dayData.isSelected 
                        ? 'rgba(59, 130, 246, 0.8)'
                        : dayData.hasData 
                          ? 'rgba(59, 130, 246, 0.25)'
                          : 'transparent',
                      transition: 'all 0.1s ease',
                      '&:hover': dayData.hasData && !dayData.isSelected ? {
                        bgcolor: 'rgba(59, 130, 246, 0.45)',
                      } : {},
                    }}
                  >
                    {dayData.day}
                  </Box>
                </Tooltip>
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

export function TimeSlider({
  availableDates,
  selectedDate,
  onDateChange,
  isLoading,
  collapsed = false,
  onToggleCollapsed,
}: TimeSliderProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [speedIndex, setSpeedIndex] = useState(1); // Default 1x
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [calendarYear, setCalendarYear] = useState<number>(() => {
    if (selectedDate) {
      return parseDate(selectedDate).year;
    }
    return new Date().getFullYear();
  });
  const sliderRef = useRef<HTMLDivElement>(null);
  const playIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Get current index
  const currentIndex = useMemo(() => {
    const idx = availableDates.indexOf(selectedDate);
    return idx >= 0 ? idx : 0;
  }, [availableDates, selectedDate]);

  // Set of available dates for quick lookup in calendar
  const availableDateSet = useMemo(() => new Set(availableDates), [availableDates]);

  // Get year range from available dates
  const yearRange = useMemo(() => {
    if (availableDates.length === 0) return { min: new Date().getFullYear(), max: new Date().getFullYear() };
    const years = availableDates.map(d => parseDate(d).year);
    return { min: Math.min(...years), max: Math.max(...years) };
  }, [availableDates]);

  // Generate tick marks with year labels
  const tickMarks = useMemo(() => {
    const marks: { value: number; label?: string; isYearStart?: boolean }[] = [];
    let lastYear = 0;
    
    availableDates.forEach((date, index) => {
      const { year } = parseDate(date);
      const isYearStart = year !== lastYear;
      
      marks.push({
        value: index,
        label: isYearStart ? String(year) : undefined,
        isYearStart,
      });
      
      lastYear = year;
    });
    
    return marks;
  }, [availableDates]);

  // Play/pause animation
  useEffect(() => {
    if (isPlaying && availableDates.length > 0) {
      playIntervalRef.current = setInterval(() => {
        const nextIndex = (currentIndex + 1) % availableDates.length;
        onDateChange(availableDates[nextIndex]);
      }, SPEEDS[speedIndex].value);
    }
    
    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current);
      }
    };
  }, [isPlaying, currentIndex, speedIndex, availableDates, onDateChange]);

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      
      switch (e.key) {
        case 'ArrowLeft':
          handleStep(-1);
          break;
        case 'ArrowRight':
          handleStep(1);
          break;
        case ' ':
          e.preventDefault();
          setIsPlaying(p => !p);
          break;
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentIndex, availableDates]);

  const handleStep = useCallback((direction: number) => {
    const newIndex = Math.max(0, Math.min(availableDates.length - 1, currentIndex + direction));
    if (newIndex !== currentIndex) {
      onDateChange(availableDates[newIndex]);
    }
  }, [currentIndex, availableDates, onDateChange]);

  // Track scrubbing state: update display immediately, defer tile load to onChangeCommitted
  const [scrubIndex, setScrubIndex] = useState<number | null>(null);
  const isScrubbing = scrubIndex !== null;
  const displayIndex = scrubIndex ?? currentIndex;

  const handleSliderChange = useCallback((_: Event, value: number | number[]) => {
    const index = typeof value === 'number' ? value : value[0];
    setScrubIndex(index);
  }, []);

  const handleSliderCommit = useCallback((_: Event | React.SyntheticEvent, value: number | number[]) => {
    const index = typeof value === 'number' ? value : value[0];
    setScrubIndex(null);
    if (availableDates[index] && availableDates[index] !== selectedDate) {
      onDateChange(availableDates[index]);
    }
  }, [availableDates, selectedDate, onDateChange]);

  const handleSpeedCycle = useCallback(() => {
    setSpeedIndex((prev) => (prev + 1) % SPEEDS.length);
  }, []);

  const handleJumpToStart = useCallback(() => {
    if (availableDates.length > 0) {
      onDateChange(availableDates[0]);
    }
  }, [availableDates, onDateChange]);

  const handleJumpToEnd = useCallback(() => {
    if (availableDates.length > 0) {
      onDateChange(availableDates[availableDates.length - 1]);
    }
  }, [availableDates, onDateChange]);

  // Calculate preview position
  const getPreviewPosition = useCallback(() => {
    if (hoverIndex === null || !sliderRef.current) return 0;
    const width = sliderRef.current.offsetWidth;
    const percent = hoverIndex / Math.max(1, availableDates.length - 1);
    return percent * width;
  }, [hoverIndex, availableDates.length]);

  if (availableDates.length === 0) {
    return (
      <Box sx={{ p: 2, textAlign: 'center' }}>
        <Typography color="text.secondary">No data available</Typography>
      </Box>
    );
  }

  // Collapsed view - compact single row (entire row clickable)
  if (collapsed) {
    return (
      <Box 
        onClick={onToggleCollapsed}
        sx={{ 
          px: 2, 
          py: 1,
          cursor: 'pointer',
          transition: 'background-color 0.15s ease',
          '&:hover': {
            bgcolor: 'rgba(255,255,255,0.02)',
          },
        }}
      >
        <Stack direction="row" alignItems="center" justifyContent="center" spacing={3}>
          {/* Current date display */}
          <Stack direction="row" spacing={1} alignItems="center">
            <CalendarMonth sx={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }} />
            <Typography variant="body2" fontWeight={500} sx={{ color: 'rgba(255,255,255,0.85)', fontSize: '0.8125rem' }}>
              {formatDate(selectedDate)}
            </Typography>
          </Stack>

          {/* Expand indicator (center) */}
          {onToggleCollapsed && (
            <Box sx={{ 
              display: 'flex',
              alignItems: 'center',
              px: 1,
              py: 0.25,
              border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <ExpandLess sx={{ fontSize: 14, color: 'rgba(255,255,255,0.3)' }} />
            </Box>
          )}

          {/* Date counter */}
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.65rem' }}>
            {currentIndex + 1} / {availableDates.length}
          </Typography>
        </Stack>
      </Box>
    );
  }

  // Expanded view - full controls
  return (
    <Box>
      {/* Calendar view - collapsible above slider */}
      <Collapse in={showCalendar}>
        <CalendarView
          year={calendarYear}
          availableDateSet={availableDateSet}
          selectedDate={selectedDate}
          onDateSelect={(date) => {
            onDateChange(date);
            setShowCalendar(false);
          }}
          onYearChange={setCalendarYear}
          yearRange={yearRange}
          onClose={() => setShowCalendar(false)}
        />
      </Collapse>

      {/* Clickable header bar - collapse on click */}
      <Box 
        onClick={onToggleCollapsed}
        sx={{ 
          px: 2, 
          py: 0.75,
          cursor: 'pointer',
          transition: 'background-color 0.15s ease',
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          '&:hover': {
            bgcolor: 'rgba(255,255,255,0.02)',
          },
        }}
      >
        <Stack direction="row" alignItems="center" justifyContent="center" spacing={3}>
          {/* Calendar toggle button */}
          <Tooltip title={showCalendar ? "Hide calendar" : "Show calendar"} arrow>
            <IconButton
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                setShowCalendar(!showCalendar);
                // Sync calendar year with selected date when opening
                if (!showCalendar && selectedDate) {
                  setCalendarYear(parseDate(selectedDate).year);
                }
              }}
              sx={{
                p: 0.5,
                color: showCalendar ? 'rgba(59, 130, 246, 0.9)' : 'rgba(255,255,255,0.4)',
                bgcolor: showCalendar ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                '&:hover': { 
                  color: showCalendar ? 'rgba(59, 130, 246, 1)' : 'rgba(255,255,255,0.7)',
                  bgcolor: showCalendar ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255,255,255,0.05)',
                },
              }}
            >
              <CalendarMonth sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>

          {/* Current date display - clickable to toggle calendar */}
          <Stack 
            direction="row" 
            spacing={1} 
            alignItems="center"
            onClick={(e) => {
              e.stopPropagation();
              setShowCalendar(!showCalendar);
              if (!showCalendar && selectedDate) {
                setCalendarYear(parseDate(selectedDate).year);
              }
            }}
            sx={{
              cursor: 'pointer',
              px: 1,
              py: 0.25,
              borderRadius: 1,
              transition: 'background-color 0.15s ease',
              '&:hover': {
                bgcolor: 'rgba(255,255,255,0.05)',
              },
            }}
          >
            <Typography variant="body2" fontWeight={500} sx={{ color: 'rgba(255,255,255,0.85)', fontSize: '0.8125rem' }}>
              {isScrubbing ? formatDate(availableDates[displayIndex] || selectedDate) : formatDate(selectedDate)}
            </Typography>
            {isLoading && !isScrubbing && (
              <Chip 
                label="..." 
                size="small" 
                sx={{ 
                  height: 16, 
                  fontSize: '0.6rem',
                  bgcolor: 'rgba(255,255,255,0.06)',
                  color: 'rgba(255,255,255,0.5)',
                  '& .MuiChip-label': { px: 0.75 },
                }}
              />
            )}
          </Stack>

          {/* Collapse indicator (center) */}
          {onToggleCollapsed && (
            <Box sx={{ 
              display: 'flex',
              alignItems: 'center',
              px: 1,
              py: 0.25,
              border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <ExpandMore sx={{ fontSize: 14, color: 'rgba(255,255,255,0.3)' }} />
            </Box>
          )}

          {/* Date counter */}
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.3)', fontSize: '0.6rem', fontFamily: 'monospace' }}>
            {currentIndex + 1}/{availableDates.length}
          </Typography>
        </Stack>
      </Box>

      {/* Controls area */}
      <Box sx={{ px: 2, py: 0.75 }}>
        {/* Playback controls row */}
        <Stack 
          direction="row" 
          alignItems="center" 
          justifyContent="center"
          spacing={0.25}
          sx={{ mb: 0.75 }}
        >
          {/* Jump to start */}
          <Tooltip title="First date" arrow>
            <IconButton 
              size="small" 
              onClick={handleJumpToStart}
              disabled={currentIndex === 0}
              sx={{ color: 'rgba(255,255,255,0.4)', p: 0.5, '&:hover': { color: 'rgba(255,255,255,0.8)' } }}
            >
              <FastRewind sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>

          {/* Step backward */}
          <Tooltip title="Previous (←)" arrow>
            <IconButton 
              size="small" 
              onClick={() => handleStep(-1)}
              disabled={currentIndex === 0}
              sx={{ color: 'rgba(255,255,255,0.4)', p: 0.5, '&:hover': { color: 'rgba(255,255,255,0.8)' } }}
            >
              <SkipPrevious sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>

          {/* Play/Pause */}
          <Tooltip title={isPlaying ? "Pause (Space)" : "Play (Space)"} arrow>
            <IconButton 
              onClick={() => setIsPlaying(!isPlaying)}
              size="small"
              sx={{ 
                width: 28,
                height: 28,
                border: '1px solid rgba(255,255,255,0.15)',
                color: isPlaying ? '#EF5350' : 'rgba(255,255,255,0.7)',
                bgcolor: 'transparent',
                '&:hover': {
                  bgcolor: 'rgba(255,255,255,0.05)',
                  borderColor: 'rgba(255,255,255,0.25)',
                },
                mx: 0.5,
              }}
            >
              {isPlaying ? <Pause sx={{ fontSize: 14 }} /> : <PlayArrow sx={{ fontSize: 14 }} />}
            </IconButton>
          </Tooltip>

          {/* Step forward */}
          <Tooltip title="Next (→)" arrow>
            <IconButton 
              size="small" 
              onClick={() => handleStep(1)}
              disabled={currentIndex === availableDates.length - 1}
              sx={{ color: 'rgba(255,255,255,0.4)', p: 0.5, '&:hover': { color: 'rgba(255,255,255,0.8)' } }}
            >
              <SkipNext sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>

          {/* Jump to end */}
          <Tooltip title="Last date" arrow>
            <IconButton 
              size="small" 
              onClick={handleJumpToEnd}
              disabled={currentIndex === availableDates.length - 1}
              sx={{ color: 'rgba(255,255,255,0.4)', p: 0.5, '&:hover': { color: 'rgba(255,255,255,0.8)' } }}
            >
              <FastForward sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>

          {/* Speed control */}
          <Tooltip title={`Speed: ${SPEEDS[speedIndex].label}`} arrow>
            <IconButton 
              size="small" 
              onClick={handleSpeedCycle}
              sx={{ ml: 0.5, color: 'rgba(255,255,255,0.4)', p: 0.5, '&:hover': { color: 'rgba(255,255,255,0.8)' } }}
            >
              <Speed sx={{ fontSize: 14 }} />
              <Typography variant="caption" sx={{ ml: 0.25, fontSize: '0.55rem', color: 'inherit' }}>
                {SPEEDS[speedIndex].label}
              </Typography>
            </IconButton>
          </Tooltip>
        </Stack>

      {/* Main slider area */}
      <Box
        ref={sliderRef}
        sx={{ 
          position: 'relative',
          px: 1,
          py: 1,
        }}
        onMouseEnter={() => setShowPreview(true)}
        onMouseLeave={() => {
          setShowPreview(false);
          setHoverIndex(null);
        }}
        onMouseMove={(e) => {
          if (!sliderRef.current || availableDates.length === 0) return;
          const rect = sliderRef.current.getBoundingClientRect();
          const x = e.clientX - rect.left;
          const percent = Math.max(0, Math.min(1, x / rect.width));
          const index = Math.round(percent * (availableDates.length - 1));
          setHoverIndex(index);
        }}
      >
        {/* Preview tooltip on hover */}
        <Fade in={showPreview && hoverIndex !== null}>
          <Box
            sx={{
              position: 'absolute',
              left: getPreviewPosition(),
              transform: 'translateX(-50%)',
              bottom: '100%',
              mb: 1,
              px: 1.5,
              py: 0.75,
              borderRadius: 1,
              bgcolor: 'rgba(8, 12, 18, 0.95)',
              backdropFilter: 'blur(8px)',
              border: '1px solid rgba(255,255,255,0.12)',
              pointerEvents: 'none',
              zIndex: 10,
              whiteSpace: 'nowrap',
            }}
          >
            {hoverIndex !== null && availableDates[hoverIndex] && (
              <Typography 
                variant="caption" 
                sx={{ 
                  fontWeight: 500, 
                  color: 'rgba(255,255,255,0.9)',
                  fontSize: '0.75rem',
                }}
              >
                {formatShortDate(availableDates[hoverIndex])}
              </Typography>
            )}
          </Box>
        </Fade>

        {/* Custom slider */}
        <Slider
          value={displayIndex}
          min={0}
          max={Math.max(0, availableDates.length - 1)}
          step={1}
          onChange={handleSliderChange}
          onChangeCommitted={handleSliderCommit}
          valueLabelDisplay="off"
          marks={tickMarks.filter(m => m.isYearStart).map(m => ({
            value: m.value,
            label: m.label,
          }))}
          sx={{
            height: 2,
            '& .MuiSlider-track': {
              background: 'rgba(255, 255, 255, 0.35)',
              border: 'none',
            },
            '& .MuiSlider-rail': {
              bgcolor: 'rgba(255,255,255,0.08)',
              opacity: 1,
            },
            '& .MuiSlider-thumb': {
              width: 10,
              height: 10,
              bgcolor: '#fff',
              border: 'none',
              boxShadow: 'none',
              '&:hover, &.Mui-focusVisible': {
                boxShadow: 'none',
                bgcolor: 'rgba(255,255,255,0.85)',
              },
              '&:before': {
                display: 'none',
              },
            },
            '& .MuiSlider-valueLabel': {
              display: 'none',
            },
            '& .MuiSlider-mark': {
              bgcolor: 'rgba(255,255,255,0.12)',
              height: 5,
              width: 1,
              '&.MuiSlider-markActive': {
                bgcolor: 'rgba(255, 255, 255, 0.3)',
              },
            },
            '& .MuiSlider-markLabel': {
              color: 'rgba(255,255,255,0.35)',
              fontSize: '0.55rem',
              top: 16,
            },
          }}
        />

        {/* Date range and count */}
        <Stack 
          direction="row" 
          justifyContent="space-between" 
          alignItems="center"
          sx={{ mt: 0.5, px: 0.5 }}
        >
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.25)', fontSize: '0.55rem', fontFamily: 'monospace', letterSpacing: '0.02em' }}>
            {availableDates[0] ? formatShortDate(availableDates[0]) : ''}
          </Typography>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.5rem', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            {availableDates.length} months
          </Typography>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.25)', fontSize: '0.55rem', fontFamily: 'monospace', letterSpacing: '0.02em' }}>
            {availableDates[availableDates.length - 1] ? formatShortDate(availableDates[availableDates.length - 1]) : ''}
          </Typography>
        </Stack>
      </Box>
      </Box>
    </Box>
  );
}
