import {
  useEffect,
  useRef,
  useCallback,
  useImperativeHandle,
  forwardRef,
  useState,
} from 'react';

import * as Cesium from 'cesium';
import { DatasetInfo, AnalysisOptions } from '../types/dataset';
import { getLocalFrameUrl } from '../services/localDatasetApi';
import { fetchOnlineFrame } from '../api/onlineApi';
import { GridOverlay } from './GridOverlay';
import 'cesium/Build/Cesium/Widgets/widgets.css';

// ============================================================================
// BASEMAP CONFIGURATION
// ============================================================================

export type BasemapId =
  | 'ocean'
  | 'esri-ocean'
  | 'satellite'
  | 's2-cloudless'
  | 'light'
  | 'streets'
  | 'dark';

export interface BasemapConfig {
  id: BasemapId;
  name: string;
  description: string;
}

export const BASEMAPS: BasemapConfig[] = [
  {
    id: 'ocean',
    name: 'Ocean',
    description: 'MapTiler bathymetry',
  },
  {
    id: 'esri-ocean',
    name: 'ESRI Ocean',
    description: 'ESRI bathymetry',
  },
  {
    id: 'satellite',
    name: 'Satellite',
    description: 'Satellite imagery',
  },
  {
    id: 's2-cloudless',
    name: 'S2 Cloudless',
    description: 'Sentinel-2 cloudless',
  },
  {
    id: 'light',
    name: 'Light Gray',
    description: 'Minimal with labels',
  },
  {
    id: 'streets',
    name: 'Streets',
    description: 'Detailed street map',
  },
  {
    id: 'dark',
    name: 'Dark Gray',
    description: 'Dark minimal',
  },
];

// ============================================================================
// PUBLIC HANDLE
// ============================================================================

export interface CesiumViewerHandle {
  viewer: Cesium.Viewer | null;
  sstLayerVisible: boolean;
  toggleSSTLayer: () => void;
  currentBasemap: BasemapId;
  setBasemap: (id: BasemapId) => void;
  setClickedPosition: (
    position: { lon: number; lat: number } | null
  ) => void;
  startBboxDrawing: () => void;
  cancelBboxDrawing: () => void;
  labelsVisible: boolean;
  toggleLabels: () => void;
  flyHome: () => void;
}

// ============================================================================
// TYPES
// ============================================================================

export interface BoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

interface CesiumViewerProps {
  selectedDate: string;

  isLoading: boolean;

  initialBasemap?: BasemapId;

  onMapClick?: (lon: number, lat: number) => void;

  clickedPosition?: {
    lon: number;
    lat: number;
  } | null;

  colorScaleMin?: number;
  colorScaleMax?: number;

  drawingMode?: boolean;

  onBboxDrawn?: (bbox: BoundingBox) => void;

  activeVariable?: string;

  visibleLayers?: string[];

  initialCamera?: {
    lon: number;
    lat: number;
    height: number;
  };

  onCameraChange?: (
    lon: number,
    lat: number,
    height: number
  ) => void;

  availableDates?: string[];

  thresholdEnabled?: boolean;
  thresholdMin?: number | null;
  thresholdMax?: number | null;

  // Local Dataset
  activeMode?: 'online' | 'local';

  activeDataset?: DatasetInfo | null;

  localVariable?: string;

  localTimeIndex?: number;

  localAnalysis?: AnalysisOptions;

  localGridEnabled?: boolean;

  colormap?: string;

  // Online OPeNDAP
  onlineVariable?: string;

  onlineDatasetId?: string;

  onlineDate?: string;

  onFrameLoadingChange?: (
    loading: boolean,
    error?: string | null,
    stage?: 'connecting' | 'receiving' | 'generating' | 'loading' | 'updating'
  ) => void;

  onScreenPositionChange?: (pos: { x: number; y: number } | null) => void;

  // Argo / Glider overlay (independent CustomDataSource entities added by
  // ArgoGliderOverlay). Picking is handled here so it can take priority
  // over the existing ocean-grid click without altering that click's
  // own logic below.
  onArgoGliderPick?: (
    kind: 'argo' | 'glider',
    properties: Record<string, unknown>
  ) => void;

}

// ============================================================================
// MAPTILER KEY
// ============================================================================

