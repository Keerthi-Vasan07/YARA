import { useState, useMemo } from 'react';
import {
  Box,
  IconButton,
  Typography,
  Tooltip,
  Stack,
  Collapse,
  alpha,
  ToggleButton,
  ToggleButtonGroup,
  Chip,
} from '@mui/material';
import {
  ChevronLeft,
  ChevronRight,
  ExpandLess,
  ExpandMore,
  CalendarMonth,
} from '@mui/icons-material';

// Month names
const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
];

// SST color scale
const SST_GRADIENT = `linear-gradient(to right, 
  #0a1128, #1a2d5a, #1e5080, #2d8a8a, 
  #4db870, #8fd14f, #d4e157, #ffca28, 
  #ff9800, #f44336, #b71c1c
)`;

interface TimelinePanelProps {
  years: Record<string, number[]>; // { "2020": [1,2,3,...12], ... }
  selectedDate: string; // "YYYY-MM-DD"
  onDateChange: (date: string) => void;
  isLoading: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
}

export function TimelinePanel({
  years,
  selectedDate,
  onDateChange,
  isLoading,
  expanded,
  onToggleExpand,
}: TimelinePanelProps) {
  // Parse selected date
  const selectedYear = selectedDate ? parseInt(selectedDate.slice(0, 4)) : null;
  const selectedMonth = selectedDate ? parseInt(selectedDate.slice(5, 7)) : null;

  // Get sorted years
  const sortedYears = useMemo(() => 
    Object.keys(years).map(Number).sort((a, b) => b - a), // Descending (newest first)
    [years]
  );

  // Currently viewed year in the picker
  const [viewYear, setViewYear] = useState<number>(selectedYear || sortedYears[0] || 2024);

  // Get available months for current view year
  const availableMonths = useMemo(() => 
    new Set(years[String(viewYear)] || []),
    [years, viewYear]
  );

  // Format selected date for display - full date with day
  const formattedDate = useMemo(() => {
    if (!selectedDate) return '—';
    const date = new Date(selectedDate);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  }, [selectedDate]);

  const handleMonthClick = (month: number) => {
    const dateStr = `${viewYear}-${String(month).padStart(2, '0')}-01`;
    onDateChange(dateStr);
  };

  const handlePrevYear = () => {
    const idx = sortedYears.indexOf(viewYear);
    if (idx < sortedYears.length - 1) {
      setViewYear(sortedYears[idx + 1]);
    }
  };

  const handleNextYear = () => {
    const idx = sortedYears.indexOf(viewYear);
    if (idx > 0) {
      setViewYear(sortedYears[idx - 1]);
    }
  };

  // Year range for display
  const yearRange = useMemo(() => {
    if (sortedYears.length === 0) return '';
    return `${sortedYears[sortedYears.length - 1]} – ${sortedYears[0]}`;
  }, [sortedYears]);

  return (
    <Box>
      {/* Collapsed bar - always visible */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2,
          py: 1,
        }}
      >
        <Stack 
          direction="row" 
          spacing={2} 
          alignItems="center"
          onClick={onToggleExpand}
          sx={{
            cursor: 'pointer',
            borderRadius: 1,
            px: 1,
            mx: -1,
            py: 0.5,
            '&:hover': {
              bgcolor: (theme) => alpha(theme.palette.action.hover, 0.5),
            },
          }}
        >
          <CalendarMonth sx={{ color: 'primary.main', fontSize: 20 }} />
          <Typography variant="subtitle2" fontWeight={600}>
            {formattedDate}
          </Typography>
          {isLoading && (
            <Chip 
              label="Loading..." 
              size="small" 
              color="primary" 
              variant="outlined"
              sx={{ height: 20, fontSize: '0.7rem' }}
            />
          )}
        </Stack>

        <Stack direction="row" spacing={2} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            {yearRange}
          </Typography>
          <IconButton 
            size="small" 
            onClick={onToggleExpand}
          >
            {expanded ? <ExpandMore fontSize="small" /> : <ExpandLess fontSize="small" />}
          </IconButton>
        </Stack>
      </Box>

      {/* Expanded calendar panel */}
      <Collapse in={expanded}>
        <Box sx={{ px: 2, pb: 2 }}>
          {/* Year selector */}
          <Stack 
            direction="row" 
            spacing={1} 
            alignItems="center" 
            justifyContent="center"
            sx={{ mb: 2 }}
          >
            <IconButton 
              size="small" 
              onClick={handlePrevYear}
              disabled={sortedYears.indexOf(viewYear) >= sortedYears.length - 1}
            >
              <ChevronLeft />
            </IconButton>
            
            <Typography 
              variant="h6" 
              sx={{ minWidth: 80, textAlign: 'center', fontWeight: 600 }}
            >
              {viewYear}
            </Typography>
            
            <IconButton 
              size="small" 
              onClick={handleNextYear}
              disabled={sortedYears.indexOf(viewYear) <= 0}
            >
              <ChevronRight />
            </IconButton>
          </Stack>

          {/* Month grid */}
          <Box 
            sx={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(6, 1fr)', 
              gap: 0.5,
              mb: 2,
            }}
          >
            {MONTHS.map((monthName, idx) => {
              const month = idx + 1;
              const isAvailable = availableMonths.has(month);
              const isSelected = viewYear === selectedYear && month === selectedMonth;
              
              return (
                <Tooltip 
                  key={month} 
                  title={isAvailable ? `${monthName} ${viewYear}` : 'Not available'}
                  arrow
                >
                  <span>
                    <ToggleButton
                      value={month}
                      selected={isSelected}
                      disabled={!isAvailable}
                      onClick={() => handleMonthClick(month)}
                      sx={{
                        width: '100%',
                        py: 0.75,
                        fontSize: '0.75rem',
                        fontWeight: isSelected ? 700 : 500,
                        border: 'none',
                        borderRadius: 1,
                        bgcolor: isSelected 
                          ? 'primary.main' 
                          : isAvailable 
                            ? (theme) => alpha(theme.palette.primary.main, 0.1)
                            : 'transparent',
                        color: isSelected 
                          ? 'primary.contrastText'
                          : isAvailable 
                            ? 'text.primary' 
                            : 'text.disabled',
                        '&:hover': {
                          bgcolor: isSelected 
                            ? 'primary.dark' 
                            : (theme) => alpha(theme.palette.primary.main, 0.2),
                        },
                        '&.Mui-disabled': {
                          color: 'text.disabled',
                          bgcolor: 'transparent',
                        },
                      }}
                    >
                      {monthName}
                    </ToggleButton>
                  </span>
                </Tooltip>
              );
            })}
          </Box>

          {/* Footer with legend */}
          <Stack 
            direction="row" 
            spacing={3} 
            alignItems="center" 
            justifyContent="space-between"
          >
            {/* Quick year jumps */}
            <ToggleButtonGroup
              size="small"
              exclusive
              value={viewYear}
              onChange={(_, newYear) => newYear && setViewYear(newYear)}
              sx={{ '& .MuiToggleButton-root': { px: 1.5, py: 0.25, fontSize: '0.7rem' } }}
            >
              {sortedYears.slice(0, 5).map(year => (
                <ToggleButton key={year} value={year}>
                  {year}
                </ToggleButton>
              ))}
              {sortedYears.length > 5 && (
                <ToggleButton value={sortedYears[sortedYears.length - 1]}>
                  {sortedYears[sortedYears.length - 1]}
                </ToggleButton>
              )}
            </ToggleButtonGroup>

            {/* SST Legend */}
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Typography variant="caption" color="text.secondary">
                SST
              </Typography>
              <Box
                sx={{
                  width: 100,
                  height: 10,
                  borderRadius: 0.5,
                  background: SST_GRADIENT,
                }}
              />
              <Stack direction="row" spacing={1.5}>
                <Typography variant="caption" color="text.secondary">-2°C</Typography>
                <Typography variant="caption" color="text.secondary">35°C</Typography>
              </Stack>
            </Stack>
          </Stack>
        </Box>
      </Collapse>
    </Box>
  );
}
