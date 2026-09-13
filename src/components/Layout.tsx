import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Box } from '@mui/material';
import * as Cesium from 'cesium';

import { Header } from './Header';
import { Footer } from './Footer';
import {
  Sidebar,
  SIDEBAR_WIDTH,
  SIDEBAR_WIDTH_COLLAPSED,
} from './Sidebar';

import { TimeSlider, MOCK_DATES } from './TimeSlider';

import {
  CesiumViewer,
  CesiumViewerHandle,
  BasemapId,
} from './CesiumViewer';

import { MapControls } from './MapControls';
import { MouseCoordinates } from './MouseCoordinates';
import { ColorScaleControls } from './ColorScaleControls';

import {
  LayersPanelPopup,
  LayerItem,
  DEFAULT_LAYERS,
} from './LayersPanelPopup';

import {
  ActiveLayer,
  DEFAULT_ACTIVE_LAYER,
} from './LayerBrowser';

import { AnalyticsPanel } from './AnalyticsPanel';
import { SettingsPanel } from './SettingsPanel';
import { AboutPanel } from './AboutPanel';
import { DataProvenancePage } from './DataProvenancePage';
import { TermsOfUsePage } from './TermsOfUsePage';

import {
  BookmarksPanel,
  Bookmark,
} from './BookmarksPanel';

import {
  TimeRange,
  SSTPointQuery,
  VariablePointQuery,
} from '../api/sstApi';

import { LocalDatasetModal } from './LocalDataset/LocalDatasetModal';
import { DatasetVariableSelector } from './LocalDataset/DatasetVariableSelector';

import {
  DatasetInfo,
  AnalysisOptions,
  LocalPointQueryResponse,
} from '../types/dataset';

import {
  defaultAnalysis,
  analysisError,
} from '../utils/gradientColormap';

import { useDebouncedValue } from '../hooks/useDebouncedValue';

import { LocalPointInfoPanel } from './LocalPointInfoPanel';
import { LocalAnalysisStatus } from './LocalAnalysisStatus';

import {
  fetchActiveMode,
  fetchLocalPoint,
} from '../services/localDatasetApi';

import {
  OnlineControls,
  OnlineState,
} from './OnlineControls';

import {
  OnlinePointInfoPanel,
} from './OnlinePointInfoPanel';

import {
  fetchOnlinePoint,
  OnlinePointQuery,
} from '../api/onlineApi';

import {
  ScientificProcessingToast,
  ProcessingState,
} from './ScientificProcessingToast';