function getMapTilerKey(): string {
  const raw = import.meta.env.VITE_MAPTILER_API_KEY || '';

  return raw.replace(/['"]/g, '').trim();
}

// ============================================================================
// CREATE BASEMAP
// ============================================================================

async function createBasemapLayers(
  id: BasemapId,
  imageryLayers: Cesium.ImageryLayerCollection
): Promise<Cesium.ImageryLayer[]> {
  const layers: Cesium.ImageryLayer[] = [];

  const apiKey = getMapTilerKey();

  switch (id) {
    case 'satellite': {
      const satelliteBase =
        new Cesium.UrlTemplateImageryProvider({
          url: `https://api.maptiler.com/maps/satellite-v4/{z}/{x}/{y}.jpg?key=${apiKey}`,
          credit: 'MapTiler',
          minimumLevel: 0,
          maximumLevel: 20,
          tileWidth: 512,
          tileHeight: 512,
        });

      satelliteBase.errorEvent.addEventListener((err) => {
        console.warn(
          'MapTiler satellite imagery unavailable:',
          err
        );
      });

      layers.push(
        imageryLayers.addImageryProvider(
          satelliteBase,
          0
        )
      );

      break;
    }

    case 's2-cloudless': {
      const s2Cloudless =
        new Cesium.UrlTemplateImageryProvider({
          url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg',
          credit:
            'Sentinel-2 cloudless by EOX - CC BY-NC-SA 4.0',
          maximumLevel: 15,
        });

      layers.push(
        imageryLayers.addImageryProvider(
          s2Cloudless,
          0
        )
      );

      break;
    }

    case 'ocean': {
      const oceanMap =
        new Cesium.UrlTemplateImageryProvider({
          url: `https://api.maptiler.com/maps/ocean/{z}/{x}/{y}.png?key=${apiKey}`,
          credit: 'MapTiler',
          minimumLevel: 0,
          maximumLevel: 20,
          tileWidth: 512,
          tileHeight: 512,
        });

      oceanMap.errorEvent.addEventListener((err) => {
        console.warn(
          'MapTiler ocean imagery unavailable:',
          err
        );
      });

      layers.push(
        imageryLayers.addImageryProvider(
          oceanMap,
          0
        )
      );

      break;
    }

    case 'esri-ocean': {
      const oceanBase =
        await Cesium.ArcGisMapServerImageryProvider.fromUrl(
          'https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer'
        );

      layers.push(
        imageryLayers.addImageryProvider(
          oceanBase,
          0
        )
      );

      const oceanRef =
        await Cesium.ArcGisMapServerImageryProvider.fromUrl(
          'https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Reference/MapServer'
        );

      layers.push(
        imageryLayers.addImageryProvider(
          oceanRef,
          1
        )
      );

      break;
    }

    case 'light': {
      const lightMap =
        new Cesium.UrlTemplateImageryProvider({
          url: `https://api.maptiler.com/maps/streets-v2-light/{z}/{x}/{y}.png?key=${apiKey}`,
          credit: 'MapTiler',
          minimumLevel: 0,
          maximumLevel: 20,
          tileWidth: 512,
          tileHeight: 512,
        });

      lightMap.errorEvent.addEventListener((err) => {
        console.warn(
          'MapTiler light imagery unavailable:',
          err
        );
      });

      layers.push(
        imageryLayers.addImageryProvider(
          lightMap,
          0
        )
      );

      break;
    }

    case 'streets': {
      const streetsMap =
        new Cesium.UrlTemplateImageryProvider({
          url: `https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=${apiKey}`,
          credit: 'MapTiler',
          minimumLevel: 0,
          maximumLevel: 20,
          tileWidth: 512,
          tileHeight: 512,
        });

      streetsMap.errorEvent.addEventListener((err) => {
        console.warn(
          'MapTiler streets imagery unavailable:',
          err
        );
      });

      layers.push(
        imageryLayers.addImageryProvider(
          streetsMap,
          0
        )
      );

      break;
    }

    case 'dark': {
      const darkMap =
        new Cesium.UrlTemplateImageryProvider({
          url: `https://api.maptiler.com/maps/streets-v2-dark/{z}/{x}/{y}.png?key=${apiKey}`,
          credit: 'MapTiler',
          minimumLevel: 0,
          maximumLevel: 20,
          tileWidth: 512,
          tileHeight: 512,
        });

      darkMap.errorEvent.addEventListener((err) => {
        console.warn(
          'MapTiler dark imagery unavailable:',
          err
        );
      });

      layers.push(
        imageryLayers.addImageryProvider(
          darkMap,
          0
        )
      );

      break;
    }

    default: {
      const defaultMap =
        new Cesium.UrlTemplateImageryProvider({
          url: `https://api.maptiler.com/maps/satellite-v4/{z}/{x}/{y}.jpg?key=${apiKey}`,
          credit: 'MapTiler',
          minimumLevel: 0,
          maximumLevel: 20,
          tileWidth: 512,
          tileHeight: 512,
        });

      defaultMap.errorEvent.addEventListener((err) => {
        console.warn(
          'MapTiler default imagery unavailable:',
          err
        );
      });

      layers.push(
        imageryLayers.addImageryProvider(
          defaultMap,
          0
        )
      );
    }
  }

  return layers;
}

// ============================================================================
// CLICK MARKER
// ============================================================================

function createPulseCircle(): HTMLCanvasElement {
  const size = 64;

  const canvas = document.createElement('canvas');

  canvas.width = size;
  canvas.height = size;

  const ctx = canvas.getContext('2d');

  if (!ctx) {
    return canvas;
  }

  const center = size / 2;

  // Outer ring
  ctx.beginPath();

  ctx.arc(
    center,
    center,
    28,
    0,
    2 * Math.PI
  );

  ctx.strokeStyle = '#1976d2';
  ctx.lineWidth = 3;

  ctx.stroke();

  // Inner ring
  ctx.beginPath();

  ctx.arc(
    center,
    center,
    18,
    0,
    2 * Math.PI
  );

  ctx.strokeStyle =
    'rgba(25, 118, 210, 0.5)';

  ctx.lineWidth = 2;

  ctx.stroke();

  // Center dot
  ctx.beginPath();

  ctx.arc(
    center,
    center,
    4,
    0,
    2 * Math.PI
  );

  ctx.fillStyle = '#ffffff';

  ctx.fill();

  ctx.strokeStyle = '#1976d2';

  ctx.lineWidth = 2;

  ctx.stroke();

  return canvas;
}

// ============================================================================
// CESIUM VIEWER
// ============================================================================

export const CesiumViewer = forwardRef<
  CesiumViewerHandle,
  CesiumViewerProps
>(
  function CesiumViewer(
    {
      selectedDate,
      isLoading,

      initialBasemap = 'satellite',

      onMapClick,
      clickedPosition,

      colorScaleMin = -2,
      colorScaleMax = 35,

      drawingMode: _drawingMode = false,

      onBboxDrawn,

      activeVariable: _activeVariable = 'sst',

      visibleLayers = ['sst'],

      initialCamera,

      onCameraChange,

      availableDates: _availableDates,

      thresholdEnabled: _thresholdEnabled = false,
      thresholdMin: _thresholdMin = null,
      thresholdMax: _thresholdMax = null,

      activeMode = 'online',

      activeDataset = null,

      localVariable,

      localTimeIndex = 0,

      localAnalysis,

      localGridEnabled = false,

      colormap,

      onlineVariable = '',

      onlineDatasetId = '',

      onlineDate = 'latest',

      onFrameLoadingChange,

      onArgoGliderPick,

      onScreenPositionChange,

    },
    ref
  ) {
    // ========================================================================
    // REFS
    // ========================================================================

    const containerRef =
      useRef<HTMLDivElement>(null);

    const viewerRef =
      useRef<Cesium.Viewer | null>(null);

    const sstLayerRef =
      useRef<Cesium.ImageryLayer | null>(null);

    const dataLayersRef =
      useRef<
        Map<string, Cesium.ImageryLayer>
      >(new Map());

    const baseLayerRef =
      useRef<Cesium.ImageryLayer | null>(null);

    const labelsLayerRef =
      useRef<Cesium.ImageryLayer | null>(null);

    const overlayLabelsRef =
      useRef<Cesium.ImageryLayer | null>(null);

    const clickMarkerRef =
      useRef<Cesium.Entity | null>(null);

    // Current active request
    const layerUpdateAbortRef =
      useRef<AbortController | null>(null);

    // Currently displayed blob URL
    const currentBlobUrlRef =
      useRef<string | null>(null);

    // Last successfully rendered request
    const lastSstRequestRef =
      useRef<string>('');

    // Current request being downloaded
    const inFlightOnlineRequestRef =
      useRef<string | null>(null);

    // Rate-limit cooldown
    const sstRateLimitedUntilRef =
      useRef<number>(0);

    // Bounding box
    const bboxEntityRef =
      useRef<Cesium.Entity | null>(null);

    const drawingHandlerRef =
      useRef<Cesium.ScreenSpaceEventHandler | null>(
        null
      );

    const drawStartRef =
      useRef<{
        lon: number;
        lat: number;
      } | null>(null);

    const isDrawingRef =
      useRef(false);


    // Callback refs
    const onMapClickRef =
      useRef(onMapClick);

    const onCameraChangeRef =
      useRef(onCameraChange);

    const onArgoGliderPickRef =
      useRef(onArgoGliderPick);

    // ========================================================================
    // STATE
    // ========================================================================

    const [sstLayerVisible, setSstLayerVisible] =
      useState(true);

    const [viewerInitialized, setViewerInitialized] =
      useState(false);

    const [currentBasemap, setCurrentBasemap] =
      useState<BasemapId>(initialBasemap);

    const [
      internalClickedPosition,
      setInternalClickedPosition,
    ] = useState<{
      lon: number;
      lat: number;
    } | null>(null);

    const [_isDrawing, setIsDrawing] =
      useState(false);

    const [labelsVisible, setLabelsVisible] =
      useState(false);

    // ========================================================================
    // CALLBACK REFS
    // ========================================================================

    useEffect(() => {
      onMapClickRef.current = onMapClick;
    }, [onMapClick]);

    useEffect(() => {
      onArgoGliderPickRef.current = onArgoGliderPick;
    }, [onArgoGliderPick]);

    useEffect(() => {
      onCameraChangeRef.current =
        onCameraChange;
    }, [onCameraChange]);

    // ========================================================================
    // RAISE LABELS
    // ========================================================================

    const raiseLabelsToTop =
      useCallback(() => {
        const viewer = viewerRef.current;

        if (
          !viewer ||
          viewer.isDestroyed()
        ) {
          return;
        }

        if (labelsLayerRef.current) {
          viewer.imageryLayers.raiseToTop(
            labelsLayerRef.current
          );
        }

        if (overlayLabelsRef.current) {
          viewer.imageryLayers.raiseToTop(
            overlayLabelsRef.current
          );
        }

        viewer.scene.requestRender();
      }, []);

    // ========================================================================
    // TOGGLE LABELS
    // ========================================================================

    const toggleLabels =
      useCallback(async () => {
        const viewer = viewerRef.current;

        if (
          !viewer ||
          viewer.isDestroyed()
        ) {
          return;
        }

        if (labelsVisible) {
          if (overlayLabelsRef.current) {
            overlayLabelsRef.current.show =
              false;
          }

          if (labelsLayerRef.current) {
            labelsLayerRef.current.show =
              false;
          }

          setLabelsVisible(false);
        } else {
          if (!overlayLabelsRef.current) {
            try {
              const labelsProvider =
                await Cesium.ArcGisMapServerImageryProvider.fromUrl(
                  'https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer'
                );

              if (
                !viewerRef.current ||
                viewerRef.current.isDestroyed()
              ) {
                return;
              }

              overlayLabelsRef.current =
                viewer.imageryLayers.addImageryProvider(
                  labelsProvider
                );

              viewer.imageryLayers.raiseToTop(
                overlayLabelsRef.current
              );
            } catch (error) {
              console.error(
                'Failed to load labels overlay:',
                error
              );

              return;
            }
          } else {
            overlayLabelsRef.current.show =
              true;
          }

          if (labelsLayerRef.current) {
            labelsLayerRef.current.show =
              true;
          }

          setLabelsVisible(true);
        }

        viewer.scene.requestRender();
      }, [labelsVisible]);

    // ========================================================================
    // SET BASEMAP
    // ========================================================================

    const handleSetBasemap =
      useCallback(
        async (id: BasemapId) => {
          const viewer = viewerRef.current;

          if (
            !viewer ||
            viewer.isDestroyed()
          ) {
            return;
          }

          try {
            if (baseLayerRef.current) {
              viewer.imageryLayers.remove(
                baseLayerRef.current
              );

              baseLayerRef.current = null;
            }

            if (labelsLayerRef.current) {
              viewer.imageryLayers.remove(
                labelsLayerRef.current
              );

              labelsLayerRef.current = null;
            }

            const newLayers =
              await createBasemapLayers(
                id,
                viewer.imageryLayers
              );

            if (
              !viewerRef.current ||
              viewerRef.current.isDestroyed()
            ) {
              return;
            }

            baseLayerRef.current =
              newLayers[0] || null;

            labelsLayerRef.current =
              newLayers[1] || null;

            if (baseLayerRef.current) {
              viewer.imageryLayers.lowerToBottom(
                baseLayerRef.current
              );
            }

            if (labelsLayerRef.current) {
              labelsLayerRef.current.show =
                labelsVisible;
            }

            raiseLabelsToTop();

            setCurrentBasemap(id);

            viewer.scene.requestRender();
          } catch (error) {
            console.error(
              'Failed to load basemap:',
              id,
              error
            );
          }
        },
        [
          raiseLabelsToTop,
          labelsVisible,
        ]
      );

    // ========================================================================
    // BBOX DRAWING
    // ========================================================================

    const cancelBboxDrawingInternal =
      useCallback(() => {
        const viewer = viewerRef.current;

        setIsDrawing(false);

        isDrawingRef.current = false;

        drawStartRef.current = null;

        if (drawingHandlerRef.current) {
          drawingHandlerRef.current.destroy();

          drawingHandlerRef.current = null;
        }

        if (
          viewer &&
          !viewer.isDestroyed() &&
          bboxEntityRef.current
        ) {
          viewer.entities.remove(
            bboxEntityRef.current
          );

          bboxEntityRef.current = null;
        }
      }, []);

    const startBboxDrawing =
      useCallback(() => {
        const viewer = viewerRef.current;

        if (
          !viewer ||
          viewer.isDestroyed()
        ) {
          return;
        }

        setIsDrawing(true);

        isDrawingRef.current = true;

        drawStartRef.current = null;

        if (bboxEntityRef.current) {
          viewer.entities.remove(
            bboxEntityRef.current
          );

          bboxEntityRef.current = null;
        }

        if (drawingHandlerRef.current) {
          drawingHandlerRef.current.destroy();
        }

        const handler =
          new Cesium.ScreenSpaceEventHandler(
            viewer.scene.canvas
          );

        drawingHandlerRef.current =
          handler;

        // --------------------------------------------------------------------
        // LEFT CLICK
        // --------------------------------------------------------------------

        handler.setInputAction(
          (
            click: Cesium.ScreenSpaceEventHandler.PositionedEvent
          ) => {
            const cartesian =
              viewer.camera.pickEllipsoid(
                click.position,
                viewer.scene.globe.ellipsoid
              );

            if (!cartesian) {
              return;
            }

            const cartographic =
              Cesium.Cartographic.fromCartesian(
                cartesian
              );

            const lon =
              Cesium.Math.toDegrees(
                cartographic.longitude
              );

            const lat =
              Cesium.Math.toDegrees(
                cartographic.latitude
              );

            if (!drawStartRef.current) {
              drawStartRef.current = {
                lon,
                lat,
              };

              bboxEntityRef.current =
                viewer.entities.add({
                  rectangle: {
                    coordinates:
                      Cesium.Rectangle.fromDegrees(
                        lon,
                        lat,
                        lon,
                        lat
                      ),

                    material:
                      Cesium.Color.fromCssColorString(
                        '#6EF2FC'
                      ).withAlpha(0.2),

                    outline: true,

                    outlineColor:
                      Cesium.Color.fromCssColorString(
                        '#6EF2FC'
                      ),

                    outlineWidth: 2,
                  },
                });
            } else {
              const start =
                drawStartRef.current;

              const bbox: BoundingBox = {
                north: Math.max(
                  start.lat,
                  lat
                ),

                south: Math.min(
                  start.lat,
                  lat
                ),

                east: Math.max(
                  start.lon,
                  lon
                ),

                west: Math.min(
                  start.lon,
                  lon
                ),
              };

              if (bboxEntityRef.current) {
                viewer.entities.remove(
                  bboxEntityRef.current
                );

                bboxEntityRef.current =
                  viewer.entities.add({
                    rectangle: {
                      coordinates:
                        Cesium.Rectangle.fromDegrees(
                          bbox.west,
                          bbox.south,
                          bbox.east,
                          bbox.north
                        ),

                      material:
                        Cesium.Color.fromCssColorString(
                          '#6EF2FC'
                        ).withAlpha(0.2),

                      outline: true,

                      outlineColor:
                        Cesium.Color.fromCssColorString(
                          '#6EF2FC'
                        ),

                      outlineWidth: 2,
                    },
                  });
              }

              setIsDrawing(false);

              isDrawingRef.current =
                false;

              drawStartRef.current = null;

              handler.destroy();

              drawingHandlerRef.current =
                null;

              onBboxDrawn?.(bbox);
            }
          },
          Cesium.ScreenSpaceEventType.LEFT_CLICK
        );

        // --------------------------------------------------------------------
        // MOUSE MOVE
        // --------------------------------------------------------------------

        handler.setInputAction(
          (
            movement: Cesium.ScreenSpaceEventHandler.MotionEvent
          ) => {
            if (
              !drawStartRef.current ||
              !bboxEntityRef.current
            ) {
              return;
            }

            const cartesian =
              viewer.camera.pickEllipsoid(
                movement.endPosition,
                viewer.scene.globe.ellipsoid
              );

            if (!cartesian) {
              return;
            }

            const cartographic =
              Cesium.Cartographic.fromCartesian(
                cartesian
              );

            const endLon =
              Cesium.Math.toDegrees(
                cartographic.longitude
              );

            const endLat =
              Cesium.Math.toDegrees(
                cartographic.latitude
              );

            const start =
              drawStartRef.current;

            const rect =
              bboxEntityRef.current.rectangle;

            if (rect) {
              rect.coordinates =
                new Cesium.ConstantProperty(
                  Cesium.Rectangle.fromDegrees(
                    Math.min(
                      start.lon,
                      endLon
                    ),

                    Math.min(
                      start.lat,
                      endLat
                    ),

                    Math.max(
                      start.lon,
                      endLon
                    ),

                    Math.max(
                      start.lat,
                      endLat
                    )
                  )
                );
            }

            viewer.scene.requestRender();
          },
          Cesium.ScreenSpaceEventType.MOUSE_MOVE
        );

        // --------------------------------------------------------------------
        // RIGHT CLICK = CANCEL
        // --------------------------------------------------------------------

        handler.setInputAction(
          () => {
            cancelBboxDrawingInternal();
          },
          Cesium.ScreenSpaceEventType.RIGHT_CLICK
        );
      }, [
        cancelBboxDrawingInternal,
        onBboxDrawn,
      ]);

    // ========================================================================
    // IMPERATIVE HANDLE
    // ========================================================================

    useImperativeHandle(
      ref,
      () => ({
        get viewer() {
          return viewerRef.current;
        },

        sstLayerVisible,

        toggleSSTLayer: () => {
          if (sstLayerRef.current) {
            sstLayerRef.current.show =
              !sstLayerRef.current.show;

            setSstLayerVisible(
              sstLayerRef.current.show
            );

            viewerRef.current?.scene.requestRender();
          }
        },

        currentBasemap,

        setBasemap:
          handleSetBasemap,

        setClickedPosition: (
          position
        ) => {
          setInternalClickedPosition(
            position
          );
        },

        startBboxDrawing,

        cancelBboxDrawing:
          cancelBboxDrawingInternal,

        labelsVisible,

        toggleLabels,

        flyHome: () => {
          const viewer =
            viewerRef.current;

          if (
            !viewer ||
            viewer.isDestroyed()
          ) {
            return;
          }

          viewer.camera.flyTo({
            destination:
              Cesium.Cartesian3.fromDegrees(
                0,
                20,
                25000000
              ),

            orientation: {
              heading:
                Cesium.Math.toRadians(0),

              pitch:
                Cesium.Math.toRadians(-90),

              roll: 0,
            },

            duration: 1.5,
          });
        },
      }),
      [
        sstLayerVisible,
        currentBasemap,
        handleSetBasemap,
        startBboxDrawing,
        cancelBboxDrawingInternal,
        labelsVisible,
        toggleLabels,
      ]
    );

    // ========================================================================
    // CLICK MARKER
    // ========================================================================

    useEffect(() => {
      const viewer = viewerRef.current;

      const position =
        clickedPosition ??
        internalClickedPosition;

      if (
        !viewer ||
        viewer.isDestroyed()
      ) {
        return;
      }

      if (clickMarkerRef.current) {
        viewer.entities.remove(
          clickMarkerRef.current
        );

        clickMarkerRef.current = null;
      }

      if (position) {
        const entity =
          viewer.entities.add({
            position:
              Cesium.Cartesian3.fromDegrees(
                position.lon,
                position.lat,
                100
              ),

            point: {
              pixelSize: 14,

              color:
                Cesium.Color.fromCssColorString(
                  '#ffffff'
                ),

              outlineColor:
                Cesium.Color.fromCssColorString(
                  '#1976d2'
                ),

              outlineWidth: 3,

              heightReference:
                Cesium.HeightReference.CLAMP_TO_GROUND,

              disableDepthTestDistance:
                Number.POSITIVE_INFINITY,
            },

            billboard: {
              image:
                createPulseCircle(),

              scale: 0.5,

              color:
                Cesium.Color.fromCssColorString(
                  '#1976d2'
                ).withAlpha(0.6),

              heightReference:
                Cesium.HeightReference.CLAMP_TO_GROUND,

              disableDepthTestDistance:
                Number.POSITIVE_INFINITY,
            },
          });

        clickMarkerRef.current =
          entity;

        viewer.scene.requestRender();
      }

      return () => {
        if (
          clickMarkerRef.current &&
          viewer &&
          !viewer.isDestroyed()
        ) {
          viewer.entities.remove(
            clickMarkerRef.current
          );

          clickMarkerRef.current = null;
        }
      };
    }, [
      clickedPosition,
      internalClickedPosition,
      viewerInitialized,
    ]);

    // ========================================================================
    // DYNAMIC SCREEN POSITION TRACKING
    // Continuously projects the selected 3D point into screen coordinates.
    // Automatically hides connection line if point is occluded by Earth.
    // ========================================================================

    useEffect(() => {
      const viewer = viewerRef.current;
      if (!viewer || viewer.isDestroyed() || !viewerInitialized) return;

      const targetPos = clickedPosition ?? internalClickedPosition;
      if (!targetPos) {
        onScreenPositionChange?.(null);
        return;
      }

      const updateScreenPos = () => {
        if (!viewerRef.current || viewerRef.current.isDestroyed()) return;

        const cartesian = Cesium.Cartesian3.fromDegrees(
          targetPos.lon,
          targetPos.lat,
          100
        );

        const cameraPos = viewer.camera.position;
        const surfaceNormal = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(
          cartesian,
          new Cesium.Cartesian3()
        );
        const toCamera = Cesium.Cartesian3.subtract(
          cameraPos,
          cartesian,
          new Cesium.Cartesian3()
        );
        const isVisible = Cesium.Cartesian3.dot(surfaceNormal, toCamera) > 0;

        if (!isVisible) {
          onScreenPositionChange?.(null);
          return;
        }

        const windowPos = Cesium.SceneTransforms.worldToWindowCoordinates(
          viewer.scene,
          cartesian
        );

        if (windowPos) {
          onScreenPositionChange?.({ x: windowPos.x, y: windowPos.y });
        } else {
          onScreenPositionChange?.(null);
        }
      };

      const removeListener = viewer.scene.postRender.addEventListener(updateScreenPos);
      updateScreenPos();

      return () => {
        removeListener();
      };
    }, [
      clickedPosition,
      internalClickedPosition,
      viewerInitialized,
      onScreenPositionChange,
    ]);

    // ========================================================================
    // INITIALIZE CESIUM
    // ========================================================================

    useEffect(() => {
      if (
        !containerRef.current ||
        viewerRef.current
      ) {
        return;
      }

      const viewer =
        new Cesium.Viewer(
          containerRef.current,
          {
            terrainProvider:
              new Cesium.EllipsoidTerrainProvider(),

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

            maximumRenderTimeChange:
              Infinity,
          }
        );

      // ----------------------------------------------------------------------
      // RENDERING SETTINGS
      // ----------------------------------------------------------------------

      viewer.scene.fog.enabled =
        false;

      viewer.scene.globe.showGroundAtmosphere =
        false;

      viewer.scene.globe.baseColor =
        Cesium.Color.fromCssColorString(
          '#0b1622'
        );

      if (viewer.scene.skyAtmosphere) {
        viewer.scene.skyAtmosphere.show =
          false;
      }

      // ----------------------------------------------------------------------
      // INITIAL BASEMAP
      // ----------------------------------------------------------------------

      createBasemapLayers(
        initialBasemap,
        viewer.imageryLayers
      )
        .then((layers) => {
          if (
            viewer.isDestroyed()
          ) {
            return;
          }

          baseLayerRef.current =
            layers[0] || null;

          labelsLayerRef.current =
            layers[1] || null;

          if (labelsLayerRef.current) {
            labelsLayerRef.current.show =
              false;
          }

          if (baseLayerRef.current) {
            viewer.imageryLayers.lowerToBottom(
              baseLayerRef.current
            );
          }

          raiseLabelsToTop();

          viewer.scene.requestRender();
        })
        .catch((error) => {
          console.error(
            'Failed to initialize basemap:',
            error
          );
        });

      // ----------------------------------------------------------------------
      // INITIAL CAMERA
      // ----------------------------------------------------------------------

      const initialLon =
        initialCamera?.lon ?? 0;

      const initialLat =
        initialCamera?.lat ?? 20;

      const initialHeight =
        initialCamera?.height ?? 15000000;

      viewer.camera.setView({
        destination:
          Cesium.Cartesian3.fromDegrees(
            initialLon,
            initialLat,
            initialHeight
          ),

        orientation: {
          heading:
            Cesium.Math.toRadians(0),

          pitch:
            Cesium.Math.toRadians(-90),

          roll: 0,
        },
      });

      // ----------------------------------------------------------------------
      // CAMERA ZOOM LIMITS
      // ----------------------------------------------------------------------

      viewer.scene
        .screenSpaceCameraController
        .minimumZoomDistance = 50000;

      viewer.scene
        .screenSpaceCameraController
        .maximumZoomDistance = 12000000;

      viewer.camera.percentageChanged =
        0.1;

      // ----------------------------------------------------------------------
      // CAMERA LISTENER
      // ----------------------------------------------------------------------

      const cameraListener =
        () => {
          if (viewer.isDestroyed()) {
            return;
          }

          const cartographic =
            viewer.camera.positionCartographic;

          const lon =
            Cesium.Math.toDegrees(
              cartographic.longitude
            );

          const lat =
            Cesium.Math.toDegrees(
              cartographic.latitude
            );

          const height =
            cartographic.height;

          onCameraChangeRef.current?.(
            lon,
            lat,
            height
          );
        };

      viewer.camera.moveEnd.addEventListener(
        cameraListener
      );

      // ----------------------------------------------------------------------
      // MAP CLICK
      // ----------------------------------------------------------------------

      const handler =
        new Cesium.ScreenSpaceEventHandler(
          viewer.scene.canvas
        );

      handler.setInputAction(
        (
          click: Cesium.ScreenSpaceEventHandler.PositionedEvent
        ) => {
          if (isDrawingRef.current) {
            return;
          }

          // ------------------------------------------------------------------
          // ARGO / GLIDER ENTITY PICK
          //
          // Checked first so a click landing on an Argo/Glider marker is
          // routed to the overlay callback instead of the existing
          // ocean-grid point query below. Any other click (including one
          // that misses every entity) falls straight through unchanged.
          // ------------------------------------------------------------------
          const pickedObject = viewer.scene.pick(click.position);
          const pickedEntity =
            pickedObject && pickedObject.id instanceof Cesium.Entity
              ? (pickedObject.id as Cesium.Entity)
              : null;

          if (pickedEntity && pickedEntity.properties) {
            const entityId = String(pickedEntity.id ?? '');
            const kind = entityId.startsWith('argo-')
              ? 'argo'
              : entityId.startsWith('glider-')
              ? 'glider'
              : null;

            if (kind) {
              const props =
                pickedEntity.properties.getValue(
                  Cesium.JulianDate.now()
                ) ?? {};
              onArgoGliderPickRef.current?.(
                kind,
                props as Record<string, unknown>
              );
              return;
            }
          }

          let cartesian: Cesium.Cartesian3 | undefined = viewer.scene.pickPosition(click.position);
          if (!cartesian || !Cesium.defined(cartesian)) {
            cartesian = viewer.camera.pickEllipsoid(
              click.position,
              viewer.scene.globe.ellipsoid
            ) || undefined;
          }

          if (!cartesian) {
            return;
          }

          const cartographic =
            Cesium.Cartographic.fromCartesian(
              cartesian
            );

          const lon =
            Cesium.Math.toDegrees(
              cartographic.longitude
            );

          const lat =
            Cesium.Math.toDegrees(
              cartographic.latitude
            );

          onMapClickRef.current?.(
            lon,
            lat
          );
        },
        Cesium.ScreenSpaceEventType.LEFT_CLICK
      );

      viewerRef.current =
        viewer;

      setViewerInitialized(true);

      // ----------------------------------------------------------------------
      // CLEANUP VIEWER
      // ----------------------------------------------------------------------

      return () => {
        viewer.camera.moveEnd.removeEventListener(
          cameraListener
        );

        handler.destroy();

        if (
          drawingHandlerRef.current
        ) {
          drawingHandlerRef.current.destroy();

          drawingHandlerRef.current =
            null;
        }

        if (
          layerUpdateAbortRef.current
        ) {
          layerUpdateAbortRef.current.abort();

          layerUpdateAbortRef.current =
            null;
        }

        inFlightOnlineRequestRef.current =
          null;

        if (
          currentBlobUrlRef.current
        ) {
          URL.revokeObjectURL(
            currentBlobUrlRef.current
          );

          currentBlobUrlRef.current =
            null;
        }

        if (
          viewerRef.current &&
          !viewerRef.current.isDestroyed()
        ) {
          viewerRef.current.destroy();
        }

        viewerRef.current = null;

        sstLayerRef.current =
          null;

        dataLayersRef.current.clear();

        baseLayerRef.current =
          null;

        labelsLayerRef.current =
          null;

        overlayLabelsRef.current =
          null;

        clickMarkerRef.current =
          null;
      };
    }, []);

    // ========================================================================
    // RESIZE
    // ========================================================================

    useEffect(() => {
      const container =
        containerRef.current;

      const viewer =
        viewerRef.current;

      if (!container || !viewer) {
        return;
      }

      const resize = () => {
        if (viewer.isDestroyed()) {
          return;
        }

        viewer.resize();

        viewer.scene.requestRender();
      };

      resize();

      let resizeObserver:
        | ResizeObserver
        | null = null;

      if (
        typeof ResizeObserver !==
        'undefined'
      ) {
        resizeObserver =
          new ResizeObserver(() => {
            resize();
          });

        resizeObserver.observe(
          container
        );
      } else {
        window.addEventListener(
          'resize',
          resize
        );
      }

      return () => {
        resizeObserver?.disconnect();

        window.removeEventListener(
          'resize',
          resize
        );
      };
    }, []);

    // ========================================================================
    // UPDATE DATA LAYERS
    //
    // IMPORTANT:
    // This function intentionally does NOT abort the current request merely
    // because React rendered again.
    //
    // A request is aborted ONLY when a genuinely different request begins.
    // ========================================================================

    const updateDataLayers =
      useCallback(
        async (
          _date: string,
          layers: string[]
        ) => {
          const viewer =
            viewerRef.current;

          if (
            !viewer ||
            viewer.isDestroyed()
          ) {
            return;
          }

          // ==================================================================
          // ONLINE MODE
          // ==================================================================

          if (
            activeMode === 'online'
          ) {
            const activeOnlineVar =
              onlineVariable?.trim();

            const activeOnlineDataset = onlineDatasetId?.trim();

            const activeOnlineDate =
              onlineDate || 'latest';

            // --------------------------------------------------------------
            // No variable selected
            // --------------------------------------------------------------

            if (!activeOnlineDataset || !activeOnlineVar) {
              console.log(
                '[YARA APPLY] No online variable selected.'
              );

              return;
            }

            const activeColormap =
              colormap || 'viridis';

            const requestKey =
              `online:${activeOnlineDataset}:${activeOnlineVar}:${activeOnlineDate}:${activeColormap}:${colorScaleMin}:${colorScaleMax}`;

            console.log(
              '[YARA APPLY] Layer effect triggered:',
              {
                variable:
                  activeOnlineVar,

                date:
                  activeOnlineDate,

                requestKey,
              }
            );

            // --------------------------------------------------------------
            // ALREADY SUCCESSFULLY RENDERED
            // --------------------------------------------------------------

            if (
              lastSstRequestRef.current ===
              requestKey
            ) {
              console.log(
                `[YARA APPLY] Already rendered — skipping: ${requestKey}`
              );

              return;
            }

            // --------------------------------------------------------------
            // SAME REQUEST ALREADY FETCHING
            //
            // VERY IMPORTANT:
            // Do NOT abort it.
            // --------------------------------------------------------------

            if (
              inFlightOnlineRequestRef.current ===
              requestKey
            ) {
              console.log(
                `[YARA APPLY] Request already in flight — keeping existing request: ${requestKey}`
              );

              return;
            }

            // --------------------------------------------------------------
            // 429 COOLDOWN
            // --------------------------------------------------------------

            if (
              Date.now() <
              sstRateLimitedUntilRef.current
            ) {
              console.warn(
                '[YARA Online] Rate limited — keeping current visualization.'
              );

              return;
            }

            // --------------------------------------------------------------
            // ABORT ONLY A DIFFERENT REQUEST
            // --------------------------------------------------------------

            if (
              layerUpdateAbortRef.current
            ) {
              console.log(
                '[YARA APPLY] Aborting previous DIFFERENT request.'
              );

              layerUpdateAbortRef.current.abort();

              layerUpdateAbortRef.current =
                null;
            }

            const abortController =
              new AbortController();

            layerUpdateAbortRef.current =
              abortController;

            // --------------------------------------------------------------
            // MARK REQUEST AS IN FLIGHT BEFORE FETCH
            // --------------------------------------------------------------

            inFlightOnlineRequestRef.current =
              requestKey;

            console.log(
              '[YARA FRAME] request-start',
              {
                requestKey,
                variable: activeOnlineVar,
                date: activeOnlineDate,
                colormap: activeColormap,
                vmin: colorScaleMin,
                vmax: colorScaleMax,
              }
            );

            onFrameLoadingChange?.(
              true,
              null,
              'connecting'
            );

            let generatedBlobUrl:
              string | null = null;

            try {
              // ==============================================================
              // FETCH SCIENTIFIC DATA
              // ==============================================================

              const frameRes =
                await fetchOnlineFrame(
                  activeOnlineDataset,
                  activeOnlineVar,
                  activeOnlineDate,
                  {
                    maxPixels: 1536,

                    colormap:
                      activeColormap,

                    vmin:
                      colorScaleMin,

                    vmax:
                      colorScaleMax,
                  },
                  abortController.signal
                );

              generatedBlobUrl =
                frameRes.blobUrl;

              console.log(
                '[YARA FRAME] response-received',
                {
                  status: frameRes.status,
                  blobSize: frameRes.blobSize,
                  matchedDate: frameRes.matchedDate,
                }
              );

              console.log(
                '[YARA FRAME] blob-created',
                frameRes.blobUrl
              );

              onFrameLoadingChange?.(
                true,
                null,
                'receiving'
              );

              // ==============================================================
              // REQUEST MAY HAVE BEEN ABORTED
              // ==============================================================

              if (
                abortController.signal
                  .aborted
              ) {
                console.log(
                  `[YARA Online] Request aborted: ${requestKey}`
                );

                if (
                  generatedBlobUrl
                ) {
                  URL.revokeObjectURL(
                    generatedBlobUrl
                  );

                  generatedBlobUrl =
                    null;
                }

                if (inFlightOnlineRequestRef.current === requestKey) {
                  onFrameLoadingChange?.(false, null);
                }

                return;
              }

              // ==============================================================
              // MAKE SURE THIS IS STILL THE CURRENT REQUEST
              // ==============================================================

              if (
                inFlightOnlineRequestRef.current !==
                requestKey
              ) {
                console.log(
                  `[YARA Online] Request is no longer current — ignoring result: ${requestKey}`
                );

                if (
                  generatedBlobUrl
                ) {
                  URL.revokeObjectURL(
                    generatedBlobUrl
                  );

                  generatedBlobUrl =
                    null;
                }

                return;
              }

              if (
                !viewerRef.current ||
                viewerRef.current.isDestroyed()
              ) {
                if (
                  generatedBlobUrl
                ) {
                  URL.revokeObjectURL(
                    generatedBlobUrl
                  );

                  generatedBlobUrl =
                    null;
                }

                return;
              }

              console.log(
                '[YARA CESIUM DEBUG] FRAME RESPONSE RECEIVED',
                {
                  status:
                    frameRes.status,

                  blobSize:
                    frameRes.blobSize,

                  blobType:
                    frameRes.blobType,

                  blobUrl:
                    frameRes.blobUrl,

                  matchedDate:
                    frameRes.matchedDate,

                  bounds:
                    frameRes.bounds,
                }
              );

              // ==============================================================
              // IMAGE DECODING CHECK
              // ==============================================================

              const testImage =
                new Image();

              testImage.onload =
                () => {
                  console.log(
                    '[YARA CESIUM DEBUG] PNG IMAGE DECODING OK',
                    {
                      width:
                        testImage.naturalWidth,

                      height:
                        testImage.naturalHeight,
                    }
                  );

                  if (
                    viewerRef.current &&
                    !viewerRef.current.isDestroyed()
                  ) {
                    viewerRef.current.scene.requestRender();
                  }
                };

              testImage.onerror =
                (imgErr) => {
                  console.error(
                    '[YARA CESIUM DEBUG] PNG IMAGE DECODING FAILED',
                    imgErr
                  );
                };

              testImage.src =
                frameRes.blobUrl;

              // ==============================================================
              // CESIUM RECTANGLE
              // ==============================================================

              const rectangle =
                Cesium.Rectangle.fromDegrees(
                  frameRes.bounds.west,

                  frameRes.bounds.south,

                  frameRes.bounds.east,

                  frameRes.bounds.north
                );

              console.log(
                '[YARA CESIUM DEBUG] CREATING SINGLE TILE PROVIDER',
                {
                  west:
                    frameRes.bounds.west,

                  south:
                    frameRes.bounds.south,

                  east:
                    frameRes.bounds.east,

                  north:
                    frameRes.bounds.north,
                }
              );

              // ==============================================================
              // CREATE CESIUM PROVIDER
              // ==============================================================

              onFrameLoadingChange?.(
                true,
                null,
                'generating'
              );

              const provider =
                await Cesium.SingleTileImageryProvider.fromUrl(
                  frameRes.blobUrl,
                  {
                    rectangle,
                  }
                );

              onFrameLoadingChange?.(
                true,
                null,
                'loading'
              );

              console.log(
                '[YARA FRAME] provider-created',
                frameRes.bounds
              );

              if (viewerRef.current && !viewerRef.current.isDestroyed()) {
                viewerRef.current.scene.requestRender();
              }

              // ==============================================================
              // CHECK AGAIN AFTER PROVIDER CREATION
              // ==============================================================

              if (
                abortController.signal
                  .aborted
              ) {
                console.log(
                  '[YARA CESIUM DEBUG] ABORTED AFTER PROVIDER CREATION'
                );

                if (
                  generatedBlobUrl
                ) {
                  URL.revokeObjectURL(
                    generatedBlobUrl
                  );

                  generatedBlobUrl =
                    null;
                }

                return;
              }

              if (
                inFlightOnlineRequestRef.current !==
                requestKey
              ) {
                console.log(
                  '[YARA CESIUM DEBUG] REQUEST NO LONGER CURRENT AFTER PROVIDER CREATION'
                );

                if (
                  generatedBlobUrl
                ) {
                  URL.revokeObjectURL(
                    generatedBlobUrl
                  );

                  generatedBlobUrl =
                    null;
                }

                return;
              }

              if (
                !viewerRef.current ||
                viewerRef.current.isDestroyed()
              ) {
                if (
                  generatedBlobUrl
                ) {
                  URL.revokeObjectURL(
                    generatedBlobUrl
                  );

                  generatedBlobUrl =
                    null;
                }

                return;
              }

              console.log(
                '[YARA CESIUM DEBUG] PROVIDER READY',
                {
                  ready:
                    (
                      provider as unknown as {
                        ready?: boolean;
                      }
                    ).ready ?? true,

                  rectangle:
                    provider.rectangle,

                  tileWidth:
                    provider.tileWidth,

                  tileHeight:
                    provider.tileHeight,
                }
              );

              // ==============================================================
              // ADD NEW LAYER FIRST
              //
              // Previous layer stays visible until new layer is ready.
              // ==============================================================

              const lengthBefore =
                viewer.imageryLayers
                  .length;

              console.log(
                `[YARA CESIUM DEBUG] IMAGERY LAYERS COUNT BEFORE ADD: ${lengthBefore}`
              );

              onFrameLoadingChange?.(
                true,
                null,
                'updating'
              );

              const newLayer =
                viewer.imageryLayers.addImageryProvider(
                  provider
                );

              newLayer.show =
                true;

              newLayer.alpha =
                1.0;

              newLayer.brightness =
                1.0;

              newLayer.contrast =
                1.0;

              const lengthAfter =
                viewer.imageryLayers
                  .length;

              const newIndex =
                viewer.imageryLayers.indexOf(
                  newLayer
                );

              console.log(
                '[YARA FRAME] layer-added',
                {
                  lengthBefore,
                  lengthAfter,
                  layerIndex: newIndex,
                  show: newLayer.show,
                  alpha: newLayer.alpha,
                }
              );

              viewer.scene.requestRender();

              // ==============================================================
              // PUT SCIENTIFIC LAYER ABOVE BASEMAP
              // ==============================================================

              viewer.imageryLayers.raiseToTop(
                newLayer
              );

              if (
                baseLayerRef.current
              ) {
                viewer.imageryLayers.lowerToBottom(
                  baseLayerRef.current
                );
              }

              viewer.scene.requestRender();

              // ==============================================================
              // ATOMIC REPLACEMENT
              // Remove old scientific layer ONLY AFTER new one exists.
              // ==============================================================

              const previousLayer =
                dataLayersRef.current.get(
                  'online'
                );

              let oldRemoved =
                false;

              if (
                previousLayer &&
                previousLayer !==
                  newLayer
              ) {
                viewer.imageryLayers.remove(
                  previousLayer,
                  true
                );

                oldRemoved =
                  true;
              }

              console.log(
                `[YARA CESIUM DEBUG] OLD LAYER REMOVED: ${oldRemoved}`
              );

              dataLayersRef.current.set(
                'online',
                newLayer
              );

              viewer.scene.requestRender();

              // ==============================================================
              // BLOB URL MANAGEMENT
              // ==============================================================

              const previousBlobUrl =
                currentBlobUrlRef.current;

              currentBlobUrlRef.current =
                frameRes.blobUrl;

              generatedBlobUrl =
                null;

              if (
                previousBlobUrl &&
                previousBlobUrl !==
                  frameRes.blobUrl
              ) {
                URL.revokeObjectURL(
                  previousBlobUrl
                );
              }

              // ==============================================================
              // MARK AS SUCCESSFULLY RENDERED ONLY AFTER LAYER ADDED
              // ==============================================================

              lastSstRequestRef.current =
                requestKey;

              onFrameLoadingChange?.(
                false,
                null
              );

              console.log(
                '[YARA FRAME] render-requested'
              );

              console.log(
                '[YARA FRAME] complete',
                requestKey
              );

              // ==============================================================
              // FORCE CESIUM RENDER
              // ==============================================================

              viewer.scene.requestRender();

              setTimeout(() => {
                if (
                  viewerRef.current &&
                  !viewerRef.current.isDestroyed()
                ) {
                  viewerRef.current.scene.requestRender();
                }
              }, 50);

              setTimeout(() => {
                if (
                  viewerRef.current &&
                  !viewerRef.current.isDestroyed()
                ) {
                  viewerRef.current.scene.requestRender();
                }
              }, 250);

              // ==============================================================
              // PERSISTENCE DEBUG
              // ==============================================================

              [100, 1000, 2000].forEach(
                (delay) => {
                  setTimeout(() => {
                    if (
                      viewerRef.current &&
                      !viewerRef.current.isDestroyed()
                    ) {
                      const stillExists =
                        viewerRef.current.imageryLayers.contains(
                          newLayer
                        );

                      const currentLen =
                        viewerRef.current.imageryLayers.length;

                      console.log(
                        `[YARA CESIUM DEBUG] PERSISTENCE CHECK @ ${delay}ms:`,
                        {
                          stillExists,

                          currentLen,

                          layerIndex:
                            viewerRef.current.imageryLayers.indexOf(
                              newLayer
                            ),
                        }
                      );
                    }
                  }, delay);
                }
              );
            } catch (
              err: unknown
            ) {
              const errMsg =
                String(err);

              // ------------------------------------------------------------
              // ABORT ERROR
              // ------------------------------------------------------------

              if (
                abortController.signal
                  .aborted ||
                errMsg.includes(
                  'AbortError'
                )
              ) {
                console.log(
                  '[YARA FRAME] request-aborted',
                  requestKey
                );

                if (inFlightOnlineRequestRef.current === requestKey) {
                  onFrameLoadingChange?.(false, null);
                }

                return;
              }

              // ------------------------------------------------------------
              // 429
              // ------------------------------------------------------------

              if (
                errMsg.includes(
                  '429'
                ) ||
                errMsg.includes(
                  'Too Many'
                )
              ) {
                sstRateLimitedUntilRef.current =
                  Date.now() +
                  300_000;

                console.error(
                  '[YARA Online] Rate limited (429).'
                );

                onFrameLoadingChange?.(
                  false,
                  'Rate limited (429). Previous visualization preserved.'
                );

                return;
              }

              // ------------------------------------------------------------
              // OTHER ERROR
              // ------------------------------------------------------------

              console.error(
                '[YARA FRAME] error',
                err
              );

              lastSstRequestRef.current = '';

              if (viewerRef.current && !viewerRef.current.isDestroyed()) {
                viewerRef.current.scene.requestRender();
              }

              onFrameLoadingChange?.(
                false,
                `Ocean visualization could not be rendered: ${errMsg}`
              );
            } finally {
              // ------------------------------------------------------------
              // CRITICAL FIX
              //
              // Always clear in-flight status when THIS request finishes.
              // But never clear a newer request's status.
              // ------------------------------------------------------------

              if (
                inFlightOnlineRequestRef.current ===
                requestKey
              ) {
                inFlightOnlineRequestRef.current =
                  null;
              }

              if (
                layerUpdateAbortRef.current ===
                abortController
              ) {
                layerUpdateAbortRef.current =
                  null;
              }

              // If an error happened after obtaining a blob URL,
              // clean it up unless it became the current displayed URL.
              if (
                generatedBlobUrl &&
                generatedBlobUrl !==
                  currentBlobUrlRef.current
              ) {
                URL.revokeObjectURL(
                  generatedBlobUrl
                );

                generatedBlobUrl =
                  null;
              }
            }

            return;
          }

          // ==================================================================
          // LOCAL DATASET MODE
          // ==================================================================

          if (
            activeMode === 'local' &&
            activeDataset
          ) {
            // Abort previous local/online operation
            if (
              layerUpdateAbortRef.current
            ) {
              layerUpdateAbortRef.current.abort();
            }

            const abortController =
              new AbortController();

            layerUpdateAbortRef.current =
              abortController;

            const varToRender =
              localVariable ||
              activeDataset.default_variable ||
              Object.keys(
                activeDataset.variables
              )[0] ||
              'data';

            const imageUrl =
              getLocalFrameUrl(
                activeDataset.id,

                varToRender,

                localTimeIndex,

                undefined,

                colormap,

                colorScaleMin,

                colorScaleMax,

                localAnalysis
              );

            const requestKey =
              `local:${activeDataset.id}:${varToRender}:${localTimeIndex}:${colormap}:${colorScaleMin}:${colorScaleMax}:${JSON.stringify(localAnalysis)}`;

            if (
              lastSstRequestRef.current ===
                requestKey &&
              dataLayersRef.current.has(
                'local'
              )
            ) {
              return;
            }

            console.log(
              '[YARA Local] START LOCAL FRAME',
              {
                dataset:
                  activeDataset.name,

                datasetId:
                  activeDataset.id,

                variable:
                  varToRender,

                timeIndex:
                  localTimeIndex,

                url:
                  imageUrl,
              }
            );

            const ext =
              activeDataset.spatial_extent;

            try {
              const provider =
                await Cesium.SingleTileImageryProvider.fromUrl(
                  imageUrl,
                  {
                    rectangle:
                      Cesium.Rectangle.fromDegrees(
                        ext.west,
                        ext.south,
                        ext.east,
                        ext.north
                      ),
                  }
                );

              if (
                abortController.signal
                  .aborted
              ) {
                return;
              }

              if (
                !viewerRef.current ||
                viewerRef.current.isDestroyed()
              ) {
                return;
              }

              // ------------------------------------------------------------
              // Remove previous local data layers only after provider ready
              // ------------------------------------------------------------

              for (const [
                layerId,
                layer,
              ] of dataLayersRef.current) {
                if (
                  layerId ===
                  'local'
                ) {
                  viewer.imageryLayers.remove(
                    layer,
                    true
                  );

                  dataLayersRef.current.delete(
                    layerId
                  );
                }
              }

              const layer =
                viewer.imageryLayers.addImageryProvider(
                  provider
                );

              layer.show =
                true;

              layer.alpha =
                1.0;

              viewer.imageryLayers.raiseToTop(
                layer
              );

              if (
                baseLayerRef.current
              ) {
                viewer.imageryLayers.lowerToBottom(
                  baseLayerRef.current
                );
              }

              dataLayersRef.current.set(
                'local',
                layer
              );

              lastSstRequestRef.current =
                requestKey;

              console.log(
                `[YARA Local] Rendered frame for ${activeDataset.name} [${varToRender}]`
              );

              raiseLabelsToTop();

              viewer.scene.requestRender();
            } catch (err) {
              if (
                abortController.signal
                  .aborted
              ) {
                return;
              }

              console.error(
                '[YARA Local] Failed to load local dataset imagery:',
                err
              );
            } finally {
              if (
                layerUpdateAbortRef.current ===
                abortController
              ) {
                layerUpdateAbortRef.current =
                  null;
              }
            }

            return;
          }

          // ==================================================================
          // LEGACY / MULTI-LAYER MODE
          // ==================================================================

          const currentLayerIds =
            new Set(
              dataLayersRef.current.keys()
            );

          const targetLayerIds =
            new Set(layers);

          // Remove invisible layers
          for (const layerId of currentLayerIds) {
            if (
              !targetLayerIds.has(
                layerId
              )
            ) {
              const layer =
                dataLayersRef.current.get(
                  layerId
                );

              if (layer) {
                viewer.imageryLayers.remove(
                  layer,
                  true
                );

                dataLayersRef.current.delete(
                  layerId
                );
              }
            }
          }

          // Add legacy layers if needed
          for (const variable of layers) {
            const existingLayer =
              dataLayersRef.current.get(
                variable
              );

            if (existingLayer) {
              let stillInViewer =
                false;

              for (
                let i = 0;
                i <
                viewer.imageryLayers.length;
                i++
              ) {
                if (
                  viewer.imageryLayers.get(
                    i
                  ) ===
                  existingLayer
                ) {
                  stillInViewer =
                    true;

                  break;
                }
              }

              if (
                stillInViewer
              ) {
                continue;
              }

              dataLayersRef.current.delete(
                variable
              );
            }
          }

          // Legacy compatibility
          sstLayerRef.current =
            dataLayersRef.current.get(
              'sst'
            ) || null;

          raiseLabelsToTop();

          if (
            !viewer.isDestroyed()
          ) {
            viewer.scene.requestRender();
          }
        },
        [
          activeMode,
          activeDataset,
          localVariable,
          localTimeIndex,
          colorScaleMin,
          colorScaleMax,
          colormap,
          localAnalysis,
          onlineVariable,
          onlineDatasetId,
          onlineDate,
          raiseLabelsToTop,
          onFrameLoadingChange,
        ]
      );

    // ========================================================================
    // UPDATE LAYERS EFFECT
    //
    // IMPORTANT:
    // There is NO:
    //
    // return () => layerUpdateAbortRef.current?.abort()
    //
    // here.
    //
    // React is allowed to rerender without killing the scientific request.
    // ========================================================================

    const prevDateRef =
      useRef<string>('');

    const prevSstScaleRef =
      useRef<{
        min: number;
        max: number;
      }>({
        min: colorScaleMin,
        max: colorScaleMax,
      });

    const prevLocalKeyRef =
      useRef<string>('');

    const prevOnlineKeyRef =
      useRef<string>('');

    useEffect(() => {
      const viewer =
        viewerRef.current;

      if (
        !viewer ||
        viewer.isDestroyed()
      ) {
        return;
      }

      // ======================================================================
      // LOCAL MODE
      // ======================================================================

      if (
        activeMode === 'local'
      ) {
        prevOnlineKeyRef.current = '';
        const localKey =
          `${activeDataset?.id}:${localVariable}:${localTimeIndex}:${colorScaleMin}:${colorScaleMax}:${colormap}:${JSON.stringify(localAnalysis)}`;

        if (
          prevLocalKeyRef.current !==
          localKey
        ) {
          prevLocalKeyRef.current =
            localKey;

          updateDataLayers(
            selectedDate,
            visibleLayers
          );
        }

        return;
      }

      // Reset local state
      prevLocalKeyRef.current =
        '';

      // ======================================================================
      // ONLINE MODE
      //
      // Do NOT gate this on isLoading or selectedDate.
      // ======================================================================

      if (
        activeMode === 'online'
      ) {
        const onlineKey = `${onlineDatasetId}:${onlineVariable}:${onlineDate}:${colormap}:${colorScaleMin}:${colorScaleMax}`;
        if (prevOnlineKeyRef.current !== onlineKey) {
          prevOnlineKeyRef.current = onlineKey;
          console.log(
            `[YARA APPLY] Layer effect triggered: variable=${onlineVariable} date=${onlineDate}`
          );

          updateDataLayers(
            selectedDate,
            visibleLayers
          );
        }

        // NO ABORT CLEANUP HERE.
        return;
      }

      // ======================================================================
      // LEGACY MODE
      // ======================================================================

      if (
        !selectedDate ||
        isLoading
      ) {
        return;
      }

      // Clear layers on date change
      if (
        prevDateRef.current !==
        selectedDate
      ) {
        for (const [
          _layerId,
          layer,
        ] of dataLayersRef.current) {
          viewer.imageryLayers.remove(
            layer,
            true
          );
        }

        dataLayersRef.current.clear();

        prevDateRef.current =
          selectedDate;
      }

      // Clear SST layer when scale changes
      if (
        prevSstScaleRef.current.min !==
          colorScaleMin ||
        prevSstScaleRef.current.max !==
          colorScaleMax
      ) {
        const sstLayer =
          dataLayersRef.current.get(
            'sst'
          );

        if (sstLayer) {
          viewer.imageryLayers.remove(
            sstLayer,
            true
          );

          dataLayersRef.current.delete(
            'sst'
          );
        }

        prevSstScaleRef.current = {
          min: colorScaleMin,
          max: colorScaleMax,
        };
      }

      updateDataLayers(
        selectedDate,
        visibleLayers
      );
    }, [
      selectedDate,
      isLoading,
      updateDataLayers,
      visibleLayers,
      activeMode,
      activeDataset,
      localVariable,
      localTimeIndex,
      colorScaleMin,
      colorScaleMax,
      colormap,
      localAnalysis,
      viewerInitialized,
      onlineVariable,
      onlineDatasetId,
      onlineDate,
    ]);

    // ========================================================================
    // FINAL COMPONENT
    // ========================================================================

    return (
      <>
        {viewerInitialized &&
          viewerRef.current &&
          activeMode === 'local' &&
          activeDataset &&
          localGridEnabled && (
            <GridOverlay
              viewer={
                viewerRef.current
              }
              datasetId={
                activeDataset.id
              }
              variable={
                localVariable ||
                activeDataset.default_variable ||
                ''
              }
            />
          )}

        <div
          ref={containerRef}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
          }}
        />
      </>
    );
  }
);
