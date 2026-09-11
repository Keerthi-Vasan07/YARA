import { useEffect, useRef, useCallback, useImperativeHandle, forwardRef, useState } from 'react';
import * as Cesium from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

// Default global SST bounds (fallback if tilejson fails)
const SST_BOUNDS = {
  west: -180,
  east: 180,
  south: -90,
  north: 90,
};

// Basemap configurations
export type BasemapId = 'ocean' | 'esri-ocean' | 'satellite' | 's2-cloudless' | 'light' | 'streets' | 'dark';

export interface BasemapConfig {
  id: BasemapId;
  name: string;
  description: string;
}

export const BASEMAPS: BasemapConfig[] = [
  { id: 'ocean', name: 'Ocean', description: 'MapTiler bathymetry' },
  { id: 'esri-ocean', name: 'ESRI Ocean', description: 'ESRI bathymetry' },
  { id: 'satellite', name: 'Satellite', description: 'Satellite imagery' },
  { id: 's2-cloudless', name: 'S2 Cloudless', description: 'Sentinel-2 cloudless' },
  { id: 'light', name: 'Light Gray', description: 'Minimal with labels' },
  { id: 'streets', name: 'Streets', description: 'Detailed street map' },
  { id: 'dark', name: 'Dark Gray', description: 'Dark minimal' },
];

export interface CesiumViewerHandle {
  viewer: Cesium.Viewer | null;
  sstLayerVisible: boolean;
  toggleSSTLayer: () => void;
  currentBasemap: BasemapId;
  setBasemap: (id: BasemapId) => void;
  setClickedPosition: (position: { lon: number; lat: number } | null) => void;
  startBboxDrawing: () => void;
  cancelBboxDrawing: () => void;
  labelsVisible: boolean;
  toggleLabels: () => void;
  flyHome: () => void;
}

export interface BoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

interface CesiumViewerProps {
  selectedDate: string; // YYYY-MM-DD format
  isLoading: boolean;
  initialBasemap?: BasemapId;
  onMapClick?: (lon: number, lat: number) => void;
  clickedPosition?: { lon: number; lat: number } | null;
  colorScaleMin?: number;
  colorScaleMax?: number;
  drawingMode?: boolean;
  onBboxDrawn?: (bbox: BoundingBox) => void;
  activeVariable?: string; // e.g., 'sst', 'sic', 'sla' (for colorscale reference)
  visibleLayers?: string[]; // Array of visible layer IDs for overlay support
  initialCamera?: { lon: number; lat: number; height: number }; // Initial camera position from URL
  onCameraChange?: (lon: number, lat: number, height: number) => void; // Called when camera moves
  availableDates?: string[]; // Sorted date list for adjacent-date prefetching
  // Threshold masking
  thresholdEnabled?: boolean;
  thresholdMin?: number | null;
  thresholdMax?: number | null;
}

