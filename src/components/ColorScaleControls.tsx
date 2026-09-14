/**
 * ColorScaleControls
 *
 * Scientific color-scale editor for YARA.
 *
 * Features:
 * - Value range
 * - Preset scientific palettes
 * - Photoshop-style editable gradient
 * - Unlimited color stops
 * - Drag color stops
 * - Color wheel for selected stop
 * - Brightness control
 * - Hex color editing
 * - Add / remove gradient stops
 * - Threshold masking
 */

import { useMemo, useState, useEffect } from 'react';

import {
  Box,
  Typography,
  Slider,
  Stack,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  Divider,
  Button,
} from '@mui/material';

import {
  RestartAlt,
  FilterAlt,
  Add,
  Delete,
} from '@mui/icons-material';

import {
  LocalAnalysisControls,
  LocalAnalysisControlsProps,
} from './LocalAnalysisControls';

// ============================================================
// TYPES
// ============================================================

interface GradientStop {
  id: number;
  position: number;
  color: string;
}

interface ColorScaleControlsProps {
  localAnalysis?: LocalAnalysisControlsProps;

  minTemp: number;
  maxTemp: number;

  /**
   * Existing presets remain supported.
   *
   * A custom gradient is encoded as:
   *
   * gradient(#000000@0,#ffffff@1)
   */
  colormap: string;

  onMinTempChange: (value: number) => void;
  onMaxTempChange: (value: number) => void;
  onColormapChange: (colormap: string) => void;

  bottomOffset?: number;

  units?: string;

  thresholdEnabled?: boolean;
  thresholdMin?: number | null;
  thresholdMax?: number | null;

  onThresholdEnabledChange?: (enabled: boolean) => void;
  onThresholdMinChange?: (value: number | null) => void;
  onThresholdMaxChange?: (value: number | null) => void;

  /**
   * Called immediately when the Apply Color Scale button is clicked,
   * before any state setters fire. Use this to show a loading indicator
   * without waiting for the React state update cycle.
   */
  onApply?: () => void;
}

// ============================================================
// PRESET COLORMAPS
// ============================================================

const COLORMAPS = [
  {
    id: 'thermal',
    label: 'Thermal',
    gradient:
      'linear-gradient(90deg, #0a1929, #1565c0, #00acc1, #66bb6a, #cddc39, #ff9800, #f44336)',
  },
  {
    id: 'viridis',
    label: 'Viridis',
    gradient:
      'linear-gradient(90deg, #440154, #3b528b, #21918c, #5ec962, #fde725)',
  },
  {
    id: 'plasma',
    label: 'Plasma',
    gradient:
      'linear-gradient(90deg, #0d0887, #7e03a8, #cc4778, #f89540, #f0f921)',
  },
  {
    id: 'coolwarm',
    label: 'Cool-Warm',
    gradient:
      'linear-gradient(90deg, #3b4cc0, #7092d0, #c9d7e9, #f0cdba, #d67163, #b40426)',
  },
];

// ============================================================
// DEFAULTS
// ============================================================

const DEFAULT_MIN = -2;
const DEFAULT_MAX = 35;

// ============================================================
// THRESHOLD PRESETS
// ============================================================

const THRESHOLD_PRESETS = [
  {
    label: 'Marine Heatwave',
    min: 28,
    max: null,
    description: 'SST ≥ 28°C',
  },
  {
    label: 'Cold Water',
    min: null,
    max: 5,
    description: 'SST ≤ 5°C',
  },
  {
    label: 'Optimal Fish',
    min: 15,
    max: 25,
    description: '15-25°C range',
  },
  {
    label: 'Coral Bleaching',
    min: 29,
    max: null,
    description: 'SST ≥ 29°C',
  },
];

// ============================================================
// COLOR HELPERS
// ============================================================