export function Layout() {

  /* ------------------------------------------------------------------ */
  /* UI STATE                                                           */
  /* ------------------------------------------------------------------ */

  const [sidebarCollapsed, setSidebarCollapsed] =
    useState(true);

  const [layersPanelOpen, setLayersPanelOpen] =
    useState(false);

  const [analyticsPanelOpen, setAnalyticsPanelOpen] =
    useState(() => window.location.pathname === '/variables');

  const [settingsPanelOpen, setSettingsPanelOpen] =
    useState(() => window.location.pathname === '/settings');

  const [aboutPanelOpen, setAboutPanelOpen] =
    useState(() => window.location.pathname === '/about');

  const [dataProvenanceOpen, setDataProvenanceOpen] =
    useState(() => window.location.pathname === '/data');

  const [termsOpen, setTermsOpen] =
    useState(() => window.location.pathname === '/terms');

  const [bookmarksPanelOpen, setBookmarksPanelOpen] =
    useState(() => window.location.pathname === '/bookmarks');

  const [timelineCollapsed, setTimelineCollapsed] =
    useState(() => {
      const saved =
        localStorage.getItem('timeline-collapsed');

      return saved !== null
        ? saved === 'true'
        : true;
    });


  /* ------------------------------------------------------------------ */
  /* CESIUM                                                            */
  /* ------------------------------------------------------------------ */

  const cesiumRef =
    useRef<CesiumViewerHandle>(null);

  const [viewerReady, setViewerReady] =
    useState(false);

  const [currentBasemap, setCurrentBasemap] =
    useState<BasemapId>('satellite');

  const [labelsVisible, setLabelsVisible] =
    useState(false);


  /* ------------------------------------------------------------------ */
  /* DATA MODE                                                          */
  /* ------------------------------------------------------------------ */

  const [activeMode, setActiveMode] =
    useState<'online' | 'local'>('online');

  const [activeDataset, setActiveDataset] =
    useState<DatasetInfo | null>(null);

  const [localVariable, setLocalVariable] =
    useState('');

  const [localTimeIndex, setLocalTimeIndex] =
    useState(0);

  const [localModalOpen, setLocalModalOpen] =
    useState(false);


  /* ------------------------------------------------------------------ */
  /* LOCAL DATA ANALYSIS                                               */
  /* ------------------------------------------------------------------ */

  const [localAnalysis, setLocalAnalysis] =
    useState<AnalysisOptions>(defaultAnalysis);

  const [validAnalysis, setValidAnalysis] =
    useState<AnalysisOptions>(defaultAnalysis);

  const [localGridEnabled, setLocalGridEnabled] =
    useState(false);

  const [localPoint, setLocalPoint] =
    useState<LocalPointQueryResponse | null>(null);

  const [localPointLoading, setLocalPointLoading] =
    useState(false);

  const [localPointError, setLocalPointError] =
    useState('');

  const [localClick, setLocalClick] =
    useState<{ lat: number; lon: number } | null>(null);


  /* ------------------------------------------------------------------ */
  /* ONLINE DATA                                                        */
  /* ------------------------------------------------------------------ */

  const [onlineState, setOnlineState] =
    useState<OnlineState>({
      datasetId: '',
      variable: '',
      date: '',
      resolvedDate: null,
      availableDates: [],
      metadata: null,
      status: 'loading',
      error: null,
      registry: [],
    });

  const [onlinePointData, setOnlinePointData] =
    useState<OnlinePointQuery | null>(null);

  const [onlinePointLoading, setOnlinePointLoading] =
    useState(false);

  const [onlineScreenPosition, setOnlineScreenPosition] =
    useState<{ x: number; y: number } | null>(null);

  const [processingState, setProcessingState] =
    useState<ProcessingState>({
      isProcessing: false,
      status: 'idle',
    });



  const handleOnlineApply = useCallback((datasetId: string, variable: string, date: string) => {
    if (!datasetId || !variable || !date) {
      console.warn('[YARA APPLY] Apply called with empty variable — ignoring');
      return;
    }

    console.log('[YARA FRONTEND] handleOnlineApply called');
    console.log(`[YARA FRONTEND] Applied variable: ${variable}`);
    console.log(`[YARA FRONTEND] Applied date: ${date}`);
    console.log('[YARA FRONTEND] Starting scientific data fetch');

    // Show the processing toast immediately so the user sees feedback.
    setProcessingState({
      isProcessing: true,
      status: 'fetching',
      title: 'Fetching scientific data…',
      message: `Requesting ${variable} for ${date} from Copernicus Marine Service OPeNDAP…`,
    });

    // Commit the applied state.
    setOnlineState(prev => ({
      ...prev,
      datasetId,
      variable,
      date,
      resolvedDate: date,
      status: prev.status === 'error' ? 'ready' : prev.status,
    }));
  }, []);

  const handleFrameLoadingChange = useCallback((loading: boolean, error?: string | null) => {
    if (loading) {
      setProcessingState(prev => ({
        ...prev,
        isProcessing: true,
        status: prev.status === 'idle' ? 'fetching' : prev.status,
      }));
    } else if (error) {
      setProcessingState({
        isProcessing: true,
        status: 'error',
        title: 'Unable to process scientific data',
        message: error,
      });
      setTimeout(() => {
        setProcessingState({ isProcessing: false, status: 'idle' });
      }, 4000);
    } else {
      setProcessingState({
        isProcessing: true,
        status: 'success',
        title: 'Scientific data loaded',
        message: 'Globe updated successfully.',
      });
      setTimeout(() => {
        setProcessingState({ isProcessing: false, status: 'idle' });
      }, 2000);
    }
  }, []);


  /* ------------------------------------------------------------------ */
  /* TIME                                                              */
  /* ------------------------------------------------------------------ */

  const [timeRange, setTimeRange] =
    useState<TimeRange | null>(null);

  const [selectedDate, setSelectedDate] =
    useState('');

  const [isLoading, setIsLoading] =
    useState(true);

  const [_error, setError] =
    useState<string | null>(null);


  /* ------------------------------------------------------------------ */
  /* LAYERS                                                            */
  /* ------------------------------------------------------------------ */

  const [layers, setLayers] =
    useState<LayerItem[]>(() => {

      const params =
        new URLSearchParams(window.location.search);

      const urlLayers =
        params.get('layers');

      if (urlLayers) {

        const ids =
          urlLayers
            .split(',')
            .filter(Boolean);

        return DEFAULT_LAYERS.map(layer => ({
          ...layer,
          visible: ids.includes(layer.id),
        }));
      }

      const stored =
        localStorage.getItem('layer-visibility');

      if (stored) {

        try {

          const visibility =
            JSON.parse(stored) as Record<string, boolean>;

          return DEFAULT_LAYERS.map(layer => ({
            ...layer,
            visible:
              visibility[layer.id] ??
              layer.visible,
          }));

        } catch {
          return DEFAULT_LAYERS;
        }
      }

      return DEFAULT_LAYERS;
    });


  const [activeLayer, _setActiveLayer] =
    useState<ActiveLayer>(DEFAULT_ACTIVE_LAYER);

  const [_layerInfoOpen, setLayerInfoOpen] =
    useState(false);


  /* ------------------------------------------------------------------ */
  /* COLOR SCALE                                                       */
  /* ------------------------------------------------------------------ */

  const [colorScaleMin, setColorScaleMin] =
    useState(() => {

      const value =
        localStorage.getItem('sst-color-min');

      return value
        ? Number(value)
        : -2;
    });


  const [colorScaleMax, setColorScaleMax] =
    useState(() => {

      const value =
        localStorage.getItem('sst-color-max');

      return value
        ? Number(value)
        : 35;
    });


  const [colormap, setColormap] =
    useState(() =>
      localStorage.getItem('sst-colormap') ||
      'thermal'
    );


  const [colorScaleOpen, setColorScaleOpen] =
    useState(false);


  /* ------------------------------------------------------------------ */
  /* THRESHOLD                                                         */
  /* ------------------------------------------------------------------ */

  const [thresholdEnabled, setThresholdEnabled] =
    useState(false);

  const [thresholdMin, setThresholdMin] =
    useState<number | null>(null);

  const [thresholdMax, setThresholdMax] =
    useState<number | null>(null);


  /* ------------------------------------------------------------------ */
  /* POINT QUERY                                                       */
  /* ------------------------------------------------------------------ */

  const [clickedPosition, setClickedPosition] =
    useState<{
      lon: number;
      lat: number;
    } | null>(null);

  const [_screenPosition, _setScreenPosition] =
    useState<{
      x: number;
      y: number;
    } | null>(null);

  const [_sstPointData, _setSstPointData] =
    useState<SSTPointQuery | null>(null);

  const [_sstPointLoading, _setSstPointLoading] =
    useState(false);

  const [_variablePointData, _setVariablePointData] =
    useState<VariablePointQuery | null>(null);

  const [_variablePointLoading, _setVariablePointLoading] =
    useState(false);

  const [_variableScreenPosition, _setVariableScreenPosition] =
    useState<{
      x: number;
      y: number;
    } | null>(null);


  /* ------------------------------------------------------------------ */
  /* LOCAL ANALYSIS                                                    */
  /* ------------------------------------------------------------------ */

  useEffect(() => {

    if (!analysisError(localAnalysis)) {
      setValidAnalysis(localAnalysis);
    }

  }, [localAnalysis]);


  const debouncedAnalysis =
    useDebouncedValue(validAnalysis);


  const localFrameStyle =
    useMemo(() => ({
      analysis: debouncedAnalysis,
      colormap,
      minVal: colorScaleMin,
      maxVal: colorScaleMax,
    }), [
      debouncedAnalysis,
      colormap,
      colorScaleMin,
      colorScaleMax,
    ]);


  /* ------------------------------------------------------------------ */
  /* PERSIST COLOR SETTINGS                                            */
  /* ------------------------------------------------------------------ */

  useEffect(() => {

    localStorage.setItem(
      'sst-color-min',
      String(colorScaleMin)
    );

  }, [colorScaleMin]);


  useEffect(() => {

    localStorage.setItem(
      'sst-color-max',
      String(colorScaleMax)
    );

  }, [colorScaleMax]);


  useEffect(() => {

    localStorage.setItem(
      'sst-colormap',
      colormap
    );

  }, [colormap]);


  /* ------------------------------------------------------------------ */
  /* ONLINE STATE CHANGE                                               */
  /* ------------------------------------------------------------------ */

  const handleOnlineStateChange =
    useCallback(
      (next: Partial<OnlineState>) => {

        setOnlineState(prev => {

          const merged = {
            ...prev,
            ...next,
          };

          /*
           * IMPORTANT:
           * When the online variable changes,
           * use its REAL backend visualization settings.
           */

          if (
            next.variable &&
            next.variable !== prev.variable
          ) {

            setOnlinePointData(null);
            setOnlinePointLoading(false);

            const dataset = (next.registry ?? prev.registry)
              .find(item => item.id === (next.datasetId ?? prev.datasetId));
            const cfg = dataset?.variables.find(item => item.id === next.variable);

            if (cfg) {

              if (cfg.vmin != null) setColorScaleMin(cfg.vmin);
              if (cfg.vmax != null) setColorScaleMax(cfg.vmax);

              if (cfg.colormap) {
                setColormap(cfg.colormap);
              }

              localStorage.setItem(
                'sst-color-min',
                String(cfg.vmin ?? '')
              );

              localStorage.setItem(
                'sst-color-max',
                String(cfg.vmax ?? '')
              );

              localStorage.setItem(
                'sst-colormap',
                cfg.colormap ||
                'viridis'
              );
            }
          }

          return merged;
        });

      },
      []
    );


  /* ------------------------------------------------------------------ */
  /* ACTIVE ONLINE VARIABLE SETTINGS                                   */
  /* ------------------------------------------------------------------ */

  const onlineConfig = onlineState.registry
    .find(dataset => dataset.id === onlineState.datasetId)
    ?.variables.find(variable => variable.id === onlineState.variable);


  /*
   * Backend registry is authoritative.
   * If metadata is available, it has priority.
   */

  const effectiveMin =
    activeMode === 'online' &&
    onlineState.metadata
      ? (onlineConfig?.vmin ?? colorScaleMin)
      : colorScaleMin;


  const effectiveMax =
    activeMode === 'online' &&
    onlineState.metadata
      ? (onlineConfig?.vmax ?? colorScaleMax)
      : colorScaleMax;


  const effectiveColormap =
    activeMode === 'online'
      ? (
          onlineConfig?.colormap ||
          colormap
        )
      : colormap;


  const effectiveUnits =
    activeMode === 'online'
      ? (
          onlineConfig?.units ||
          ''
        )
      : (
          activeDataset
            ?.variables[
              localVariable
            ]?.units ||
          ''
        );


  /* ------------------------------------------------------------------ */
  /* VISIBLE DATA LAYERS                                               */
  /* ------------------------------------------------------------------ */

  const normalVisibleLayers =
    useMemo(
      () =>
        layers
          .filter(layer => layer.visible)
          .map(layer => layer.id),
      [layers]
    );


  /*
   * THIS IS THE IMPORTANT FIX.
   *
   * Online variables are not necessarily:
   * sst / sic / sla / chl.
   *
   * They can be:
   * uo / vo / thetao / so / zos / ...
   *
   * Therefore Cesium must receive the actual selected
   * online variable.
   */

  const dataVisibleLayers =
    activeMode === 'online'
      ? (
          onlineState.variable
            ? [onlineState.variable]
            : []
        )
      : normalVisibleLayers;


  /* ------------------------------------------------------------------ */
  /* ACTIVE DATASET CHECK                                              */
  /* ------------------------------------------------------------------ */

  useEffect(() => {

    let cancelled = false;

    async function checkActiveDataset() {

      try {

        const data =
          await fetchActiveMode();

        if (
          cancelled ||
          data.mode !== 'local' ||
          !data.dataset
        ) {
          return;
        }

        setActiveMode('local');
        setActiveDataset(data.dataset);

        const variable =
          data.dataset.default_variable ||
          Object.keys(
            data.dataset.variables
          )[0] ||
          '';

        setLocalVariable(variable);

        const timestamps =
          data.dataset.time_axis.timestamps;

        if (
          timestamps &&
          timestamps.length > 0
        ) {

          setSelectedDate(
            timestamps[0]
          );

          setTimeRange({
            total_months: 1,
            start_date:
              data.dataset.time_axis.start_time ||
              timestamps[0],
            end_date:
              data.dataset.time_axis.end_time ||
              timestamps[
                timestamps.length - 1
              ],
            available_dates:
              timestamps,
            years: {},
          });

          setIsLoading(false);
        }

      } catch (err) {

        console.warn(
          'Unable to detect active local dataset:',
          err
        );

      }

    }

    checkActiveDataset();

    return () => {
      cancelled = true;
    };

  }, []);


  /* ------------------------------------------------------------------ */
  /* ONLINE TIME RANGE                                                 */
  /* ------------------------------------------------------------------ */

  useEffect(() => {

    if (activeMode === 'local') {
      return;
    }

    if (!onlineState.variable) {
      return;
    }

    /*
     * OnlineControls owns the real date list.
     *
     * Do not call the old SST time-range API here.
     */

    if (
      onlineState.resolvedDate &&
      !selectedDate
    ) {

      setSelectedDate(
        onlineState.resolvedDate
      );
    }

  }, [
    activeMode,
    onlineState.variable,
    onlineState.resolvedDate,
    selectedDate,
  ]);


  /* ------------------------------------------------------------------ */
  /* DATE CHANGE                                                       */
  /* ------------------------------------------------------------------ */

  const handleDateChange =
    useCallback(
      (date: string) => {

        setSelectedDate(date);

        if (
          activeMode === 'local' &&
          activeDataset
        ) {

          const index =
            activeDataset.time_axis.timestamps
              .indexOf(date);

          if (index >= 0) {
            setLocalTimeIndex(index);
          }
        }

      },
      [
        activeMode,
        activeDataset,
      ]
    );


  /* ------------------------------------------------------------------ */
  /* LOCAL POINT QUERY                                                 */
  /* ------------------------------------------------------------------ */

  useEffect(() => {

    let cancelled = false;

    if (
      activeMode !== 'local' ||
      !activeDataset ||
      !localClick
    ) {
      return;
    }

    setLocalPointLoading(true);
    setLocalPointError('');

    fetchLocalPoint(
      activeDataset.id,
      localClick.lat,
      localClick.lon,
      localVariable,
      localTimeIndex
    )
      .then(data => {

        if (!cancelled) {
          setLocalPoint(data);
        }

      })
      .catch(err => {

        if (!cancelled) {
          setLocalPointError(
            String(err)
          );
        }

      })
      .finally(() => {

        if (!cancelled) {
          setLocalPointLoading(false);
        }

      });

    return () => {
      cancelled = true;
    };

  }, [
    activeMode,
    activeDataset,
    localVariable,
    localTimeIndex,
    localClick,
  ]);


  /* ------------------------------------------------------------------ */
  /* MAP CLICK                                                         */
  /* ------------------------------------------------------------------ */

  const handleMapClick =
    useCallback(
      async (
        lon: number,
        lat: number
      ) => {

        /*
         * LOCAL
         */

        if (
          activeMode === 'local' &&
          activeDataset
        ) {

          setLocalClick({
            lat,
            lon,
          });

          setClickedPosition({
            lat,
            lon,
          });

          return;
        }


        /*
         * ONLINE
         *
         * Do NOT require selectedDate here.
         * The online controller has its own resolved date.
         */

        if (
          activeMode === 'online'
        ) {

          if (
            !onlineState.variable
          ) {
            return;
          }

          const viewer =
            cesiumRef.current?.viewer;

          let position = null;

          if (
            viewer &&
            !viewer.isDestroyed()
          ) {

            const cartesian =
              Cesium.Cartesian3.fromDegrees(
                lon,
                lat
              );

            const screen =
              Cesium.SceneTransforms
                .worldToWindowCoordinates(
                  viewer.scene,
                  cartesian
                );

            if (screen) {
              position = {
                x: screen.x,
                y: screen.y,
              };
            }
          }

          setClickedPosition({
            lon,
            lat,
          });

          setOnlineScreenPosition(
            position
          );

          setOnlinePointLoading(true);
          setOnlinePointData(null);
          setProcessingState({
            isProcessing: true,
            status: 'fetching',
            title: 'Fetching scientific observation…',
            message: `Querying nearest native ocean grid point for ${onlineState.variable}…`,
          });

          try {

            const date =
              onlineState.resolvedDate ||
              onlineState.date ||
              'latest';

            const result =
              await fetchOnlinePoint(
                onlineState.datasetId,
                onlineState.variable,
                date,
                lon,
                lat
              );

            setOnlinePointData(
              result
            );

            setProcessingState({
              isProcessing: false,
              status: 'idle',
            });

          } catch (err) {

            console.error(
              '[YARA] Online point query failed:',
              err
            );

            setOnlinePointData(null);
            setProcessingState({
              isProcessing: false,
              status: 'idle',
            });

          } finally {

            setOnlinePointLoading(false);

          }

          return;
        }

      },
      [
        activeMode,
        activeDataset,
        onlineState.variable,
        onlineState.datasetId,
        onlineState.resolvedDate,
        onlineState.date,
      ]
    );


  /* ------------------------------------------------------------------ */
  /* VIEWER READY                                                      */
  /* ------------------------------------------------------------------ */

  useEffect(() => {

    const timer =
      window.setInterval(() => {

        const viewer =
          cesiumRef.current?.viewer;

        if (
          viewer &&
          !viewer.isDestroyed()
        ) {

          setViewerReady(true);

          window.clearInterval(timer);
        }

      }, 50);

    return () =>
      window.clearInterval(timer);

  }, []);


  /* ------------------------------------------------------------------ */
  /* CAMERA                                                            */
  /* ------------------------------------------------------------------ */

  const [
    currentCameraPosition,
    setCurrentCameraPosition,
  ] = useState({
    lat: 0,
    lon: 0,
    height: 10000000,
  });


  const handleCameraChange =
    useCallback(
      (
        lon: number,
        lat: number,
        height: number
      ) => {

        setCurrentCameraPosition({
          lat,
          lon,
          height,
        });

      },
      []
    );


  /* ------------------------------------------------------------------ */
  /* BASEMAP                                                           */
  /* ------------------------------------------------------------------ */

  const handleBasemapChange =
    useCallback(
      (id: BasemapId) => {

        cesiumRef.current?.setBasemap(id);

        setCurrentBasemap(id);

      },
      []
    );


  /* ------------------------------------------------------------------ */
  /* LABELS                                                            */
  /* ------------------------------------------------------------------ */

  const handleLabelsToggle =
    useCallback(() => {

      cesiumRef.current?.toggleLabels();

      setLabelsVisible(
        value => !value
      );

    }, []);


  /* ------------------------------------------------------------------ */
  /* LAYER TOGGLE                                                      */
  /* ------------------------------------------------------------------ */

  const handleToggleLayer =
    useCallback(
      (layerId: string) => {

        setLayers(prev => {

          const next =
            prev.map(layer =>
              layer.id === layerId
                ? {
                    ...layer,
                    visible:
                      !layer.visible,
                  }
                : layer
            );

          const visibility:
            Record<string, boolean> = {};

          next.forEach(layer => {
            visibility[
              layer.id
            ] = layer.visible;
          });

          localStorage.setItem(
            'layer-visibility',
            JSON.stringify(
              visibility
            )
          );

          return next;
        });

      },
      []
    );


  /* ------------------------------------------------------------------ */
  /* DATASET ACTIVATION                                                */
  /* ------------------------------------------------------------------ */

  const handleDatasetActivated =
    useCallback(
      (dataset: DatasetInfo) => {

        setActiveMode('local');

        setActiveDataset(dataset);

        setLocalVariable(
          dataset.default_variable ||
          Object.keys(
            dataset.variables
          )[0] ||
          ''
        );

        setLocalTimeIndex(0);

        setLocalClick(null);

        setIsLoading(false);

        setError(null);

      },
      []
    );


  const handleDatasetDeactivated =
    useCallback(
      async () => {

        setActiveMode('online');

        setActiveDataset(null);

        setLocalVariable('');

        setLocalTimeIndex(0);

        setLocalClick(null);

        setOnlinePointData(null);

        setSelectedDate('');

      },
      []
    );





  /* ------------------------------------------------------------------ */
  /* SIDEBAR                                                            */
  /* ------------------------------------------------------------------ */

  const sidebarWidth =
    sidebarCollapsed
      ? SIDEBAR_WIDTH_COLLAPSED
      : SIDEBAR_WIDTH;


  /* ------------------------------------------------------------------ */
  /* RETURN                                                            */
  /* ------------------------------------------------------------------ */

  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
      }}
    >

      {/* ============================================================ */}
      {/* CESIUM GLOBE                                                 */}
      {/* ============================================================ */}

      <CesiumViewer
        ref={cesiumRef}

        selectedDate={
          activeMode === 'online'
            ? (
                onlineState.resolvedDate ||
                onlineState.date ||
                ''
              )
            : selectedDate
        }

        isLoading={
          activeMode === 'online'
            ? onlineState.status === 'loading'
            : isLoading
        }

        initialBasemap={
          currentBasemap
        }

        onMapClick={
          handleMapClick
        }

        clickedPosition={
          clickedPosition
        }

        /*
         * Use the effective backend values.
         */

        colorScaleMin={
          effectiveMin
        }

        colorScaleMax={
          effectiveMax
        }

        colormap={
          effectiveColormap
        }

        activeVariable={
          activeMode === 'online'
            ? (
                onlineState.variable ||
                'sst'
              )
            : (
                localVariable ||
                activeLayer.variableId ||
                'sst'
              )
        }

        /*
         * IMPORTANT:
         * online => actual selected variable
         * local  => normal layer list
         */

        visibleLayers={
          dataVisibleLayers
        }

        drawingMode={false}

        onBboxDrawn={() => {}}

        thresholdEnabled={
          thresholdEnabled
        }

        thresholdMin={
          thresholdMin
        }

        thresholdMax={
          thresholdMax
        }

        activeMode={
          activeMode
        }

        activeDataset={
          activeDataset
        }

        localVariable={
          localVariable
        }

        localTimeIndex={
          localTimeIndex
        }

        localAnalysis={
          debouncedAnalysis
        }

        localGridEnabled={
          localGridEnabled
        }

        onlineVariable={
          onlineState.variable
        }

        onlineDatasetId={
          onlineState.datasetId
        }

        onlineDate={
          onlineState.resolvedDate ||
          onlineState.date ||
          'latest'
        }

        onCameraChange={
          handleCameraChange
        }

        onFrameLoadingChange={
          handleFrameLoadingChange
        }

      />


      {/* ============================================================ */}
      {/* ONLINE CONTROLS                                              */}
      {/* ============================================================ */}

      {activeMode === 'online' && (

        <OnlineControls
          state={
            onlineState
          }

          onChange={
            handleOnlineStateChange
          }

          onApply={
            handleOnlineApply
          }

          frameLoading={
            onlinePointLoading
          }
        />

      )}


      {/* ============================================================ */}
      {/* ONLINE POINT PANEL                                           */}
      {/* ============================================================ */}

      {activeMode === 'online' &&
        (
          onlinePointData ||
          onlinePointLoading
        ) && (

          <OnlinePointInfoPanel
            data={
              onlinePointData
            }

            loading={
              onlinePointLoading
            }

            screenPosition={
              onlineScreenPosition
            }

            onClose={() => {

              setOnlinePointData(null);
              setOnlinePointLoading(false);
              setClickedPosition(null);
              setOnlineScreenPosition(null);

            }}
          />

      )}


      {/* ============================================================ */}
      {/* LOCAL MODE                                                    */}
      {/* ============================================================ */}

      {activeMode === 'local' &&
        activeDataset && (

          <>
            <LocalAnalysisStatus
              datasetId={
                activeDataset.id
              }

              variable={
                localVariable
              }

              index={
                localTimeIndex
              }

              style={
                localFrameStyle
              }
            />

            <LocalPointInfoPanel
              data={
                localPoint
              }

              loading={
                localPointLoading
              }

              error={
                localPointError
              }

              onClose={() => {

                setLocalClick(null);
                setClickedPosition(null);

              }}
            />
          </>

      )}


      {/* ============================================================ */}
      {/* COLOR SCALE                                                  */}
      {/* ============================================================ */}

      {colorScaleOpen && (

        <ColorScaleControls

          minTemp={
            effectiveMin
          }

          maxTemp={
            effectiveMax
          }

          colormap={
            effectiveColormap
          }

          onMinTempChange={
            setColorScaleMin
          }

          onMaxTempChange={
            setColorScaleMax
          }

          onColormapChange={
            setColormap
          }

          units={
            effectiveUnits
          }

          bottomOffset={
            timelineCollapsed
              ? 130
              : 260
          }

          thresholdEnabled={
            thresholdEnabled
          }

          thresholdMin={
            thresholdMin
          }

          thresholdMax={
            thresholdMax
          }

          onThresholdEnabledChange={
            setThresholdEnabled
          }

          onThresholdMinChange={
            setThresholdMin
          }

          onThresholdMaxChange={
            setThresholdMax
          }

          localAnalysis={
            activeMode === 'local'
              ? {
                  value:
                    localAnalysis,

                  onChange:
                    setLocalAnalysis,

                  gridEnabled:
                    localGridEnabled,

                  onGridChange:
                    setLocalGridEnabled,

                  units:
                    activeDataset
                      ?.variables[
                        localVariable
                      ]?.units,
                }
              : undefined
          }
        />

      )}


      {/* ============================================================ */}
      {/* MAP CONTROLS                                                 */}
      {/* ============================================================ */}

      {viewerReady &&
        cesiumRef.current && (

          <MapControls
            viewer={
              cesiumRef.current.viewer
            }

            currentBasemap={
              currentBasemap
            }

            onBasemapChange={
              handleBasemapChange
            }

            bottomOffset={
              timelineCollapsed
                ? 80
                : 210
            }

            colorScaleOpen={
              colorScaleOpen
            }

            onColorScaleToggle={() =>
              setColorScaleOpen(
                value => !value
              )
            }

            onStartDrawing={() => {}}

            isDrawingMode={
              false
            }

            labelsVisible={
              labelsVisible
            }

            onLabelsToggle={
              handleLabelsToggle
            }
          />

      )}


      {/* ============================================================ */}
      {/* COORDINATES                                                  */}
      {/* ============================================================ */}

      {viewerReady &&
        cesiumRef.current && (

          <MouseCoordinates
            viewer={
              cesiumRef.current.viewer
            }

            bottomOffset={
              timelineCollapsed
                ? 56
                : 186
            }

            leftOffset={
              sidebarWidth + 24
            }
          />

      )}


      {/* ============================================================ */}
      {/* TIME SLIDER                                                  */}
      {/* ============================================================ */}

      <Box
        sx={{
          position: 'absolute',
          bottom: 12,
          left: 12,
          right: 12,
          bgcolor:
            'rgba(8,12,18,0.85)',
          backdropFilter:
            'blur(16px)',
          zIndex: 1000,
        }}
      >

        <TimeSlider

          availableDates={
            activeMode === 'online'
              ? (
                  onlineState.availableDates
                    ?.length
                    ? onlineState.availableDates
                    : (
                        onlineState.resolvedDate
                          ? [
                              onlineState.resolvedDate,
                            ]
                          : []
                      )
                )
              : (
                  timeRange
                    ?.available_dates
                    ?.length
                    ? timeRange.available_dates
                    : MOCK_DATES
                )
          }

          selectedDate={
            activeMode === 'online'
              ? (
                  onlineState.date === 'latest'
                    ? (
                        onlineState.resolvedDate ||
                        'latest'
                      )
                    : onlineState.date
                )
              : (
                  selectedDate ||
                  MOCK_DATES[
                    MOCK_DATES.length - 1
                  ]
                )
          }

          onDateChange={
            date => {

              if (
                activeMode === 'online'
              ) {

                handleOnlineStateChange({
                  date,
                  resolvedDate:
                    date,
                });

              } else {

                handleDateChange(
                  date
                );

              }

            }
          }

          isLoading={
            activeMode === 'online'
              ? onlineState.status === 'loading'
              : isLoading
          }

          collapsed={
            timelineCollapsed
          }

          onToggleCollapsed={() => {

            const value =
              !timelineCollapsed;

            setTimelineCollapsed(
              value
            );

            localStorage.setItem(
              'timeline-collapsed',
              String(value)
            );

          }}
        />

      </Box>


      {/* ============================================================ */}
      {/* HEADER                                                       */}
      {/* ============================================================ */}

      <Header

        activeDataset={
          activeDataset
        }

        activeMode={
          activeMode
        }

        onOpenLocalModal={() =>
          setLocalModalOpen(true)
        }

        onSwitchToOnline={
          handleDatasetDeactivated
        }
      />


      {/* ============================================================ */}
      {/* LOCAL DATASET MODAL                                          */}
      {/* ============================================================ */}

      <LocalDatasetModal

        open={
          localModalOpen
        }

        onClose={() =>
          setLocalModalOpen(false)
        }

        activeDataset={
          activeDataset
        }

        onDatasetActivated={
          handleDatasetActivated
        }

        onDatasetDeactivated={
          handleDatasetDeactivated
        }
      />


      {/* ============================================================ */}
      {/* LOCAL VARIABLE SELECTOR                                      */}
      {/* ============================================================ */}

      {activeMode === 'local' &&
        activeDataset && (

          <Box
            sx={{
              position: 'absolute',
              top: 58,
              right: 12,
              zIndex: 1000,
            }}
          >

            <DatasetVariableSelector

              dataset={
                activeDataset
              }

              selectedVariable={
                localVariable
              }

              onSelectVariable={
                variable => {

                  setLocalVariable(
                    variable
                  );

                  setLocalTimeIndex(
                    0
                  );

                }
              }
            />

          </Box>

      )}


      {/* ============================================================ */}
      {/* SIDEBAR                                                      */}
      {/* ============================================================ */}

      <Box
        sx={{
          position: 'absolute',
          top: 52,
          left: 12,
          bottom: 80,
          width: sidebarWidth,
          bgcolor:
            'rgba(8,12,18,0.85)',
          backdropFilter:
            'blur(16px)',
          zIndex: 1000,
        }}
      >

        <Sidebar

          collapsed={
            sidebarCollapsed
          }

          onToggle={() =>
            setSidebarCollapsed(
              value => !value
            )
          }

          onOpenLayers={() =>
            setLayersPanelOpen(
              value => !value
            )
          }

          onOpenAnalytics={() =>
            setAnalyticsPanelOpen(
              true
            )
          }

          onFlyHome={() =>
            cesiumRef.current?.flyHome()
          }

          onOpenSettings={() =>
            setSettingsPanelOpen(
              true
            )
          }

          onOpenAbout={() =>
            setAboutPanelOpen(
              true
            )
          }

          onOpenBookmarks={() =>
            setBookmarksPanelOpen(
              true
            )
          }
        />

      </Box>


      {/* ============================================================ */}
      {/* LAYERS PANEL                                                 */}
      {/* ============================================================ */}

      <LayersPanelPopup

        open={
          layersPanelOpen
        }

        onClose={() =>
          setLayersPanelOpen(false)
        }

        layers={
          layers
        }

        onToggleLayer={
          handleToggleLayer
        }

        anchorTop={64}

        anchorLeft={
          sidebarWidth + 20
        }

        selectedDate={
          selectedDate
        }

        onOpenInfo={() =>
          setLayerInfoOpen(true)
        }

        onStartDrawing={() => {}}

        drawnBbox={null}

        isDrawingMode={
          false
        }

        onOpenCatalog={() => {

          setLayersPanelOpen(
            false
          );

          setAnalyticsPanelOpen(
            true
          );

        }}
      />


      {/* ============================================================ */}
      {/* PANELS                                                       */}
      {/* ============================================================ */}

      <AnalyticsPanel
        open={
          analyticsPanelOpen
        }
        onClose={() =>
          setAnalyticsPanelOpen(false)
        }
      />

      <SettingsPanel
        open={
          settingsPanelOpen
        }
        onClose={() =>
          setSettingsPanelOpen(false)
        }
      />

      <AboutPanel
        open={
          aboutPanelOpen
        }
        onClose={() =>
          setAboutPanelOpen(false)
        }
      />

      <DataProvenancePage
        open={
          dataProvenanceOpen
        }
        onClose={() =>
          setDataProvenanceOpen(false)
        }
      />

      <TermsOfUsePage
        open={
          termsOpen
        }
        onClose={() =>
          setTermsOpen(false)
        }
      />

      <BookmarksPanel

        open={
          bookmarksPanelOpen
        }

        onClose={() =>
          setBookmarksPanelOpen(false)
        }

        currentLat={
          currentCameraPosition.lat
        }

        currentLon={
          currentCameraPosition.lon
        }

        currentHeight={
          currentCameraPosition.height
        }

        currentDate={
          selectedDate
        }

        currentLayers={
          normalVisibleLayers
        }

        currentBasemap={
          currentBasemap
        }

        onLoadBookmark={
          (_bookmark: Bookmark) => {}
        }
      />




      {/* ============================================================ */}
      {/* FOOTER                                                       */}
      {/* ============================================================ */}

      <ScientificProcessingToast state={processingState} />

      <Footer />

    </Box>
  );
}