// Helper to create basemap layers (may return multiple for base + labels)
async function createBasemapLayers(id: BasemapId, imageryLayers: Cesium.ImageryLayerCollection): Promise<Cesium.ImageryLayer[]> {
  const layers: Cesium.ImageryLayer[] = [];
  
  switch (id) {
    case 'satellite': {
      // MapTiler Satellite (pure imagery, no labels baked in)
      const apiKey = import.meta.env.VITE_MAPTILER_API_KEY;
      const satelliteBase = new Cesium.UrlTemplateImageryProvider({
        url: `https://api.maptiler.com/maps/satellite/{z}/{x}/{y}.jpg?key=${apiKey}`,
        credit: 'MapTiler',
        maximumLevel: 20,
      });
      layers.push(imageryLayers.addImageryProvider(satelliteBase, 0));
      
      // Add ESRI reference labels overlay (free, transparent background)
      const satelliteLabels = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
        'https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer'
      );
      layers.push(imageryLayers.addImageryProvider(satelliteLabels, 1));
      break;
    }
    case 's2-cloudless': {
      // EOX Sentinel-2 Cloudless (free for non-commercial, CC BY-NC-SA 4.0)
      const s2Cloudless = new Cesium.UrlTemplateImageryProvider({
        url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg',
        credit: 'Sentinel-2 cloudless by EOX - CC BY-NC-SA 4.0',
        maximumLevel: 15,
      });
      layers.push(imageryLayers.addImageryProvider(s2Cloudless, 0));
      
      // Add ESRI reference labels overlay (free, transparent background)
      const labelsRef = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
        'https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer'
      );
      layers.push(imageryLayers.addImageryProvider(labelsRef, 1));
      break;
    }
    case 'ocean': {
      // MapTiler Ocean style (bathymetry with clean labels)
      const apiKey = import.meta.env.VITE_MAPTILER_API_KEY;
      const oceanMap = new Cesium.UrlTemplateImageryProvider({
        url: `https://api.maptiler.com/maps/ocean/{z}/{x}/{y}.png?key=${apiKey}`,
        credit: 'MapTiler',
        maximumLevel: 20,
      });
      layers.push(imageryLayers.addImageryProvider(oceanMap, 0));
      break;
    }
    case 'esri-ocean': {
      // ESRI Ocean Base + Reference
      const oceanBase = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
        'https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer'
      );
      layers.push(imageryLayers.addImageryProvider(oceanBase, 0));
      
      const oceanRef = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
        'https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Reference/MapServer'
      );
      layers.push(imageryLayers.addImageryProvider(oceanRef, 1));
      break;
    }
    case 'light': {
      // MapTiler Light/Positron style
      const apiKey = import.meta.env.VITE_MAPTILER_API_KEY;
      const lightMap = new Cesium.UrlTemplateImageryProvider({
        url: `https://api.maptiler.com/maps/streets-v2-light/{z}/{x}/{y}.png?key=${apiKey}`,
        credit: 'MapTiler',
        maximumLevel: 20,
      });
      layers.push(imageryLayers.addImageryProvider(lightMap, 0));
      break;
    }
    case 'streets': {
      // MapTiler Streets style
      const apiKey = import.meta.env.VITE_MAPTILER_API_KEY;
      const streetsMap = new Cesium.UrlTemplateImageryProvider({
        url: `https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=${apiKey}`,
        credit: 'MapTiler',
        maximumLevel: 20,
      });
      layers.push(imageryLayers.addImageryProvider(streetsMap, 0));
      break;
    }
    case 'dark': {
      // MapTiler Dark style
      const apiKey = import.meta.env.VITE_MAPTILER_API_KEY;
      const darkMap = new Cesium.UrlTemplateImageryProvider({
        url: `https://api.maptiler.com/maps/streets-v2-dark/{z}/{x}/{y}.png?key=${apiKey}`,
        credit: 'MapTiler',
        maximumLevel: 20,
      });
      layers.push(imageryLayers.addImageryProvider(darkMap, 0));
      break;
    }
    default: {
      // MapTiler Ocean fallback
      const apiKey = import.meta.env.VITE_MAPTILER_API_KEY;
      const defaultMap = new Cesium.UrlTemplateImageryProvider({
        url: `https://api.maptiler.com/maps/ocean/{z}/{x}/{y}.png?key=${apiKey}`,
        credit: 'MapTiler',
        maximumLevel: 20,
      });
      layers.push(imageryLayers.addImageryProvider(defaultMap, 0));
    }
  }
  
  return layers;
}

// Create a circular target marker image for click location
function createPulseCircle(): HTMLCanvasElement {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  
  const center = size / 2;
  
  // Outer ring
  ctx.beginPath();
  ctx.arc(center, center, 28, 0, 2 * Math.PI);
  ctx.strokeStyle = '#1976d2';
  ctx.lineWidth = 3;
  ctx.stroke();
  
  // Inner ring  
  ctx.beginPath();
  ctx.arc(center, center, 18, 0, 2 * Math.PI);
  ctx.strokeStyle = 'rgba(25, 118, 210, 0.5)';
  ctx.lineWidth = 2;
  ctx.stroke();
  
  // Center dot
  ctx.beginPath();
  ctx.arc(center, center, 4, 0, 2 * Math.PI);
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.strokeStyle = '#1976d2';
  ctx.lineWidth = 2;
  ctx.stroke();
  
  return canvas;
}