function hslToHex(
  h: number,
  s: number,
  l: number
): string {
  s /= 100;
  l /= 100;

  const c =
    (1 - Math.abs(2 * l - 1)) * s;

  const x =
    c *
    (1 -
      Math.abs(
        ((h / 60) % 2) - 1
      ));

  const m = l - c / 2;

  let r = 0;
  let g = 0;
  let b = 0;

  if (h < 60) {
    r = c;
    g = x;
  } else if (h < 120) {
    r = x;
    g = c;
  } else if (h < 180) {
    g = c;
    b = x;
  } else if (h < 240) {
    g = x;
    b = c;
  } else if (h < 300) {
    r = x;
    b = c;
  } else {
    r = c;
    b = x;
  }

  const toHex = (value: number) =>
    Math.round(
      (value + m) * 255
    )
      .toString(16)
      .padStart(2, '0');

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function hexToRgb(hex: string) {
  const clean =
    hex.replace('#', '');

  if (clean.length !== 6) {
    return null;
  }

  const r = parseInt(
    clean.substring(0, 2),
    16
  );

  const g = parseInt(
    clean.substring(2, 4),
    16
  );

  const b = parseInt(
    clean.substring(4, 6),
    16
  );

  if (
    Number.isNaN(r) ||
    Number.isNaN(g) ||
    Number.isNaN(b)
  ) {
    return null;
  }

  return { r, g, b };
}

function rgbToHsl(
  r: number,
  g: number,
  b: number
) {
  r /= 255;
  g /= 255;
  b /= 255;

  const max = Math.max(
    r,
    g,
    b
  );

  const min = Math.min(
    r,
    g,
    b
  );

  let h = 0;
  let s = 0;

  const l =
    (max + min) / 2;

  if (max !== min) {
    const d = max - min;

    s =
      l > 0.5
        ? d /
          (2 - max - min)
        : d /
          (max + min);

    switch (max) {
      case r:
        h =
          ((g - b) /
            d +
            (g < b ? 6 : 0)) /
          6;
        break;

      case g:
        h =
          ((b - r) /
            d +
            2) /
          6;
        break;

      case b:
        h =
          ((r - g) /
            d +
            4) /
          6;
        break;
    }
  }

  return {
    h: h * 360,
    s: s * 100,
    l: l * 100,
  };
}

// ============================================================
// GRADIENT SERIALIZATION
// ============================================================

function serializeGradient(
  stops: GradientStop[]
) {
  const sorted = [...stops].sort(
    (a, b) =>
      a.position - b.position
  );

  return `gradient(${sorted
    .map(
      (stop) =>
        `${stop.color}@${stop.position.toFixed(
          4
        )}`
    )
    .join(',')})`;
}

// ============================================================
// GRADIENT PARSER
// ============================================================

function parseGradient(
  value: string
): GradientStop[] | null {
  if (
    !value.startsWith(
      'gradient('
    )
  ) {
    return null;
  }

  const content =
    value.substring(
      9,
      value.length - 1
    );

  if (!content) {
    return null;
  }

  const parts =
    content.split(',');

  const stops: GradientStop[] =
    [];

  parts.forEach(
    (part, index) => {
      const separator =
        part.lastIndexOf('@');

      if (separator === -1) {
        return;
      }

      const color =
        part.substring(
          0,
          separator
        );

      const position =
        parseFloat(
          part.substring(
            separator + 1
          )
        );

      if (
        !color ||
        Number.isNaN(position)
      ) {
        return;
      }

      stops.push({
        id: index + 1,
        color,
        position,
      });
    }
  );

  return stops.length >= 2
    ? stops
    : null;
}

// ============================================================
// PRESET -> GRADIENT
// ============================================================

function presetToStops(
  id: string
): GradientStop[] {
  switch (id) {
    case 'thermal':
      return [
        {
          id: 1,
          position: 0,
          color: '#0a1929',
        },
        {
          id: 2,
          position: 0.17,
          color: '#1565c0',
        },
        {
          id: 3,
          position: 0.34,
          color: '#00acc1',
        },
        {
          id: 4,
          position: 0.5,
          color: '#66bb6a',
        },
        {
          id: 5,
          position: 0.67,
          color: '#cddc39',
        },
        {
          id: 6,
          position: 0.83,
          color: '#ff9800',
        },
        {
          id: 7,
          position: 1,
          color: '#f44336',
        },
      ];

    case 'viridis':
      return [
        {
          id: 1,
          position: 0,
          color: '#440154',
        },
        {
          id: 2,
          position: 0.25,
          color: '#3b528b',
        },
        {
          id: 3,
          position: 0.5,
          color: '#21918c',
        },
        {
          id: 4,
          position: 0.75,
          color: '#5ec962',
        },
        {
          id: 5,
          position: 1,
          color: '#fde725',
        },
      ];

    case 'plasma':
      return [
        {
          id: 1,
          position: 0,
          color: '#0d0887',
        },
        {
          id: 2,
          position: 0.25,
          color: '#7e03a8',
        },
        {
          id: 3,
          position: 0.5,
          color: '#cc4778',
        },
        {
          id: 4,
          position: 0.75,
          color: '#f89540',
        },
        {
          id: 5,
          position: 1,
          color: '#f0f921',
        },
      ];

    case 'coolwarm':
      return [
        {
          id: 1,
          position: 0,
          color: '#3b4cc0',
        },
        {
          id: 2,
          position: 0.2,
          color: '#7092d0',
        },
        {
          id: 3,
          position: 0.4,
          color: '#c9d7e9',
        },
        {
          id: 4,
          position: 0.6,
          color: '#f0cdba',
        },
        {
          id: 5,
          position: 0.8,
          color: '#d67163',
        },
        {
          id: 6,
          position: 1,
          color: '#b40426',
        },
      ];

    default:
      return [
        {
          id: 1,
          position: 0,
          color: '#000000',
        },
        {
          id: 2,
          position: 1,
          color: '#ffffff',
        },
      ];
  }
}

// ============================================================
// COLOR WHEEL
// ============================================================

interface ColorWheelProps {
  value: string;
  onChange: (
    color: string
  ) => void;
}

function ColorWheel({
  value,
  onChange,
}: ColorWheelProps) {
  const parsedRgb =
    value.startsWith('#')
      ? hexToRgb(value)
      : null;

  const initialHsl =
    parsedRgb
      ? rgbToHsl(
          parsedRgb.r,
          parsedRgb.g,
          parsedRgb.b
        )
      : {
          h: 190,
          s: 100,
          l: 50,
        };

  const [hue, setHue] =
    useState(
      initialHsl.h
    );

  const [
    saturation,
    setSaturation,
  ] = useState(
    initialHsl.s
  );

  const [
    lightness,
    setLightness,
  ] = useState(
    initialHsl.l
  );

  const updateColor = (
    newHue: number,
    newSaturation: number,
    newLightness: number
  ) => {
    const hex =
      hslToHex(
        newHue,
        newSaturation,
        newLightness
      );

    onChange(hex);
  };

  const handleWheelInteraction =
    (
      event:
        | React.PointerEvent<HTMLDivElement>
        | React.MouseEvent<HTMLDivElement>
    ) => {
      const rect =
        event.currentTarget.getBoundingClientRect();

      const x =
        event.clientX -
        rect.left;

      const y =
        event.clientY -
        rect.top;

      const centerX =
        rect.width / 2;

      const centerY =
        rect.height / 2;

      const dx =
        x - centerX;

      const dy =
        y - centerY;

      const distance =
        Math.sqrt(
          dx * dx +
            dy * dy
        );

      const radius =
        Math.min(
          rect.width,
          rect.height
        ) / 2;

      if (
        distance > radius
      ) {
        return;
      }

      let newHue =
        (Math.atan2(
          dy,
          dx
        ) *
          180) /
        Math.PI;

      if (newHue < 0) {
        newHue += 360;
      }

      const newSaturation =
        Math.min(
          100,
          (distance /
            radius) *
            100
        );

      setHue(newHue);
      setSaturation(
        newSaturation
      );

      updateColor(
        newHue,
        newSaturation,
        lightness
      );
    };

  const handlePointerDown =
    (
      event: React.PointerEvent<HTMLDivElement>
    ) => {
      event.currentTarget.setPointerCapture(
        event.pointerId
      );

      handleWheelInteraction(
        event
      );
    };

  const handlePointerMove =
    (
      event: React.PointerEvent<HTMLDivElement>
    ) => {
      if (
        event.currentTarget.hasPointerCapture(
          event.pointerId
        )
      ) {
        handleWheelInteraction(
          event
        );
      }
    };

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          justifyContent:
            'center',
          py: 1,
        }}
      >
        <Box
          onPointerDown={
            handlePointerDown
          }
          onPointerMove={
            handlePointerMove
          }
          sx={{
            position:
              'relative',
            width: 160,
            height: 160,
            borderRadius:
              '50%',
            cursor:
              'crosshair',
            touchAction:
              'none',

            background: `
              conic-gradient(
                #ff0000 0deg,
                #ffff00 60deg,
                #00ff00 120deg,
                #00ffff 180deg,
                #0000ff 240deg,
                #ff00ff 300deg,
                #ff0000 360deg
              )
            `,

            '&::before': {
              content:
                '""',
              position:
                'absolute',
              inset: 0,
              borderRadius:
                '50%',
              background: `
                radial-gradient(
                  circle,
                  transparent 0%,
                  rgba(255,255,255,0.05) 35%,
                  rgba(0,0,0,0.4) 100%
                )
              `,
            },

            boxShadow:
              '0 0 25px rgba(0,0,0,0.4)',
          }}
        >
          <Box
            sx={{
              position:
                'absolute',

              left: `calc(
                50% +
                ${
                  Math.cos(
                    (hue *
                      Math.PI) /
                      180
                  ) *
                  saturation *
                  0.42
                }%
              )`,

              top: `calc(
                50% +
                ${
                  Math.sin(
                    (hue *
                      Math.PI) /
                      180
                  ) *
                  saturation *
                  0.42
                }%
              )`,

              transform:
                'translate(-50%, -50%)',

              width: 22,
              height: 22,

              borderRadius:
                '50%',

              background:
                value,

              border:
                '2px solid white',

              boxShadow:
                '0 0 0 2px rgba(0,0,0,0.8)',

              zIndex: 5,
              pointerEvents:
                'none',
            }}
          />
        </Box>
      </Box>

      <Typography
        variant="caption"
        sx={{
          color:
            'rgba(255,255,255,0.4)',
          fontSize:
            '0.6rem',
          display:
            'block',
          mb: 0.25,
        }}
      >
        Brightness
      </Typography>

      <Slider
        value={lightness}
        min={5}
        max={95}
        step={1}
        onChange={(
          _,
          newValue
        ) => {
          const next =
            newValue as number;

          setLightness(next);

          updateColor(
            hue,
            saturation,
            next
          );
        }}
        sx={{
          height: 4,

          '& .MuiSlider-thumb':
            {
              width: 12,
              height: 12,
              bgcolor:
                value,
              border:
                '2px solid white',
            },

          '& .MuiSlider-track':
            {
              background:
                `linear-gradient(
                  90deg,
                  #000,
                  ${value},
                  #fff
                )`,
              border: 'none',
            },
        }}
      />

      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        sx={{ mt: 0.5 }}
      >
        <Box
          sx={{
            width: 30,
            height: 30,
            borderRadius: 0.5,
            background:
              value,
            border:
              '1px solid rgba(255,255,255,0.25)',
          }}
        />

        <Box>
          <Typography
            sx={{
              fontSize:
                '0.6rem',
              color:
                'rgba(255,255,255,0.4)',
            }}
          >
            Selected stop
          </Typography>

          <Typography
            sx={{
              fontSize:
                '0.7rem',
              color:
                'rgba(255,255,255,0.8)',
              fontFamily:
                'monospace',
            }}
          >
            {value}
          </Typography>
        </Box>
      </Stack>
    </Box>
  );
}

