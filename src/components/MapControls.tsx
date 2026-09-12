import { useState, useCallback, useEffect } from 'react';
import {
  Box,
  IconButton,
  Tooltip,
  Divider,
  alpha,
  Fade,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
  Typography,
  Theme,
} from '@mui/material';
import {
  Public,
  CenterFocusStrong,
  Add,
  Remove,
  Fullscreen,
  FullscreenExit,
  Navigation,
  Map,
  Explore,
  MyLocation,
  Rotate90DegreesCw,
  ThreeSixty,
  Layers,
  Satellite,
  DarkMode,
  Waves,
  Check,
  LightMode,
  Signpost,
  Palette,
  HighlightAlt,
  Label,
} from '@mui/icons-material';
import * as Cesium from 'cesium';
import { BasemapId, BASEMAPS } from './CesiumViewer';

// North Atlantic SST region bounds
const SST_REGION = {
  west: -32,
  east: 42,
  south: 50,
  north: 84,
  center: { lon: 5, lat: 67 },
};

interface MapControlsProps {
  viewer: Cesium.Viewer | null;
  currentBasemap: BasemapId;
  onBasemapChange: (id: BasemapId) => void;
  bottomOffset?: number;
  colorScaleOpen?: boolean;
  onColorScaleToggle?: () => void;
  onStartDrawing?: () => void;
  isDrawingMode?: boolean;
  labelsVisible?: boolean;
  onLabelsToggle?: () => void;
}

// Icons for each basemap
const basemapIcons: Record<BasemapId, React.ReactNode> = {
  ocean: <Waves fontSize="small" />,
  'esri-ocean': <Waves fontSize="small" />,
  satellite: <Satellite fontSize="small" />,
  's2-cloudless': <Satellite fontSize="small" />,
  light: <LightMode fontSize="small" />,
  streets: <Signpost fontSize="small" />,
  dark: <DarkMode fontSize="small" />,
};