export const CesiumViewer = forwardRef<CesiumViewerHandle, CesiumViewerProps>(
  function CesiumViewer({ selectedDate, isLoading, initialBasemap = 'satellite', onMapClick, clickedPosition, colorScaleMin = -2, colorScaleMax = 35, drawingMode: _drawingMode = false, onBboxDrawn, activeVariable: _activeVariable = 'sst', visibleLayers = ['sst'], initialCamera, onCameraChange, availableDates: _availableDates, thresholdEnabled: _thresholdEnabled = false, thresholdMin: _thresholdMin = null, thresholdMax: _thresholdMax = null }, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const sstLayerRef = useRef<Cesium.ImageryLayer | null>(null);
  const dataLayersRef = useRef<Map<string, Cesium.ImageryLayer>>(new Map());
  const baseLayerRef = useRef<Cesium.ImageryLayer | null>(null);
  const labelsLayerRef = useRef<Cesium.ImageryLayer | null>(null);
  const overlayLabelsRef = useRef<Cesium.ImageryLayer | null>(null); // Independent labels overlay
  const clickMarkerRef = useRef<Cesium.Entity | null>(null);
  const layerUpdateAbortRef = useRef<AbortController | null>(null);
  const lastSstRequestRef = useRef<string>('');  // Track last SST request to prevent duplicates
  const sstRateLimitedUntilRef = useRef<number>(0);  // 429 cooldown timestamp
  const bboxEntityRef = useRef<Cesium.Entity | null>(null);
  const drawingHandlerRef = useRef<Cesium.ScreenSpaceEventHandler | null>(null);
  const onMapClickRef = useRef(onMapClick); // Store callback in ref to avoid re-creating viewer
  const onCameraChangeRef = useRef(onCameraChange); // Store callback in ref
  const [sstLayerVisible, setSstLayerVisible] = useState(true);
  const [viewerInitialized, setViewerInitialized] = useState(false);
  const [currentBasemap, setCurrentBasemap] = useState<BasemapId>(initialBasemap);
  const [internalClickedPosition, setInternalClickedPosition] = useState<{ lon: number; lat: number } | null>(null);
  const [_isDrawing, setIsDrawing] = useState(false);
  const [labelsVisible, setLabelsVisible] = useState(false);
  const drawStartRef = useRef<{ lon: number; lat: number } | null>(null);
  const isDrawingRef = useRef(false); // Ref to track drawing state for click handler

  // Keep onMapClick ref updated
  useEffect(() => {
    onMapClickRef.current = onMapClick;
  }, [onMapClick]);

  // Keep onCameraChange ref updated
  useEffect(() => {
    onCameraChangeRef.current = onCameraChange;
  }, [onCameraChange]);

  // Raise labels layer to top (called after SST layer changes)
  const raiseLabelsToTop = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    
    // Raise basemap labels if present
    if (labelsLayerRef.current) {
      viewer.imageryLayers.raiseToTop(labelsLayerRef.current);
    }
    
    // Raise independent overlay labels if present
    if (overlayLabelsRef.current) {
      viewer.imageryLayers.raiseToTop(overlayLabelsRef.current);
    }
    
    viewer.scene.requestRender();
  }, []);

  // Toggle labels overlay visibility
  const toggleLabels = useCallback(async () => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    if (labelsVisible) {
      // Hide labels
      if (overlayLabelsRef.current) {
        overlayLabelsRef.current.show = false;
      }
      if (labelsLayerRef.current) {
        labelsLayerRef.current.show = false;
      }
      setLabelsVisible(false);
    } else {
      // Show labels - create overlay if doesn't exist
      if (!overlayLabelsRef.current) {
        try {
          const labelsProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
            'https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer'
          );
          overlayLabelsRef.current = viewer.imageryLayers.addImageryProvider(labelsProvider);
          viewer.imageryLayers.raiseToTop(overlayLabelsRef.current);
        } catch (error) {
          console.error('Failed to load labels overlay:', error);
          return;
        }
      } else {
        overlayLabelsRef.current.show = true;
      }
      if (labelsLayerRef.current) {
        labelsLayerRef.current.show = true;
      }
      setLabelsVisible(true);
    }
    viewer.scene.requestRender();
  }, [labelsVisible]);

  // Change basemap
  const handleSetBasemap = useCallback(async (id: BasemapId) => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    try {
      // Remove old base and labels layers
      if (baseLayerRef.current) {
        viewer.imageryLayers.remove(baseLayerRef.current);
        baseLayerRef.current = null;
      }
      if (labelsLayerRef.current) {
        viewer.imageryLayers.remove(labelsLayerRef.current);
        labelsLayerRef.current = null;
      }

      // Create and add new base layers
      const newLayers = await createBasemapLayers(id, viewer.imageryLayers);
      if (viewer && !viewer.isDestroyed()) {
        baseLayerRef.current = newLayers[0] || null;
        labelsLayerRef.current = newLayers[1] || null;
        
        // Respect current labels visibility state
        if (labelsLayerRef.current) {
          labelsLayerRef.current.show = labelsVisible;
        }
        
        // Ensure labels are on top
        raiseLabelsToTop();
        
        setCurrentBasemap(id);
        viewer.scene.requestRender();
      }
    } catch (error) {
      console.error('Failed to load basemap:', id, error);
    }
  }, [raiseLabelsToTop, labelsVisible]);

  // Start bounding box drawing mode
  const startBboxDrawing = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    
    setIsDrawing(true);
    isDrawingRef.current = true;
    drawStartRef.current = null;
    
    // Remove existing bbox entity
    if (bboxEntityRef.current) {
      viewer.entities.remove(bboxEntityRef.current);
      bboxEntityRef.current = null;
    }
    
    // Create new handler for drawing
    if (drawingHandlerRef.current) {
      drawingHandlerRef.current.destroy();
    }
    
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    drawingHandlerRef.current = handler;
    
    // First click - set start point
    handler.setInputAction((click: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
      const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
      if (cartesian) {
        const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
        const lon = Cesium.Math.toDegrees(cartographic.longitude);
        const lat = Cesium.Math.toDegrees(cartographic.latitude);
        
        if (!drawStartRef.current) {
          // First click - start drawing
          drawStartRef.current = { lon, lat };
          
          // Create rectangle entity
          bboxEntityRef.current = viewer.entities.add({
            rectangle: {
              coordinates: new Cesium.CallbackProperty(() => {
                if (!drawStartRef.current) return null;
                const start = drawStartRef.current;
                const end = drawStartRef.current; // Will be updated by mouse move
                return Cesium.Rectangle.fromDegrees(
                  Math.min(start.lon, end.lon),
                  Math.min(start.lat, end.lat),
                  Math.max(start.lon, end.lon),
                  Math.max(start.lat, end.lat)
                );
              }, false),
              material: Cesium.Color.fromCssColorString('#6EF2FC').withAlpha(0.2),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString('#6EF2FC'),
              outlineWidth: 2,
            },
          });
        } else {
          // Second click - finish drawing
          const start = drawStartRef.current;
          const bbox: BoundingBox = {
            north: Math.max(start.lat, lat),
            south: Math.min(start.lat, lat),
            east: Math.max(start.lon, lon),
            west: Math.min(start.lon, lon),
          };
          
          // Finalize rectangle
          if (bboxEntityRef.current) {
            viewer.entities.remove(bboxEntityRef.current);
            bboxEntityRef.current = viewer.entities.add({
              rectangle: {
                coordinates: Cesium.Rectangle.fromDegrees(bbox.west, bbox.south, bbox.east, bbox.north),
                material: Cesium.Color.fromCssColorString('#6EF2FC').withAlpha(0.2),
                outline: true,
                outlineColor: Cesium.Color.fromCssColorString('#6EF2FC'),
                outlineWidth: 2,
              },
            });
          }
          
          setIsDrawing(false);          isDrawingRef.current = false;          drawStartRef.current = null;
          handler.destroy();
          drawingHandlerRef.current = null;
          
          if (onBboxDrawn) {
            onBboxDrawn(bbox);
          }
        }
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    
    // Mouse move - update rectangle preview
    handler.setInputAction((movement: Cesium.ScreenSpaceEventHandler.MotionEvent) => {
      if (!drawStartRef.current || !bboxEntityRef.current) return;
      
      const cartesian = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
      if (cartesian) {
        const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
        const endLon = Cesium.Math.toDegrees(cartographic.longitude);
        const endLat = Cesium.Math.toDegrees(cartographic.latitude);
        const start = drawStartRef.current;
        
        // Update rectangle using CallbackProperty by storing end position
        const rect = bboxEntityRef.current.rectangle;
        if (rect) {
          rect.coordinates = new Cesium.ConstantProperty(
            Cesium.Rectangle.fromDegrees(
              Math.min(start.lon, endLon),
              Math.min(start.lat, endLat),
              Math.max(start.lon, endLon),
              Math.max(start.lat, endLat)
            )
          );
        }
        viewer.scene.requestRender();
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
    
    // Right click or escape - cancel
    handler.setInputAction(() => {
      cancelBboxDrawingInternal();
    }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);
  }, [onBboxDrawn]);
  
  // Cancel bounding box drawing
  const cancelBboxDrawingInternal = useCallback(() => {
    const viewer = viewerRef.current;
    setIsDrawing(false);
    isDrawingRef.current = false;
    drawStartRef.current = null;
    
    if (drawingHandlerRef.current) {
      drawingHandlerRef.current.destroy();
      drawingHandlerRef.current = null;
    }
    
    if (viewer && !viewer.isDestroyed() && bboxEntityRef.current) {
      viewer.entities.remove(bboxEntityRef.current);
      bboxEntityRef.current = null;
    }
  }, []);

  // Expose viewer and controls via ref
  useImperativeHandle(ref, () => ({
    get viewer() {
      return viewerRef.current;
    },
    sstLayerVisible,
    toggleSSTLayer: () => {
      if (sstLayerRef.current) {
        sstLayerRef.current.show = !sstLayerRef.current.show;
        setSstLayerVisible(sstLayerRef.current.show);
        viewerRef.current?.scene.requestRender();
      }
    },
    currentBasemap,
    setBasemap: handleSetBasemap,
    setClickedPosition: (position: { lon: number; lat: number } | null) => {
      setInternalClickedPosition(position);
    },
    startBboxDrawing,
    cancelBboxDrawing: cancelBboxDrawingInternal,
    labelsVisible,
    toggleLabels,
    flyHome: () => {
      const viewer = viewerRef.current;
      if (!viewer || viewer.isDestroyed()) return;
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(0, 20, 25000000),
        orientation: {
          heading: Cesium.Math.toRadians(0),
          pitch: Cesium.Math.toRadians(-90),
          roll: 0,
        },
        duration: 1.5,
      });
    },
  }), [sstLayerVisible, viewerInitialized, currentBasemap, handleSetBasemap, startBboxDrawing, cancelBboxDrawingInternal, labelsVisible, toggleLabels]);

  // Manage click marker entity
  useEffect(() => {
    const viewer = viewerRef.current;
    const position = clickedPosition ?? internalClickedPosition;
    
    if (!viewer || viewer.isDestroyed()) return;
    
    // Remove existing marker
    if (clickMarkerRef.current) {
      viewer.entities.remove(clickMarkerRef.current);
      clickMarkerRef.current = null;
    }
    
    // Add new marker if position exists
    if (position) {
      const entity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(position.lon, position.lat, 100),
        point: {
          pixelSize: 14,
          color: Cesium.Color.fromCssColorString('#ffffff'),
          outlineColor: Cesium.Color.fromCssColorString('#1976d2'),
          outlineWidth: 3,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        // Add a pulsing billboard for better visibility
        billboard: {
          image: createPulseCircle(),
          scale: 0.5,
          color: Cesium.Color.fromCssColorString('#1976d2').withAlpha(0.6),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      clickMarkerRef.current = entity;
      viewer.scene.requestRender();
    }
    
    return () => {
      if (clickMarkerRef.current && viewer && !viewer.isDestroyed()) {
        viewer.entities.remove(clickMarkerRef.current);
        clickMarkerRef.current = null;
      }
    };
  }, [clickedPosition, internalClickedPosition, viewerInitialized]);

  // Initialize Cesium viewer
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    const viewer = new Cesium.Viewer(containerRef.current, {
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      animation: false,
      timeline: false,
      fullscreenButton: false,
      vrButton: false,
      geocoder: false,
      homeButton: false,
      infoBox: false,
      sceneModePicker: false,
      selectionIndicator: false,
      navigationHelpButton: false,
      baseLayerPicker: false,
      baseLayer: false,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
    });

    // Performance & rendering settings
    viewer.scene.fog.enabled = false;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.globe.baseColor = Cesium.Color.BLACK; // Neutral background for unrendered areas
    if (viewer.scene.skyAtmosphere) {
      viewer.scene.skyAtmosphere.show = false;
    }

    // Add initial basemap (with labels hidden by default)
    createBasemapLayers(initialBasemap, viewer.imageryLayers).then((layers) => {
      if (viewer && !viewer.isDestroyed()) {
        baseLayerRef.current = layers[0] || null;
        labelsLayerRef.current = layers[1] || null;
        
        // Hide labels by default (user can toggle with labels button)
        if (labelsLayerRef.current) {
          labelsLayerRef.current.show = false;
        }
        
        // Ensure base layer stays at index 0 beneath all data overlays
        if (baseLayerRef.current) {
          viewer.imageryLayers.lowerToBottom(baseLayerRef.current);
        }
        
        viewer.scene.requestRender();
      }
    });

    // Set initial view - use initialCamera from URL or default global ocean perspective
    const initialLon = initialCamera?.lon ?? 0;
    const initialLat = initialCamera?.lat ?? 20;
    const initialHeight = initialCamera?.height ?? 15000000;
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(initialLon, initialLat, initialHeight),
      orientation: {
        heading: Cesium.Math.toRadians(0),
        pitch: Cesium.Math.toRadians(-90), // Top-down view
        roll: 0,
      },
    });

    // Limit zoom range - no Star Trek views
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = 50000;    // 50km minimum
    viewer.scene.screenSpaceCameraController.maximumZoomDistance = 12000000; // 12,000km max (roughly Earth diameter)

    // Set camera change percentage for smoother updates
    viewer.camera.percentageChanged = 0.1; // Fire changed event when camera moves 10%

    // Camera move listener - update URL when camera stops moving
    const cameraListener = () => {
      if (viewer.isDestroyed()) return;
      const cartographic = viewer.camera.positionCartographic;
      const lon = Cesium.Math.toDegrees(cartographic.longitude);
      const lat = Cesium.Math.toDegrees(cartographic.latitude);
      const height = cartographic.height;
      if (onCameraChangeRef.current) {
        onCameraChangeRef.current(lon, lat, height);
      }
    };
    viewer.camera.moveEnd.addEventListener(cameraListener);

    // Click handler for SST point queries
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click: Cesium.ScreenSpaceEventHandler.PositionedEvent) => {
      // Skip if in drawing mode
      if (isDrawingRef.current) return;
      
      const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
      if (cartesian) {
        const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
        const lon = Cesium.Math.toDegrees(cartographic.longitude);
        const lat = Cesium.Math.toDegrees(cartographic.latitude);
        if (onMapClickRef.current) {
          onMapClickRef.current(lon, lat);
        }
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    viewerRef.current = viewer;
    setViewerInitialized(true);

    return () => {
      viewer.camera.moveEnd.removeEventListener(cameraListener);
      handler.destroy();
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
      sstLayerRef.current = null;
    };
  }, []); // Empty deps - viewer should only be created once

  // Resize handler
  useEffect(() => {
    const container = containerRef.current;
    const viewer = viewerRef.current;
    if (!container || !viewer) return;

    const resize = () => {
      if (viewer.isDestroyed()) return;
      viewer.resize();
      viewer.scene.requestRender();
    };

    resize();

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => resize());
      resizeObserver.observe(container);
    } else {
      window.addEventListener('resize', resize);
    }

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener('resize', resize);
    };
  }, []);

  // Update data layer (SST/SIC/SLA) when date or variable changes
  const updateDataLayers = useCallback(async (date: string, layers: string[]) => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    // Abort any in-flight layer update
    if (layerUpdateAbortRef.current) {
      layerUpdateAbortRef.current.abort();
    }
    const abortController = new AbortController();
    layerUpdateAbortRef.current = abortController;

    const currentLayerIds = new Set(dataLayersRef.current.keys());
    const targetLayerIds = new Set(layers);
    
    // Remove layers that are no longer visible
    for (const layerId of currentLayerIds) {
      if (!targetLayerIds.has(layerId)) {
        const layer = dataLayersRef.current.get(layerId);
        if (layer) {
          viewer.imageryLayers.remove(layer);
          dataLayersRef.current.delete(layerId);
        }
      }
    }
    
    // Add layers that are newly visible
    for (const variable of layers) {
      // Check abort before each async iteration
      if (abortController.signal.aborted) return;

      // Check if layer exists in ref AND is still in viewer
      const existingLayer = dataLayersRef.current.get(variable);
      if (existingLayer) {
        // Verify it's still in the viewer
        let stillInViewer = false;
        for (let i = 0; i < viewer.imageryLayers.length; i++) {
          if (viewer.imageryLayers.get(i) === existingLayer) {
            stillInViewer = true;
            break;
          }
        }
        if (stillInViewer) {
          continue;
        } else {
          dataLayersRef.current.delete(variable);
        }
      }
      
      // SST: load date-specific PNG from NOAA OPeNDAP backend
      if (variable === 'sst' && viewer && !viewer.isDestroyed() && !abortController.signal.aborted) {
        // Request deduplication: skip if same date+variable already requested
        const requestKey = `sst:${date}`;
        if (lastSstRequestRef.current === requestKey) {
          continue;
        }

        // 429 cooldown: skip if rate limited
        if (Date.now() < sstRateLimitedUntilRef.current) {
          console.warn('[YARA SST] Rate limited — skipping SST request until cooldown expires.');
          continue;
        }

        // Use selected date in URL — no cache-buster needed (date IS the cache key)
        const imageUrl = `/opendap/sst/${date}.png`;
        
        try {
          const provider = await Cesium.SingleTileImageryProvider.fromUrl(imageUrl, {
            rectangle: Cesium.Rectangle.fromDegrees(
              SST_BOUNDS.west,
              SST_BOUNDS.south,
              SST_BOUNDS.east,
              SST_BOUNDS.north
            ),
          });

          if (viewer && !viewer.isDestroyed() && !abortController.signal.aborted) {
            const layer = viewer.imageryLayers.addImageryProvider(provider);
            layer.show = true;
            layer.alpha = 1.0;
            layer.brightness = 1.0;
            layer.contrast = 1.0;
            
            viewer.imageryLayers.raiseToTop(layer);
            dataLayersRef.current.set(variable, layer);
            lastSstRequestRef.current = requestKey;
            console.log(`[YARA SST] Loaded SST for ${date} on globe.`);
          }
        } catch (err: unknown) {
          // Check for 429 rate limit
          const errMsg = String(err);
          if (errMsg.includes('429') || errMsg.includes('Too Many')) {
            sstRateLimitedUntilRef.current = Date.now() + 300_000; // 5 min cooldown
            console.error('[YARA SST] NOAA rate limited (429). Stopping SST requests for 5 minutes.');
          } else {
            console.error(`[YARA SST] Failed to load SST for ${date}:`, err);
          }
          // Do NOT retry — keep basemap visible
        }
        continue;
      }
    }
    
    // Also update legacy ref for compatibility
    sstLayerRef.current = dataLayersRef.current.get('sst') || null;
    
    // Raise labels to top so they're visible over data layers
    raiseLabelsToTop();
    
    // Check viewer is still valid after async operations
    if (viewer && !viewer.isDestroyed()) {
      viewer.scene.requestRender();
    }
  }, [raiseLabelsToTop]);

  // Update layers when date, color scale, or visibleLayers changes
  const prevDateRef = useRef<string>('');
  const prevSstScaleRef = useRef<{ min: number; max: number }>({ min: colorScaleMin, max: colorScaleMax });
  
  useEffect(() => {
    if (!selectedDate || isLoading) return;
    
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    
    // Clear all layers if date changed
    if (prevDateRef.current !== selectedDate) {
      for (const [_layerId, layer] of dataLayersRef.current) {
        viewer.imageryLayers.remove(layer);
      }
      dataLayersRef.current.clear();
      prevDateRef.current = selectedDate;
    }
    
    // Clear SST layer if color scale changed (for live updates)
    if (prevSstScaleRef.current.min !== colorScaleMin || prevSstScaleRef.current.max !== colorScaleMax) {
      const sstLayer = dataLayersRef.current.get('sst');
      if (sstLayer) {
        viewer.imageryLayers.remove(sstLayer);
        dataLayersRef.current.delete('sst');
      }
      prevSstScaleRef.current = { min: colorScaleMin, max: colorScaleMax };
    }
    
    updateDataLayers(selectedDate, visibleLayers);
  }, [selectedDate, isLoading, updateDataLayers, visibleLayers]);

  return (
    <div 
      ref={containerRef} 
      style={{ 
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
      }}
    />
  );
});