// ============================================================
// GRADIENT EDITOR
// ============================================================

interface GradientEditorProps {
  stops: GradientStop[];
  selectedId: number;
  onSelect: (
    id: number
  ) => void;
  onMove: (
    id: number,
    position: number
  ) => void;
  onAdd: (
    position?: number
  ) => void;
  onDelete: (
    id: number
  ) => void;
}

function GradientEditor({
  stops,
  selectedId,
  onSelect,
  onMove,
  onAdd,
  onDelete,
}: GradientEditorProps) {
  const sortedStops =
    [...stops].sort(
      (a, b) =>
        a.position -
        b.position
    );

  const gradient = `
    linear-gradient(
      90deg,
      ${sortedStops
        .map(
          (stop) =>
            `${stop.color} ${
              stop.position * 100
            }%`
        )
        .join(', ')}
    )
  `;

  const handleGradientClick =
    (
      event: React.MouseEvent<HTMLDivElement>
    ) => {
      const rect =
        event.currentTarget.getBoundingClientRect();

      const position =
        Math.max(
          0,
          Math.min(
            1,
            (event.clientX -
              rect.left) /
              rect.width
          )
        );

      onAdd(position);
    };

  const handleStopPointerDown =
    (
      event: React.PointerEvent<HTMLDivElement>,
      stop: GradientStop
    ) => {
      event.stopPropagation();

      onSelect(stop.id);

      event.currentTarget.setPointerCapture(
        event.pointerId
      );

      const parent =
        event.currentTarget.parentElement;

      if (!parent) {
        return;
      }

      const rect =
        parent.getBoundingClientRect();

      const move = (
        e: PointerEvent
      ) => {
        const position =
          Math.max(
            0,
            Math.min(
              1,
              (e.clientX -
                rect.left) /
                rect.width
            )
          );

        onMove(
          stop.id,
          position
        );
      };

      const up = () => {
        window.removeEventListener(
          'pointermove',
          move
        );

        window.removeEventListener(
          'pointerup',
          up
        );
      };

      window.addEventListener(
        'pointermove',
        move
      );

      window.addEventListener(
        'pointerup',
        up
      );
    };

  return (
    <Box>
      <Typography
        variant="caption"
        sx={{
          color:
            'rgba(255,255,255,0.45)',
          fontSize:
            '0.65rem',
          display:
            'block',
          mb: 0.75,
        }}
      >
        Custom Gradient
      </Typography>

      {/* GRADIENT BAR */}

      <Box
        sx={{
          position:
            'relative',
          px: 0.5,
          pt: 1.8,
          pb: 1.8,
        }}
      >
        <Box
          onClick={
            handleGradientClick
          }
          sx={{
            height: 22,
            borderRadius: 0.5,
            background:
              gradient,
            border:
              '1px solid rgba(255,255,255,0.25)',
            cursor:
              'crosshair',
            boxShadow:
              '0 0 12px rgba(0,0,0,0.4)',
          }}
        />

        {/* COLOR STOPS */}

        {sortedStops.map(
          (stop) => (
            <Box
              key={stop.id}
              onPointerDown={(
                event
              ) =>
                handleStopPointerDown(
                  event,
                  stop
                )
              }
              onClick={(event) => {
                event.stopPropagation();
                onSelect(
                  stop.id
                );
              }}
              sx={{
                position:
                  'absolute',

                left: `calc(
                  ${
                    stop.position *
                    100
                  }% + 2px
                )`,

                bottom: 1,

                transform:
                  'translateX(-50%)',

                width:
                  selectedId ===
                  stop.id
                    ? 18
                    : 14,

                height:
                  selectedId ===
                  stop.id
                    ? 18
                    : 14,

                borderRadius:
                  '50%',

                background:
                  stop.color,

                border:
                  selectedId ===
                  stop.id
                    ? '2px solid white'
                    : '2px solid rgba(255,255,255,0.55)',

                boxShadow:
                  selectedId ===
                  stop.id
                    ? '0 0 0 2px rgba(0,0,0,0.8), 0 0 8px rgba(255,255,255,0.5)'
                    : '0 1px 4px rgba(0,0,0,0.8)',

                cursor:
                  'grab',

                zIndex: 10,

                '&:active': {
                  cursor:
                    'grabbing',
                },
              }}
            />
          )
        )}
      </Box>

      {/* STOP INFO */}

      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mt: 0.25 }}
      >
        <Typography
          sx={{
            fontSize:
              '0.55rem',
            color:
              'rgba(255,255,255,0.3)',
          }}
        >
          Click gradient to add
          a color stop
        </Typography>

        <Typography
          sx={{
            fontSize:
              '0.55rem',
            color:
              'rgba(255,255,255,0.3)',
          }}
        >
          {stops.length} colors
        </Typography>
      </Stack>

      {/* SELECTED STOP */}

      {(() => {
        const selected =
          stops.find(
            (stop) =>
              stop.id ===
              selectedId
          );

        if (!selected) {
          return null;
        }

        return (
          <Box
            sx={{
              mt: 1,
              p: 0.75,
              bgcolor:
                'rgba(255,255,255,0.035)',
              border:
                '1px solid rgba(255,255,255,0.08)',
              borderRadius:
                0.5,
            }}
          >
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
            >
              <Typography
                sx={{
                  fontSize:
                    '0.6rem',
                  color:
                    'rgba(255,255,255,0.55)',
                }}
              >
                Selected Color Stop
              </Typography>

              <Tooltip
                title={
                  stops.length <=
                  2
                    ? 'At least two colors are required'
                    : 'Delete color stop'
                }
              >
                <span>
                  <IconButton
                    size="small"
                    disabled={
                      stops.length <=
                      2
                    }
                    onClick={() =>
                      onDelete(
                        selected.id
                      )
                    }
                    sx={{
                      p: 0.25,
                    }}
                  >
                    <Delete
                      sx={{
                        fontSize:
                          14,
                        color:
                          'rgba(255,80,80,0.7)',
                      }}
                    />
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>

            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{
                mt: 0.5,
              }}
            >
              <Box
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius:
                    0.5,
                  bgcolor:
                    selected.color,
                  border:
                    '1px solid rgba(255,255,255,0.25)',
                }}
              />

              <Box
                component="input"
                value={
                  selected.color
                }
                onChange={(
                  e
                ) => {
                  const value =
                    e.target.value;

                  if (
                    /^#[0-9A-Fa-f]{6}$/.test(
                      value
                    )
                  ) {
                    onSelect(
                      selected.id
                    );
                  }
                }}
                sx={{
                  width: 95,
                  bgcolor:
                    'rgba(255,255,255,0.05)',
                  border:
                    '1px solid rgba(255,255,255,0.1)',
                  borderRadius:
                    0.5,
                  color:
                    'white',
                  fontFamily:
                    'monospace',
                  fontSize:
                    '0.65rem',
                  px: 0.75,
                  py: 0.5,
                  outline:
                    'none',
                }}
              />

              <Typography
                sx={{
                  fontSize:
                    '0.55rem',
                  color:
                    'rgba(255,255,255,0.35)',
                }}
              >
                {Math.round(
                  selected.position *
                    100
                )}
                %
              </Typography>
            </Stack>
          </Box>
        );
      })()}

      {/* ADD BUTTON */}

      <Box
        sx={{
          display:
            'flex',
          justifyContent:
            'center',
          mt: 0.75,
        }}
      >
        <Box
          onClick={() =>
            onAdd()
          }
          sx={{
            display:
              'flex',
            alignItems:
              'center',
            gap: 0.5,
            px: 1,
            py: 0.4,
            border:
              '1px solid rgba(110,242,252,0.2)',
            bgcolor:
              'rgba(110,242,252,0.05)',
            color:
              'rgba(255,255,255,0.65)',
            fontSize:
              '0.6rem',
            cursor:
              'pointer',
            borderRadius:
              0.5,
            '&:hover': {
              bgcolor:
                'rgba(110,242,252,0.1)',
            },
          }}
        >
          <Add
            sx={{
              fontSize: 14,
            }}
          />

          Add Color
        </Box>
      </Box>
    </Box>
  );
}