export function MapControls({ viewer, currentBasemap, onBasemapChange, bottomOffset = 80, colorScaleOpen = false, onColorScaleToggle, onStartDrawing, isDrawingMode = false, labelsVisible = true, onLabelsToggle }: MapControlsProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [is3DMode, setIs3DMode] = useState(true);
  const [basemapAnchor, setBasemapAnchor] = useState<null | HTMLElement>(null);

  // Listen for fullscreen changes
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // Zoom in
  const handleZoomIn = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const camera = viewer.camera;
    const currentHeight = camera.positionCartographic.height;
    camera.zoomIn(currentHeight * 0.3);
    viewer.scene.requestRender();
  }, [viewer]);

  // Zoom out (with limit)
  const handleZoomOut = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const camera = viewer.camera;
    const currentHeight = camera.positionCartographic.height;
    const maxHeight = 12000000; // 12,000km max
    const newHeight = Math.min(currentHeight * 1.5, maxHeight);
    if (currentHeight < maxHeight) {
      camera.zoomOut(newHeight - currentHeight);
      viewer.scene.requestRender();
    }
  }, [viewer]);

  // Reset to home view (North Atlantic)
  const handleHome = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(SST_REGION.center.lon, SST_REGION.center.lat, 4500000),
      orientation: {
        heading: Cesium.Math.toRadians(0),
        pitch: Cesium.Math.toRadians(-75),
        roll: 0,
      },
      duration: 1.5,
    });
  }, [viewer]);

  // Reset north (orient camera to north)
  const handleResetNorth = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const camera = viewer.camera;
    const currentPosition = camera.positionCartographic;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromRadians(
        currentPosition.longitude,
        currentPosition.latitude,
        currentPosition.height
      ),
      orientation: {
        heading: 0,
        pitch: camera.pitch,
        roll: 0,
      },
      duration: 0.5,
    });
  }, [viewer]);

  // Fly to SST data region
  const handleFlyToSST = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    viewer.camera.flyTo({
      destination: Cesium.Rectangle.fromDegrees(
        SST_REGION.west,
        SST_REGION.south,
        SST_REGION.east,
        SST_REGION.north
      ),
      duration: 1.5,
    });
  }, [viewer]);

  // Toggle 2D/3D mode
  const handleToggleMode = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    if (is3DMode) {
      viewer.scene.morphTo2D(1.0);
    } else {
      viewer.scene.morphTo3D(1.0);
    }
    setIs3DMode(!is3DMode);
  }, [viewer, is3DMode]);

  // Toggle fullscreen
  const handleToggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
    } else {
      document.exitFullscreen();
    }
  }, []);

  // Top-down view
  const handleTopDown = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const camera = viewer.camera;
    const currentPosition = camera.positionCartographic;
    
    // Get the current look-at point (center of view)
    const center = viewer.camera.pickEllipsoid(
      new Cesium.Cartesian2(viewer.canvas.clientWidth / 2, viewer.canvas.clientHeight / 2),
      viewer.scene.globe.ellipsoid
    );
    
    if (center) {
      const centerCartographic = Cesium.Cartographic.fromCartesian(center);
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromRadians(
          centerCartographic.longitude,
          centerCartographic.latitude,
          currentPosition.height
        ),
        orientation: {
          heading: 0,
          pitch: Cesium.Math.toRadians(-90),
          roll: 0,
        },
        duration: 0.8,
      });
    } else {
      // Fallback: use current camera position
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromRadians(
          currentPosition.longitude,
          currentPosition.latitude,
          currentPosition.height
        ),
        orientation: {
          heading: 0,
          pitch: Cesium.Math.toRadians(-90),
          roll: 0,
        },
        duration: 0.8,
      });
    }
  }, [viewer]);

  // Tilt view (45 degrees)
  const handleTiltView = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const camera = viewer.camera;
    const currentPosition = camera.positionCartographic;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromRadians(
        currentPosition.longitude,
        currentPosition.latitude,
        currentPosition.height
      ),
      orientation: {
        heading: camera.heading,
        pitch: Cesium.Math.toRadians(-45),
        roll: 0,
      },
      duration: 0.8,
    });
  }, [viewer]);

  // Rotate 90 degrees
  const handleRotate = useCallback(() => {
    if (!viewer || viewer.isDestroyed()) return;
    const camera = viewer.camera;
    const currentPosition = camera.positionCartographic;
    const newHeading = camera.heading + Cesium.Math.toRadians(90);
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromRadians(
        currentPosition.longitude,
        currentPosition.latitude,
        currentPosition.height
      ),
      orientation: {
        heading: newHeading,
        pitch: camera.pitch,
        roll: 0,
      },
      duration: 0.5,
    });
  }, [viewer]);

  // Basemap menu handlers
  const handleBasemapClick = (event: React.MouseEvent<HTMLElement>) => {
    setBasemapAnchor(event.currentTarget);
  };

  const handleBasemapClose = () => {
    setBasemapAnchor(null);
  };

  const handleBasemapSelect = (id: BasemapId) => {
    onBasemapChange(id);
    setBasemapAnchor(null);
  };

  const buttonSx = {
    width: 36,
    height: 36,
    bgcolor: (theme: Theme) => alpha(theme.palette.background.paper, 0.9),
    backdropFilter: 'blur(8px)',
    border: 1,
    borderColor: 'divider',
    color: 'text.primary',
    '&:hover': {
      bgcolor: (theme: Theme) => alpha(theme.palette.primary.main, 0.15),
      borderColor: 'primary.main',
    },
    '& svg': {
      fontSize: 20,
    },
  };

  return (
    <Fade in timeout={500}>
      <Box
        sx={{
          position: 'absolute',
          bottom: bottomOffset,
          right: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 0.5,
          zIndex: 1000,
          transition: 'bottom 0.2s ease',
        }}
      >
        {/* View mode controls */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 0.5,
            p: 0.5,
            bgcolor: 'rgba(8, 12, 18, 0.85)',
            backdropFilter: 'blur(16px)',
            borderRadius: 0,
            border: '1px solid rgba(255,255,255,0.04)',
          }}
        >
          <Tooltip title={is3DMode ? '2D Map View' : '3D Globe View'} placement="left" arrow>
            <IconButton
              size="small"
              onClick={handleToggleMode}
              sx={buttonSx}
            >
              {is3DMode ? <Map /> : <Public />}
            </IconButton>
          </Tooltip>

          <Tooltip title="Top-down view" placement="left" arrow>
            <IconButton size="small" onClick={handleTopDown} sx={buttonSx}>
              <Explore />
            </IconButton>
          </Tooltip>

          <Tooltip title="Tilt view (45°)" placement="left" arrow>
            <IconButton size="small" onClick={handleTiltView} sx={buttonSx}>
              <ThreeSixty />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Navigation controls */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 0.5,
            p: 0.5,
            bgcolor: 'rgba(8, 12, 18, 0.85)',
            backdropFilter: 'blur(16px)',
            borderRadius: 0,
            border: '1px solid rgba(255,255,255,0.04)',
          }}
        >
          <Tooltip title="Zoom in" placement="left" arrow>
            <IconButton size="small" onClick={handleZoomIn} sx={buttonSx}>
              <Add />
            </IconButton>
          </Tooltip>

          <Tooltip title="Zoom out" placement="left" arrow>
            <IconButton size="small" onClick={handleZoomOut} sx={buttonSx}>
              <Remove />
            </IconButton>
          </Tooltip>

          <Divider sx={{ my: 0.25 }} />

          <Tooltip title="Reset north" placement="left" arrow>
            <IconButton size="small" onClick={handleResetNorth} sx={buttonSx}>
              <Navigation />
            </IconButton>
          </Tooltip>

          <Tooltip title="Rotate 90°" placement="left" arrow>
            <IconButton size="small" onClick={handleRotate} sx={buttonSx}>
              <Rotate90DegreesCw />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Location & controls */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 0.5,
            p: 0.5,
            bgcolor: 'rgba(8, 12, 18, 0.85)',
            backdropFilter: 'blur(16px)',
            borderRadius: 0,
            border: '1px solid rgba(255,255,255,0.04)',
          }}
        >
          <Tooltip title="Home (North Atlantic)" placement="left" arrow>
            <IconButton size="small" onClick={handleHome} sx={buttonSx}>
              <CenterFocusStrong />
            </IconButton>
          </Tooltip>

          <Tooltip title="Fly to SST region" placement="left" arrow>
            <IconButton size="small" onClick={handleFlyToSST} sx={buttonSx}>
              <MyLocation />
            </IconButton>
          </Tooltip>

          <Divider sx={{ my: 0.25 }} />

          <Tooltip title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'} placement="left" arrow>
            <IconButton size="small" onClick={handleToggleFullscreen} sx={buttonSx}>
              {isFullscreen ? <FullscreenExit /> : <Fullscreen />}
            </IconButton>
          </Tooltip>
        </Box>

        {/* Basemap switcher */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 0.5,
            p: 0.5,
            bgcolor: 'rgba(8, 12, 18, 0.85)',
            backdropFilter: 'blur(16px)',
            borderRadius: 0,
            border: '1px solid rgba(255,255,255,0.04)',
          }}
        >
          <Tooltip title="Change basemap" placement="left" arrow>
            <IconButton
              size="small"
              onClick={handleBasemapClick}
              sx={buttonSx}
            >
              <Layers />
            </IconButton>
          </Tooltip>

          <Tooltip title={labelsVisible ? 'Hide labels & borders' : 'Show labels & borders'} placement="left" arrow>
            <IconButton
              size="small"
              onClick={onLabelsToggle}
              sx={{
                ...buttonSx,
                ...(labelsVisible && {
                  color: '#6EF2FC',
                }),
              }}
            >
              <Label />
            </IconButton>
          </Tooltip>

          <Tooltip title="Color scale settings" placement="left" arrow>
            <IconButton
              size="small"
              onClick={onColorScaleToggle}
              sx={{
                ...buttonSx,
                ...(colorScaleOpen && {
                  bgcolor: 'rgba(110, 242, 252, 0.15)',
                  borderColor: 'rgba(110, 242, 252, 0.5)',
                  color: '#6EF2FC',
                }),
              }}
            >
              <Palette />
            </IconButton>
          </Tooltip>

          <Tooltip title="Draw area for download" placement="left" arrow>
            <IconButton
              size="small"
              onClick={onStartDrawing}
              sx={{
                ...buttonSx,
                ...(isDrawingMode && {
                  bgcolor: 'rgba(110, 242, 252, 0.15)',
                  borderColor: 'rgba(110, 242, 252, 0.5)',
                  color: '#6EF2FC',
                }),
              }}
            >
              <HighlightAlt />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Basemap Menu */}
        <Menu
          anchorEl={basemapAnchor}
          open={Boolean(basemapAnchor)}
          onClose={handleBasemapClose}
          anchorOrigin={{ vertical: 'center', horizontal: 'left' }}
          transformOrigin={{ vertical: 'center', horizontal: 'right' }}
          PaperProps={{
            sx: {
              bgcolor: (theme) => alpha(theme.palette.background.paper, 0.95),
              backdropFilter: 'blur(12px)',
              minWidth: 180,
            },
          }}
        >
          <Typography
            variant="overline"
            sx={{ px: 2, py: 0.5, display: 'block', color: 'text.secondary', fontSize: '0.65rem' }}
          >
            Basemap
          </Typography>
          {BASEMAPS.map((basemap) => (
            <MenuItem
              key={basemap.id}
              onClick={() => handleBasemapSelect(basemap.id)}
              selected={currentBasemap === basemap.id}
              sx={{ py: 0.75 }}
            >
              <ListItemIcon sx={{ color: currentBasemap === basemap.id ? 'primary.main' : 'text.secondary' }}>
                {basemapIcons[basemap.id]}
              </ListItemIcon>
              <ListItemText
                primary={basemap.name}
                secondary={basemap.description}
                primaryTypographyProps={{ fontSize: '0.875rem' }}
                secondaryTypographyProps={{ fontSize: '0.7rem' }}
              />
              {currentBasemap === basemap.id && (
                <Check fontSize="small" color="primary" sx={{ ml: 1 }} />
              )}
            </MenuItem>
          ))}
        </Menu>
      </Box>
    </Fade>
  );
}