// ============================================================
// MAIN COMPONENT
// ============================================================

export function ColorScaleControls({
  localAnalysis,

  minTemp,
  maxTemp,

  colormap,

  onMinTempChange,
  onMaxTempChange,
  onColormapChange,

  bottomOffset = 220,

  units = '°C',

  thresholdEnabled = false,
  thresholdMin = null,
  thresholdMax = null,

  onThresholdEnabledChange,
  onThresholdMinChange,
  onThresholdMaxChange,

  onApply,
}: ColorScaleControlsProps) {
  // ── Draft State for Color Scale ──────────────────────────────────────────
  const [draftMin, setDraftMin] = useState(minTemp);
  const [draftMax, setDraftMax] = useState(maxTemp);
  const [draftColormap, setDraftColormap] = useState(colormap);
  const [draftThresholdEnabled, setDraftThresholdEnabled] = useState(thresholdEnabled);
  const [draftThresholdMin, setDraftThresholdMin] = useState(thresholdMin);
  const [draftThresholdMax, setDraftThresholdMax] = useState(thresholdMax);

  const [
    _showThresholds,
    _setShowThresholds,
  ] = useState(false);

  useEffect(() => { setDraftMin(minTemp); }, [minTemp]);
  useEffect(() => { setDraftMax(maxTemp); }, [maxTemp]);
  useEffect(() => { setDraftColormap(colormap); }, [colormap]);
  useEffect(() => { setDraftThresholdEnabled(thresholdEnabled); }, [thresholdEnabled]);
  useEffect(() => { setDraftThresholdMin(thresholdMin); }, [thresholdMin]);
  useEffect(() => { setDraftThresholdMax(thresholdMax); }, [thresholdMax]);

  const handleColorApply = () => {
    // Fire immediately so the parent can show a loading state before
    // React processes the individual state setter calls below.
    onApply?.();

    onMinTempChange(draftMin);
    onMaxTempChange(draftMax);
    onColormapChange(draftColormap);
    onThresholdEnabledChange?.(draftThresholdEnabled);
    onThresholdMinChange?.(draftThresholdMin);
    onThresholdMaxChange?.(draftThresholdMax);
  };

  // ----------------------------------------------------------
  // LOCAL MODE
  // ----------------------------------------------------------

  if (localAnalysis) {
    return (
      <LocalAnalysisControls
        {...localAnalysis}
        bottomOffset={
          bottomOffset
        }
      />
    );
  }

  // ----------------------------------------------------------
  // INITIAL GRADIENT
  // ----------------------------------------------------------

  const initialStops =
    useMemo(() => {
      const parsed =
        parseGradient(
          draftColormap
        );

      if (parsed) {
        return parsed;
      }

      return presetToStops(
        draftColormap
      );
    }, [draftColormap]);

  const [
    gradientStops,
    setGradientStops,
  ] =
    useState<GradientStop[]>(
      initialStops
    );

  const [
    selectedStopId,
    setSelectedStopId,
  ] =
    useState<number>(
      initialStops[0]?.id ??
        1
    );

  const applyStops = (
    stops: GradientStop[]
  ) => {
    setGradientStops(
      stops
    );

    setDraftColormap(
      serializeGradient(
        stops
      )
    );
  };

  // ----------------------------------------------------------
  // SELECT PRESET
  // ----------------------------------------------------------

  const handlePresetClick = (
    id: string
  ) => {
    const stops =
      presetToStops(id);

    setGradientStops(
      stops
    );

    setSelectedStopId(
      stops[0].id
    );

    setDraftColormap(id);
  };

  // ----------------------------------------------------------
  // ADD COLOR STOP
  // ----------------------------------------------------------

  const handleAddStop = (
    requestedPosition?: number
  ) => {
    const sorted =
      [...gradientStops].sort(
        (a, b) =>
          a.position -
          b.position
      );

    let position =
      requestedPosition;

    if (
      position ===
      undefined
    ) {
      const selected =
        gradientStops.find(
          (stop) =>
            stop.id ===
            selectedStopId
        );

      position =
        selected
          ? Math.min(
              0.95,
              selected.position +
                0.1
            )
          : 0.5;
    }

    position =
      Math.max(
        0.01,
        Math.min(
          0.99,
          position
        )
      );

    // Find nearest two stops
    let left =
      sorted[0];

    let right =
      sorted[
        sorted.length - 1
      ];

    for (
      let i = 0;
      i <
      sorted.length - 1;
      i++
    ) {
      if (
        position >=
          sorted[i]
            .position &&
        position <=
          sorted[i + 1]
            .position
      ) {
        left =
          sorted[i];

        right =
          sorted[i + 1];

        break;
      }
    }

    const ratio =
      right.position ===
      left.position
        ? 0.5
        : (position -
            left.position) /
          (right.position -
            left.position);

    const leftRgb =
      hexToRgb(
        left.color
      );

    const rightRgb =
      hexToRgb(
        right.color
      );

    let color =
      '#ffffff';

    if (
      leftRgb &&
      rightRgb
    ) {
      const r = Math.round(
        leftRgb.r +
          (rightRgb.r -
            leftRgb.r) *
            ratio
      );

      const g = Math.round(
        leftRgb.g +
          (rightRgb.g -
            leftRgb.g) *
            ratio
      );

      const b = Math.round(
        leftRgb.b +
          (rightRgb.b -
            leftRgb.b) *
            ratio
      );

      color =
        '#' +
        [r, g, b]
          .map(
            (v) =>
              v
                .toString(16)
                .padStart(
                  2,
                  '0'
                )
          )
          .join('');
    }

    const newId =
      Math.max(
        0,
        ...gradientStops.map(
          (s) => s.id
        )
      ) + 1;

    const newStop: GradientStop =
      {
        id: newId,
        position,
        color,
      };

    const next = [
      ...gradientStops,
      newStop,
    ];

    setSelectedStopId(
      newId
    );

    applyStops(next);
  };

  // ----------------------------------------------------------
  // MOVE COLOR STOP
  // ----------------------------------------------------------

  const handleMoveStop = (
    id: number,
    position: number
  ) => {
    const next =
      gradientStops.map(
        (stop) =>
          stop.id === id
            ? {
                ...stop,
                position,
              }
            : stop
      );

    applyStops(next);
  };

  // ----------------------------------------------------------
  // DELETE COLOR STOP
  // ----------------------------------------------------------

  const handleDeleteStop = (
    id: number
  ) => {
    if (
      gradientStops.length <=
      2
    ) {
      return;
    }

    const next =
      gradientStops.filter(
        (stop) =>
          stop.id !== id
      );

    const nextSelected =
      next[0]?.id ?? 1;

    setSelectedStopId(
      nextSelected
    );

    applyStops(next);
  };

  // ----------------------------------------------------------
  // CHANGE SELECTED COLOR
  // ----------------------------------------------------------

  const handleSelectedColorChange =
    (
      color: string
    ) => {
      const next =
        gradientStops.map(
          (stop) =>
            stop.id ===
            selectedStopId
              ? {
                  ...stop,
                  color,
                }
              : stop
        );

      applyStops(next);
    };

  // ----------------------------------------------------------
  // CURRENT SELECTED STOP
  // ----------------------------------------------------------

  const selectedStop =
    gradientStops.find(
      (stop) =>
        stop.id ===
        selectedStopId
    ) ??
    gradientStops[0];

  // ----------------------------------------------------------
  // RESET
  // ----------------------------------------------------------

  const handleReset = () => {
    setDraftMin(DEFAULT_MIN);
    setDraftMax(DEFAULT_MAX);
    const stops = presetToStops('thermal');
    setGradientStops(stops);
    setSelectedStopId(stops[0].id);
    setDraftColormap('thermal');
    setDraftThresholdEnabled(false);
    setDraftThresholdMin(null);
    setDraftThresholdMax(null);
  };

  // ----------------------------------------------------------
  // THRESHOLD PRESET
  // ----------------------------------------------------------

  const handlePresetThreshold =
    (
      preset: typeof THRESHOLD_PRESETS[number]
    ) => {
      setDraftThresholdMin(preset.min);
      setDraftThresholdMax(preset.max);
      setDraftThresholdEnabled(true);
    };

  // ----------------------------------------------------------
  // CURRENT PRESET
  // ----------------------------------------------------------

  const currentColormap =
    COLORMAPS.find(
      (c) =>
        c.id ===
        draftColormap
    ) ??
    COLORMAPS[0];

  // ----------------------------------------------------------
  // UI
  // ----------------------------------------------------------

  return (
    <Box
      sx={{
        position:
          'absolute',

        bottom:
          bottomOffset + 8,

        right: 72,

        bgcolor:
          'rgba(8, 12, 18, 0.94)',

        backdropFilter:
          'blur(12px)',

        border:
          '1px solid rgba(255,255,255,0.08)',

        overflow:
          'hidden',

        zIndex: 100,

        width: 300,

        maxHeight:
          'calc(100vh - 100px)',

        overflowY:
          'auto',

        '&::-webkit-scrollbar':
          {
            width: 4,
          },

        '&::-webkit-scrollbar-thumb':
          {
            background:
              'rgba(255,255,255,0.15)',
          },
      }}
    >
      {/* =====================================================
          HEADER
      ===================================================== */}

      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{
          px: 1.5,
          py: 1,

          borderBottom:
            '1px solid rgba(255,255,255,0.06)',
        }}
      >
        <Typography
          variant="caption"
          sx={{
            color:
              'rgba(255,255,255,0.7)',
            fontSize:
              '0.75rem',
            fontWeight: 600,
          }}
        >
          Color Scale
        </Typography>

        <Tooltip
          title="Reset to defaults"
          arrow
        >
          <IconButton
            size="small"
            onClick={
              handleReset
            }
            sx={{
              p: 0.25,
            }}
          >
            <RestartAlt
              sx={{
                fontSize: 14,
                color:
                  'rgba(255,255,255,0.4)',
              }}
            />
          </IconButton>
        </Tooltip>
      </Stack>

      {/* =====================================================
          BODY
      ===================================================== */}

      <Box
        sx={{
          p: 1.5,
          pt: 1,
        }}
      >
        <Stack
          spacing={1.5}
        >
          {/* =================================================
              VALUE RANGE
          ================================================= */}

          <Box>
            <Typography
              variant="caption"
              sx={{
                color:
                  'rgba(255,255,255,0.5)',
                fontSize:
                  '0.65rem',
                mb: 0.75,
                display:
                  'block',
              }}
            >
              Value Range
            </Typography>

            <Stack
              direction="row"
              spacing={1.5}
              alignItems="center"
            >
              <Typography
                sx={{
                  color:
                    'rgba(255,255,255,0.8)',
                  fontSize:
                    '0.75rem',
                  fontFamily:
                    'monospace',
                  minWidth: 42,
                }}
              >
                {draftMin}
                {units}
              </Typography>

              <Slider
                value={[
                  draftMin,
                  draftMax,
                ]}
                min={-5}
                max={40}
                onChange={(
                  _,
                  value
                ) => {
                  const [
                    min,
                    max,
                  ] =
                    value as number[];

                  setDraftMin(min);
                  setDraftMax(max);
                }}
                valueLabelDisplay="auto"
                valueLabelFormat={(
                  v
                ) =>
                  `${v}${units}`
                }
                sx={{
                  flex: 1,
                  height: 6,

                  '& .MuiSlider-track':
                    {
                      background:
                        currentColormap.gradient,
                      border:
                        'none',
                    },

                  '& .MuiSlider-rail':
                    {
                      bgcolor:
                        'rgba(255,255,255,0.1)',
                    },

                  '& .MuiSlider-thumb':
                    {
                      width: 14,
                      height: 14,
                      bgcolor:
                        '#fff',
                    },
                }}
              />

              <Typography
                sx={{
                  color:
                    'rgba(255,255,255,0.8)',
                  fontSize:
                    '0.75rem',
                  fontFamily:
                    'monospace',
                  minWidth: 42,
                  textAlign:
                    'right',
                }}
              >
                {draftMax}
                {units}
              </Typography>
            </Stack>
          </Box>

          {/* =================================================
              PRESETS
          ================================================= */}

          <Box>
            <Typography
              variant="caption"
              sx={{
                color:
                  'rgba(255,255,255,0.4)',
                fontSize:
                  '0.65rem',
                mb: 0.5,
                display:
                  'block',
              }}
            >
              Preset Palettes
            </Typography>

            <Stack
              spacing={0.5}
            >
              {COLORMAPS.map(
                (cm) => (
                  <Box
                    key={cm.id}
                    onClick={() =>
                      handlePresetClick(
                        cm.id
                      )
                    }
                    sx={{
                      display:
                        'flex',
                      alignItems:
                        'center',
                      gap: 1,
                      p: 0.6,
                      cursor:
                        'pointer',

                      border:
                        draftColormap ===
                        cm.id
                          ? '1px solid rgba(110,242,252,0.35)'
                          : '1px solid rgba(255,255,255,0.06)',

                      bgcolor:
                        draftColormap ===
                        cm.id
                          ? 'rgba(110,242,252,0.08)'
                          : 'transparent',

                      '&:hover':
                        {
                          bgcolor:
                            'rgba(255,255,255,0.05)',
                        },
                    }}
                  >
                    <Box
                      sx={{
                        width:
                          100,
                        height:
                          10,
                        borderRadius:
                          0.25,
                        background:
                          cm.gradient,
                        flexShrink:
                          0,
                      }}
                    />

                    <Typography
                      sx={{
                        fontSize:
                          '0.65rem',
                        color:
                          'rgba(255,255,255,0.65)',
                      }}
                    >
                      {
                        cm.label
                      }
                    </Typography>
                  </Box>
                )
              )}
            </Stack>
          </Box>

          {/* =================================================
              GRADIENT EDITOR
          ================================================= */}

          <Divider
            sx={{
              borderColor:
                'rgba(255,255,255,0.08)',
            }}
          />

          <GradientEditor
            stops={
              gradientStops
            }
            selectedId={
              selectedStop?.id ??
              1
            }
            onSelect={
              setSelectedStopId
            }
            onMove={
              handleMoveStop
            }
            onAdd={
              handleAddStop
            }
            onDelete={
              handleDeleteStop
            }
          />

          {/* =================================================
              COLOR WHEEL
          ================================================= */}

          {selectedStop && (
            <>
              <Divider
                sx={{
                  borderColor:
                    'rgba(255,255,255,0.08)',
                }}
              />

              <Box>
                <Typography
                  variant="caption"
                  sx={{
                    color:
                      'rgba(255,255,255,0.4)',
                    fontSize:
                      '0.65rem',
                    mb: 0.5,
                    display:
                      'block',
                  }}
                >
                  Color Wheel
                </Typography>

                <ColorWheel
                  value={
                    selectedStop.color
                  }
                  onChange={
                    handleSelectedColorChange
                  }
                />

                <Typography
                  variant="caption"
                  sx={{
                    color:
                      'rgba(255,255,255,0.3)',
                    fontSize:
                      '0.55rem',
                    display:
                      'block',
                    mt: 0.5,
                    textAlign:
                      'center',
                  }}
                >
                  Select a stop above,
                  then choose its
                  color here.
                </Typography>
              </Box>
            </>
          )}

          {/* =================================================
              THRESHOLD MASKING
          ================================================= */}

          {onThresholdEnabledChange && (
            <>
              <Divider
                sx={{
                  borderColor:
                    'rgba(255,255,255,0.08)',
                  my: 0.5,
                }}
              />

              <Box>
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Stack
                    direction="row"
                    alignItems="center"
                    spacing={0.5}
                  >
                    <FilterAlt
                      sx={{
                        fontSize: 14,
                        color:
                          thresholdEnabled
                            ? '#FFB347'
                            : 'rgba(255,255,255,0.4)',
                      }}
                    />

                    <Typography
                      variant="caption"
                      sx={{
                        color:
                          'rgba(255,255,255,0.5)',
                        fontSize:
                          '0.65rem',
                      }}
                    >
                      Threshold Mask
                    </Typography>
                  </Stack>

                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={
                          draftThresholdEnabled
                        }
                        onChange={(
                          e
                        ) =>
                          setDraftThresholdEnabled(
                            e.target
                              .checked
                          )
                        }
                      />
                    }
                    label=""
                    sx={{
                      m: 0,
                    }}
                  />
                </Stack>

                {draftThresholdEnabled && (
                  <Box
                    sx={{
                      mt: 1,
                    }}
                  >
                    <Stack
                      direction="row"
                      flexWrap="wrap"
                      gap={0.5}
                      sx={{
                        mb: 1,
                      }}
                    >
                      {THRESHOLD_PRESETS.map(
                        (
                          preset
                        ) => (
                          <Tooltip
                            key={
                              preset.label
                            }
                            title={
                              preset.description
                            }
                            arrow
                          >
                            <Box
                              onClick={() =>
                                handlePresetThreshold(
                                  preset
                                )
                              }
                              sx={{
                                px: 1,
                                py: 0.25,
                                fontSize:
                                  '0.6rem',
                                bgcolor:
                                  'rgba(255,179,71,0.1)',
                                border:
                                  '1px solid rgba(255,179,71,0.2)',
                                borderRadius:
                                  0.5,
                                color:
                                  'rgba(255,255,255,0.7)',
                                cursor:
                                  'pointer',
                              }}
                            >
                              {
                                preset.label
                              }
                            </Box>
                          </Tooltip>
                        )
                      )}
                    </Stack>

                    <Stack
                      direction="row"
                      spacing={1}
                      alignItems="center"
                    >
                      <Box
                        sx={{
                          flex: 1,
                        }}
                      >
                        <Typography
                          variant="caption"
                          sx={{
                            color:
                              'rgba(255,255,255,0.35)',
                            fontSize:
                              '0.55rem',
                          }}
                        >
                          Min (≥)
                        </Typography>

                        <Box
                          component="input"
                          type="number"
                          step="0.5"
                          value={
                            draftThresholdMin ??
                            ''
                          }
                          placeholder="—"
                          onChange={(
                            e
                          ) => {
                            const value =
                              e.target
                                .value;

                            setDraftThresholdMin(
                              value ===
                                ''
                                ? null
                                : parseFloat(
                                    value
                                  )
                            );
                          }}
                          sx={{
                            width:
                              '100%',
                            p: 0.5,
                            bgcolor:
                              'rgba(255,255,255,0.05)',
                            border:
                              '1px solid rgba(255,255,255,0.1)',
                            borderRadius:
                              0.5,
                            color:
                              'rgba(255,255,255,0.85)',
                            fontSize:
                              '0.7rem',
                            fontFamily:
                              'monospace',
                          }}
                        />
                      </Box>

                      <Typography
                        sx={{
                          color:
                            'rgba(255,255,255,0.3)',
                          fontSize:
                            '0.7rem',
                        }}
                      >
                        to
                      </Typography>

                      <Box
                        sx={{
                          flex: 1,
                        }}
                      >
                        <Typography
                          variant="caption"
                          sx={{
                            color:
                              'rgba(255,255,255,0.35)',
                            fontSize:
                              '0.55rem',
                          }}
                        >
                          Max (≤)
                        </Typography>

                        <Box
                          component="input"
                          type="number"
                          step="0.5"
                          value={
                            draftThresholdMax ??
                            ''
                          }
                          placeholder="—"
                          onChange={(
                            e
                          ) => {
                            const value =
                              e.target
                                .value;

                            setDraftThresholdMax(
                              value ===
                                ''
                                ? null
                                : parseFloat(
                                    value
                                  )
                            );
                          }}
                          sx={{
                            width:
                              '100%',
                            p: 0.5,
                            bgcolor:
                              'rgba(255,255,255,0.05)',
                            border:
                              '1px solid rgba(255,255,255,0.1)',
                            borderRadius:
                              0.5,
                            color:
                              'rgba(255,255,255,0.85)',
                            fontSize:
                              '0.7rem',
                            fontFamily:
                              'monospace',
                          }}
                        />
                      </Box>

                      <Typography
                        sx={{
                          color:
                            'rgba(255,255,255,0.4)',
                          fontSize:
                            '0.65rem',
                        }}
                      >
                        {units}
                      </Typography>
                    </Stack>
                  </Box>
                )}
              </Box>
            </>
          )}

          {/* COLOR SCALE APPLY BUTTON */}
          <Button
            variant="contained"
            fullWidth
            disabled={
              draftMin === minTemp &&
              draftMax === maxTemp &&
              draftColormap === colormap &&
              draftThresholdEnabled === thresholdEnabled &&
              draftThresholdMin === thresholdMin &&
              draftThresholdMax === thresholdMax
            }
            onClick={handleColorApply}
            sx={{
              mt: 1.5,
              py: 0.75,
              fontWeight: 700,
              fontSize: '0.72rem',
              letterSpacing: '0.08em',
              bgcolor: 'rgba(110,242,252,0.2)',
              color: '#6EF2FC',
              border: '1px solid rgba(110,242,252,0.4)',
              boxShadow: '0 0 12px rgba(110,242,252,0.2)',
              '&:hover': {
                bgcolor: 'rgba(110,242,252,0.35)',
                border: '1px solid #6EF2FC',
              },
              '&.Mui-disabled': {
                bgcolor: 'rgba(255,255,255,0.04)',
                color: 'rgba(255,255,255,0.25)',
                borderColor: 'rgba(255,255,255,0.08)',
              },
            }}
          >
            {draftMin === minTemp &&
            draftMax === maxTemp &&
            draftColormap === colormap &&
            draftThresholdEnabled === thresholdEnabled &&
            draftThresholdMin === thresholdMin &&
            draftThresholdMax === thresholdMax
              ? 'COLOR APPLIED'
              : 'APPLY COLOR SCALE'}
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}

export default ColorScaleControls;