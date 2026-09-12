import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Box } from '@mui/material';
import * as Cesium from 'cesium';
import { Header } from './Header';
import { Footer } from './Footer';
import { Sidebar, SIDEBAR_WIDTH, SIDEBAR_WIDTH_COLLAPSED } from './Sidebar';
import { TimeSlider, MOCK_DATES } from './TimeSlider';
import { CesiumViewer, CesiumViewerHandle, BasemapId } from './CesiumViewer';
import { MapControls } from './MapControls';
import { MouseCoordinates } from './MouseCoordinates';
import { ColorScaleControls } from './ColorScaleControls';
import { LayersPanelPopup, LayerItem, DEFAULT_LAYERS } from './LayersPanelPopup';
import { ActiveLayer, DEFAULT_ACTIVE_LAYER } from './LayerBrowser';
import { LayerInfoDialog } from './LayerInfoDialog';
import { SSTInfoPanel } from './SSTInfoPanel';
import { VariableInfoPanel } from './VariableInfoPanel';
import { AnalyticsPanel } from './AnalyticsPanel';
import { SettingsPanel } from './SettingsPanel';
import { AboutPanel } from './AboutPanel';
import { DataProvenancePage } from './DataProvenancePage';
import { TermsOfUsePage } from './TermsOfUsePage';
import { BboxDrawingOverlay, BoundingBox } from './BboxDrawingOverlay';
import { DownloadPanel } from './DownloadPanel';
import { BookmarksPanel, Bookmark } from './BookmarksPanel';
import { fetchTimeRangeForVariable, fetchSSTPoint, fetchVariablePoint, TimeRange, SSTPointQuery, VariablePointQuery } from '../api/sstApi';
import { LocalDatasetModal } from './LocalDataset/LocalDatasetModal';
import { DatasetVariableSelector } from './LocalDataset/DatasetVariableSelector';
import { PlaybackControls } from './LocalDataset/PlaybackControls';
import { DatasetInfo } from '../types/dataset';
import { fetchActiveMode, fetchLocalPoint } from '../services/localDatasetApi';

export function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true); // Start collapsed for cleaner view
  const [layersPanelOpen, setLayersPanelOpen] = useState(false);
  const [analyticsPanelOpen, setAnalyticsPanelOpen] = useState(() => {
    return window.location.pathname === '/variables';
  });
  const [settingsPanelOpen, setSettingsPanelOpen] = useState(() => {
    return window.location.pathname === '/settings';
  });
  const [aboutPanelOpen, setAboutPanelOpen] = useState(() => {
    return window.location.pathname === '/about';
  });
  const [dataProvenanceOpen, setDataProvenanceOpen] = useState(() => {
    return window.location.pathname === '/data';
  });
  const [termsOpen, setTermsOpen] = useState(() => {
    return window.location.pathname === '/terms';
  });
  const [bookmarksPanelOpen, setBookmarksPanelOpen] = useState(() => {
    return window.location.pathname === '/bookmarks';
  });
  const [timelineCollapsed, setTimelineCollapsed] = useState(() => {
    const saved = localStorage.getItem('timeline-collapsed');
    return saved !== null ? saved === 'true' : true; // Default to collapsed
  });

  // Listen for settings changes (from Settings panel) and sync timeline state
  useEffect(() => {
    const handleSettingsChanged = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail && typeof detail.timelineCollapsed === 'boolean') {
        setTimelineCollapsed(detail.timelineCollapsed);
      }
    };
    window.addEventListener('settings-changed', handleSettingsChanged);
    return () => window.removeEventListener('settings-changed', handleSettingsChanged);
  }, []);

  const cesiumRef = useRef<CesiumViewerHandle>(null);
  const [viewerReady, setViewerReady] = useState(false);
  const [currentBasemap, setCurrentBasemap] = useState<BasemapId>('satellite');
  const [labelsVisible, setLabelsVisible] = useState(false);

  const [timeRange, setTimeRange] = useState<TimeRange | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Local scientific dataset state
  const [activeMode, setActiveMode] = useState<'online' | 'local'>('online');
  const [activeDataset, setActiveDataset] = useState<DatasetInfo | null>(null);
  const [localVariable, setLocalVariable] = useState<string>('');
  const [localTimeIndex, setLocalTimeIndex] = useState<number>(0);
  const [localModalOpen, setLocalModalOpen] = useState<boolean>(false);

  // URL state management - read initial values from URL
  const urlParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const initialUrlDate = urlParams.get('date');
  
  // Parse camera position from URL (lat, lon, z for height)
  const initialCamera = useMemo(() => {
    const lat = parseFloat(urlParams.get('lat') || '');
    const lon = parseFloat(urlParams.get('lon') || '');
    const z = parseFloat(urlParams.get('z') || '');
    if (!isNaN(lat) && !isNaN(lon) && !isNaN(z)) {
      return { lat, lon, height: z };
    }
    return undefined;
  }, [urlParams]);

  // Update URL when date changes
  const updateUrlState = useCallback((date: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set('date', date);
    window.history.replaceState({}, '', url.toString());
  }, []);

  // Update URL with visible layers
  const updateLayersUrl = useCallback((visibleLayerIds: string[]) => {
    const url = new URL(window.location.href);
    if (visibleLayerIds.length > 0) {
      url.searchParams.set('layers', visibleLayerIds.join(','));
    } else {
      url.searchParams.delete('layers');
    }
    window.history.replaceState({}, '', url.toString());
  }, []);

  // Update URL path for panel navigation
  const updateUrlPath = useCallback((path: string) => {
    const url = new URL(window.location.href);
    url.pathname = path;
    window.history.pushState({}, '', url.toString());
  }, []);

  // Panel open/close handlers with URL persistence
  const handleOpenAnalytics = useCallback(() => {
    setAnalyticsPanelOpen(true);
    updateUrlPath('/variables');
  }, [updateUrlPath]);

  const handleCloseAnalytics = useCallback(() => {
    setAnalyticsPanelOpen(false);
    updateUrlPath('/');
  }, [updateUrlPath]);

  const handleOpenSettings = useCallback(() => {
    setSettingsPanelOpen(true);
    updateUrlPath('/settings');
  }, [updateUrlPath]);

  const handleCloseSettings = useCallback(() => {
    setSettingsPanelOpen(false);
    updateUrlPath('/');
  }, [updateUrlPath]);

  const handleOpenAbout = useCallback(() => {
    setAboutPanelOpen(true);
    updateUrlPath('/about');
  }, [updateUrlPath]);

  const handleCloseAbout = useCallback(() => {
    setAboutPanelOpen(false);
    updateUrlPath('/');
  }, [updateUrlPath]);

  // TODO: wire up handleOpenDataProvenance to a button when ready
  const handleCloseDataProvenance = useCallback(() => {
    setDataProvenanceOpen(false);
    updateUrlPath('/');
  }, [updateUrlPath]);

  // TODO: wire up handleOpenTerms to a button when ready
  const handleCloseTerms = useCallback(() => {
    setTermsOpen(false);
    updateUrlPath('/');
  }, [updateUrlPath]);

  const handleOpenBookmarks = useCallback(() => {
    setBookmarksPanelOpen(true);
    updateUrlPath('/bookmarks');
  }, [updateUrlPath]);

  const handleCloseBookmarks = useCallback(() => {
    setBookmarksPanelOpen(false);
    updateUrlPath('/');
  }, [updateUrlPath]);

  // Track current camera position for bookmarks
  const [currentCameraPosition, setCurrentCameraPosition] = useState({ lat: 0, lon: 0, height: 10000000 });

  // Update URL with camera position (debounced in CesiumViewer) and track for bookmarks
  const handleCameraChange = useCallback((lon: number, lat: number, height: number) => {
    setCurrentCameraPosition({ lat, lon, height });
    const url = new URL(window.location.href);
    url.searchParams.set('lat', lat.toFixed(2));
    url.searchParams.set('lon', lon.toFixed(2));
    url.searchParams.set('z', Math.round(height).toString());
    window.history.replaceState({}, '', url.toString());
  }, []);

  // Load a bookmark (fly to position, set date, set layers)
  const handleLoadBookmark = useCallback((bookmark: Bookmark) => {
    // Set date
    setSelectedDate(bookmark.date);
    updateUrlState(bookmark.date);
    
    // Set layers
    setLayers((prev) => {
      const newLayers = prev.map((layer) => ({
        ...layer,
        visible: bookmark.layers.includes(layer.id),
      }));
      const visibility: Record<string, boolean> = {};
      newLayers.forEach(l => { visibility[l.id] = l.visible; });
      localStorage.setItem('layer-visibility', JSON.stringify(visibility));
      updateLayersUrl(bookmark.layers);
      return newLayers;
    });
    
    // Fly to camera position
    const viewer = cesiumRef.current?.viewer;
    if (viewer && !viewer.isDestroyed()) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(bookmark.lon, bookmark.lat, bookmark.height),
        duration: 1.5,
      });
    }
    
    // Set basemap if provided
    if (bookmark.basemap) {
      cesiumRef.current?.setBasemap(bookmark.basemap as BasemapId);
      setCurrentBasemap(bookmark.basemap as BasemapId);
    }
  }, [updateUrlState, updateLayersUrl]);

  // Layer configuration - with localStorage persistence for visibility
  // URL takes priority over localStorage
  const [layers, setLayers] = useState<LayerItem[]>(() => {
    // Check URL first (read synchronously since this is initial state)
    const urlLayersParam = new URLSearchParams(window.location.search).get('layers');
    if (urlLayersParam) {
      const urlLayers = urlLayersParam.split(',').filter(Boolean);
      return DEFAULT_LAYERS.map(layer => ({
        ...layer,
        visible: urlLayers.includes(layer.id),
      }));
    }
    // Fall back to localStorage
    const savedVisibility = localStorage.getItem('layer-visibility');
    if (savedVisibility) {
      try {
        const visibility: Record<string, boolean> = JSON.parse(savedVisibility);
        return DEFAULT_LAYERS.map(layer => ({
          ...layer,
          visible: visibility[layer.id] ?? layer.visible,
        }));
      } catch {
        return DEFAULT_LAYERS;
      }
    }
    return DEFAULT_LAYERS;
  });
  const [activeLayer, setActiveLayer] = useState<ActiveLayer>(DEFAULT_ACTIVE_LAYER);
  const [layerInfoOpen, setLayerInfoOpen] = useState(false);
  // const [showLayerList, setShowLayerList] = useState(false); // TODO: uncomment with LayerBrowser

  // Bounding box drawing state
  const [isDrawingBbox, setIsDrawingBbox] = useState(false);
  const [drawnBbox, setDrawnBbox] = useState<{ north: number; south: number; east: number; west: number } | null>(null);
  const [downloadPanelOpen, setDownloadPanelOpen] = useState(false);

  // Color scale settings (with localStorage persistence)
  const [colorScaleMin, setColorScaleMin] = useState(() => {
    const saved = localStorage.getItem('sst-color-min');
    return saved ? parseFloat(saved) : -2;
  });
  const [colorScaleMax, setColorScaleMax] = useState(() => {
    const saved = localStorage.getItem('sst-color-max');
    return saved ? parseFloat(saved) : 35;
  });
  const [colormap, setColormap] = useState(() => {
    return localStorage.getItem('sst-colormap') || 'thermal';
  });
  const [colorScaleOpen, setColorScaleOpen] = useState(false);

  // Threshold masking state
  const [thresholdEnabled, setThresholdEnabled] = useState(false);
  const [thresholdMin, setThresholdMin] = useState<number | null>(null);
  const [thresholdMax, setThresholdMax] = useState<number | null>(null);

  // SST point query state
  const [sstPointData, setSstPointData] = useState<SSTPointQuery | null>(null);
  const [sstPointLoading, setSstPointLoading] = useState(false);
  const [clickedPosition, setClickedPosition] = useState<{ lon: number; lat: number } | null>(null);
  const [screenPosition, setScreenPosition] = useState<{ x: number; y: number } | null>(null);

  // Variable (SIC/SLA) point query state
  const [variablePointData, setVariablePointData] = useState<VariablePointQuery | null>(null);
  const [variablePointLoading, setVariablePointLoading] = useState(false);
  const [variableScreenPosition, setVariableScreenPosition] = useState<{ x: number; y: number } | null>(null);

  // Persist color scale preferences to localStorage
  useEffect(() => {
    localStorage.setItem('sst-color-min', String(colorScaleMin));
  }, [colorScaleMin]);

  useEffect(() => {
    localStorage.setItem('sst-color-max', String(colorScaleMax));
  }, [colorScaleMax]);

  useEffect(() => {
    localStorage.setItem('sst-colormap', colormap);
  }, [colormap]);

  // Update screen position when camera moves
  useEffect(() => {
    const viewer = cesiumRef.current?.viewer;
    if (!viewer || viewer.isDestroyed() || !clickedPosition) return;

    const updateScreenPos = () => {
      if (viewer.isDestroyed() || !clickedPosition) return;
      const cartesian = Cesium.Cartesian3.fromDegrees(clickedPosition.lon, clickedPosition.lat);
      const screenPos = Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene, cartesian);
      if (screenPos) {
        setScreenPosition({ x: screenPos.x, y: screenPos.y });
      } else {
        setScreenPosition(null); // Point not visible
      }
    };

    // Update initially with a small delay to ensure scene is rendered
    setTimeout(updateScreenPos, 50);

    // Listen for camera changes
    const removeListener = viewer.camera.changed.addEventListener(updateScreenPos);
    
    // Also listen for scene renders
    const postRenderListener = viewer.scene.postRender.addEventListener(updateScreenPos);
    
    return () => {
      removeListener();
      postRenderListener();
    };
  }, [clickedPosition, viewerReady]);

  // Handle map click - query visible layers at point
  const handleMapClick = useCallback(async (lon: number, lat: number) => {
    if (!selectedDate) return;
    
    // Get visible layers that support point queries
    const sstLayer = layers.find((l) => l.id === 'sst');
    const sicLayer = layers.find((l) => l.id === 'sic');
    const slaLayer = layers.find((l) => l.id === 'sla');
    const chlLayer = layers.find((l) => l.id === 'chl');
    const kd490Layer = layers.find((l) => l.id === 'kd490');
    
    // If no queryable layer is visible, do nothing
    if (!sstLayer?.visible && !sicLayer?.visible && !slaLayer?.visible && !chlLayer?.visible && !kd490Layer?.visible) return;
    
    // Calculate screen position
    const viewer = cesiumRef.current?.viewer;
    let currentScreenPos: { x: number; y: number } | null = null;
    if (viewer && !viewer.isDestroyed()) {
      const cartesian = Cesium.Cartesian3.fromDegrees(lon, lat);
      const screenPos = Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene, cartesian);
      if (screenPos) {
        currentScreenPos = { x: screenPos.x, y: screenPos.y };
      }
    }
    
    // Local Dataset point query
    if (activeMode === 'local' && activeDataset) {
      setClickedPosition({ lon, lat });
      setSstPointLoading(true);
      setSstPointData(null);
      setScreenPosition(currentScreenPos);

      try {
        const pdata = await fetchLocalPoint(
          activeDataset.id,
          lat,
          lon,
          localVariable || activeDataset.default_variable,
          localTimeIndex
        );
        setSstPointData({
          date: pdata.timestamp || selectedDate,
          lon: pdata.matched_lon,
          lat: pdata.matched_lat,
          sst: pdata.is_valid && pdata.value !== undefined ? pdata.value : null,
          unit: pdata.units || '',
          message: pdata.is_valid ? undefined : 'No data / Land cell'
        });
      } catch (err) {
        console.error('Failed to query local point:', err);
        setSstPointData({
          date: selectedDate,
          lon,
          lat,
          sst: null,
          unit: '',
          message: 'Failed to query local dataset point'
        });
      } finally {
        setSstPointLoading(false);
      }
      return;
    }

    // Query SST if visible
    if (sstLayer?.visible) {
      setClickedPosition({ lon, lat });
      setSstPointLoading(true);
      setSstPointData(null);
      setScreenPosition(currentScreenPos);
      
      try {
        const data = await fetchSSTPoint(selectedDate, lon, lat);
        setSstPointData(data);
      } catch (err) {
        console.error('Failed to fetch SST point:', err);
        setSstPointData({
          date: selectedDate,
          lon,
          lat,
          sst: null,
          unit: '°C',
          message: 'Failed to query SST data'
        });
      } finally {
        setSstPointLoading(false);
      }
    }
    
    // Query SIC, SLA, CHL, or KD490 if visible (prefer SIC > SLA > CHL > KD490 if multiple visible)
    const variableToQuery = sicLayer?.visible ? 'sic' : slaLayer?.visible ? 'sla' : chlLayer?.visible ? 'chl' : kd490Layer?.visible ? 'kd490' : null;
    if (variableToQuery) {
      setVariablePointLoading(true);
      setVariablePointData(null);
      setVariableScreenPosition(currentScreenPos);
      
      try {
        const data = await fetchVariablePoint(variableToQuery, selectedDate, lon, lat);
        setVariablePointData(data);
      } catch (err) {
        console.error(`Failed to fetch ${variableToQuery.toUpperCase()} point:`, err);
        const unitMap: Record<string, string> = { sic: '%', sla: 'm', chl: 'mg/m³' };
        setVariablePointData({
          date: selectedDate,
          variable: variableToQuery,
          lon,
          lat,
          value: null,
          unit: unitMap[variableToQuery] || '',
          message: `Failed to query ${variableToQuery.toUpperCase()} data`
        });
      } finally {
        setVariablePointLoading(false);
      }
    }
  }, [selectedDate, layers]);

  const handleCloseSstPanel = useCallback(() => {
    setSstPointData(null);
    setSstPointLoading(false);
    setClickedPosition(null);
    setScreenPosition(null);
  }, []);

  const handleCloseVariablePanel = useCallback(() => {
    setVariablePointData(null);
    setVariablePointLoading(false);
    setVariableScreenPosition(null);
  }, []);

  // Close SST panel if SST layer is hidden
  useEffect(() => {
    const sstLayer = layers.find((l) => l.id === 'sst');
    if (sstLayer && !sstLayer.visible && (sstPointData || sstPointLoading)) {
      setSstPointData(null);
      setSstPointLoading(false);
      setClickedPosition(null);
      setScreenPosition(null);
    }
  }, [layers, sstPointData, sstPointLoading]);

  // Close variable panel if its layer is hidden
  useEffect(() => {
    if (!variablePointData && !variablePointLoading) return;
    const variable = variablePointData?.variable;
    if (variable) {
      const layer = layers.find((l) => l.id === variable);
      if (layer && !layer.visible) {
        setVariablePointData(null);
        setVariablePointLoading(false);
        setVariableScreenPosition(null);
      }
    }
  }, [layers, variablePointData, variablePointLoading]);

  const handleToggleLayer = useCallback((layerId: string) => {
    // Toggle individual layer visibility (overlay mode - multiple layers allowed)
    setLayers((prev) => {
      const newLayers = prev.map((layer) =>
        layer.id === layerId 
          ? { ...layer, visible: !layer.visible } 
          : layer
      );
      // Persist visibility to localStorage
      const visibility: Record<string, boolean> = {};
      newLayers.forEach(l => { visibility[l.id] = l.visible; });
      localStorage.setItem('layer-visibility', JSON.stringify(visibility));
      
      // Update URL with visible layers
      const visibleIds = newLayers.filter(l => l.visible).map(l => l.id);
      updateLayersUrl(visibleIds);
      
      return newLayers;
    });
    
    // Also update activeLayer if toggling on (for colorscale reference)
    const layerToCategory: Record<string, { categoryId: string; productId: string; variableId: string }> = {
      'sst': { categoryId: 'ocean-temp', productId: 'sst-monthly', variableId: 'sst' },
      'sic': { categoryId: 'ocean-ice', productId: 'sic-monthly', variableId: 'sic' },
      'sla': { categoryId: 'ocean-ssh', productId: 'sla-daily', variableId: 'sla' },
      'chl': { categoryId: 'ocean-bio', productId: 'chl-daily', variableId: 'chl' },
    };
    
    // Set activeLayer to the toggled layer if it's being turned on
    const layer = layers.find(l => l.id === layerId);
    if (layer && !layer.visible && layerToCategory[layerId]) {
      setActiveLayer(layerToCategory[layerId]);
    }
  }, [layers, updateLayersUrl]);

  const handleBasemapChange = useCallback((id: BasemapId) => {
    cesiumRef.current?.setBasemap(id);
    setCurrentBasemap(id);
  }, []);

  const handleLabelsToggle = useCallback(() => {
    cesiumRef.current?.toggleLabels();
    setLabelsVisible(prev => !prev);
  }, []);

  // Force re-render when cesium viewer is ready
  useEffect(() => {
    const checkViewer = setInterval(() => {
      const viewer = cesiumRef.current?.viewer;
      if (viewer && !viewer.isDestroyed() && !viewerReady) {
        setViewerReady(true);
        clearInterval(checkViewer);
      }
    }, 50);
    return () => clearInterval(checkViewer);
  }, [viewerReady]);

  // Check on mount if a local dataset is already active on the server
  useEffect(() => {
    async function checkActiveDataset() {
      try {
        const modeData = await fetchActiveMode();
        if (modeData.mode === 'local' && modeData.dataset) {
          setActiveMode('local');
          setActiveDataset(modeData.dataset);
          setLocalVariable(modeData.dataset.default_variable || Object.keys(modeData.dataset.variables)[0] || '');
          const ts = modeData.dataset.time_axis.timestamps;
          if (ts && ts.length > 0) {
            setSelectedDate(ts[0]);
            setTimeRange({
              total_months: 1,
              start_date: modeData.dataset.time_axis.start_time || ts[0],
              end_date: modeData.dataset.time_axis.end_time || ts[ts.length - 1],
              available_dates: ts,
              years: {},
            });
            setIsLoading(false);
          }
        }
      } catch (err) {
        console.warn('Could not check active dataset on start:', err);
      }
    }
    checkActiveDataset();
  }, []);

  // Fetch available time range on mount and when variable changes (only when in online mode)
  useEffect(() => {
    if (activeMode === 'local') return;

    async function loadTimeRange() {
      try {
        setIsLoading(true);
        
        // Fetch dates for current variable
        const currentVar = activeLayer?.variableId || 'sst';
        const data = await fetchTimeRangeForVariable(currentVar);
        setTimeRange(data);
        
        // If current date not available, select best alternative
        if (data.available_dates.length > 0) {
          const currentAvailable = data.available_dates.includes(selectedDate);
          if (!currentAvailable) {
            // Priority: URL date > most recent available date
            let dateToSelect = '';
            if (initialUrlDate && data.available_dates.includes(initialUrlDate)) {
              dateToSelect = initialUrlDate;
            } else {
              // Use most recent available date
              dateToSelect = data.available_dates[data.available_dates.length - 1];
            }
            setSelectedDate(dateToSelect);
            updateUrlState(dateToSelect);
          }
        }
        
        setError(null);
      } catch (err) {
        console.error('Failed to load time range:', err);
        setError('Unable to load available dates from server.');
        // Use MOCK_DATES as minimal fallback so UI is not empty
        const years: Record<string, number[]> = {};
        MOCK_DATES.forEach(date => {
          const [year, month] = date.split('-');
          if (!years[year]) years[year] = [];
          years[year].push(parseInt(month, 10));
        });
        if (MOCK_DATES.length > 0) {
          setTimeRange({
            total_months: MOCK_DATES.length,
            start_date: MOCK_DATES[0],
            end_date: MOCK_DATES[MOCK_DATES.length - 1],
            available_dates: MOCK_DATES,
            years,
          });
          const fallbackDate = MOCK_DATES[MOCK_DATES.length - 1];
          setSelectedDate(fallbackDate);
          updateUrlState(fallbackDate);
        }
      } finally {
        setIsLoading(false);
      }
    }
    loadTimeRange();
  }, [initialUrlDate, updateUrlState, activeLayer?.variableId, activeMode]);

  const handleDatasetActivated = useCallback((dataset: DatasetInfo) => {
    setActiveMode('local');
    setActiveDataset(dataset);
    setLocalVariable(dataset.default_variable || Object.keys(dataset.variables)[0] || '');
    setLocalTimeIndex(0);
    const ts = dataset.time_axis.timestamps;
    if (ts && ts.length > 0) {
      setSelectedDate(ts[0]);
      setTimeRange({
        total_months: 1,
        start_date: dataset.time_axis.start_time || ts[0],
        end_date: dataset.time_axis.end_time || ts[ts.length - 1],
        available_dates: ts,
        years: {},
      });
    }
  }, []);

  const handleDatasetDeactivated = useCallback(() => {
    setActiveMode('online');
    setActiveDataset(null);
    setLocalVariable('');
    setLocalTimeIndex(0);
    // Reload online time range
    fetchTimeRangeForVariable('sst').then(data => {
      setTimeRange(data);
      if (data.available_dates.length > 0) {
        const latestDate = data.available_dates[data.available_dates.length - 1];
        setSelectedDate(latestDate);
        updateUrlState(latestDate);
      }
    }).catch(console.error);
  }, [updateUrlState]);

  const handleDateChange = useCallback((date: string) => {
    setSelectedDate(date);
    updateUrlState(date);
    if (activeMode === 'local' && activeDataset) {
      const tsList = activeDataset.time_axis.timestamps;
      const idx = tsList.indexOf(date);
      if (idx >= 0) {
        setLocalTimeIndex(idx);
      }
    }
  }, [updateUrlState, activeMode, activeDataset]);

  // Keyboard shortcuts: Arrow keys for date, +/- for zoom
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if typing in input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      
      const viewer = cesiumRef.current?.viewer;
      
      switch (e.key) {
        case 'ArrowLeft':
          // Previous date
          if (timeRange?.available_dates) {
            const currentIdx = timeRange.available_dates.indexOf(selectedDate);
            if (currentIdx > 0) {
              handleDateChange(timeRange.available_dates[currentIdx - 1]);
            }
          }
          break;
        case 'ArrowRight':
          // Next date
          if (timeRange?.available_dates) {
            const currentIdx = timeRange.available_dates.indexOf(selectedDate);
            if (currentIdx < timeRange.available_dates.length - 1) {
              handleDateChange(timeRange.available_dates[currentIdx + 1]);
            }
          }
          break;
        case '+':
        case '=':
          // Zoom in
          if (viewer && !viewer.isDestroyed()) {
            viewer.camera.zoomIn(viewer.camera.positionCartographic.height * 0.3);
          }
          break;
        case '-':
        case '_':
          // Zoom out
          if (viewer && !viewer.isDestroyed()) {
            viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.3);
          }
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedDate, timeRange, handleDateChange]);

  const sidebarWidth = sidebarCollapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH;

  // Memoize visibleLayers to avoid unnecessary re-renders - only change when actual visibility changes
  const visibleLayersKey = layers.filter(l => l.visible).map(l => l.id).join(',');
  const visibleLayers = useMemo(() => {
    const visible = visibleLayersKey.split(',').filter(Boolean);
    return visible;
  }, [visibleLayersKey]);

  return (
    <Box sx={{ 
      position: 'fixed', 
      top: 0, 
      left: 0, 
      right: 0, 
      bottom: 0, 
      width: '100vw', 
      height: '100vh', 
      overflow: 'hidden' 
    }}>
      {/* Globe - Full screen background */}
      <CesiumViewer 
        ref={cesiumRef} 
        selectedDate={selectedDate} 
        isLoading={isLoading} 
        initialBasemap={currentBasemap}
        onMapClick={handleMapClick}
        clickedPosition={clickedPosition}
        colorScaleMin={colorScaleMin}
        colorScaleMax={colorScaleMax}
        drawingMode={false}
        onBboxDrawn={() => {}}
        activeVariable={activeLayer?.variableId || 'sst'}
        visibleLayers={visibleLayers}
        initialCamera={initialCamera}
        onCameraChange={handleCameraChange}
        thresholdEnabled={thresholdEnabled}
        thresholdMin={thresholdMin}
        thresholdMax={thresholdMax}
        activeMode={activeMode}
        activeDataset={activeDataset}
        localVariable={localVariable}
        localTimeIndex={localTimeIndex}
        colormap={colormap}
      />

      {/* Bounding Box Drawing Overlay */}
      <BboxDrawingOverlay
        active={isDrawingBbox}
        onComplete={(bbox: BoundingBox) => {
          setDrawnBbox(bbox);
          setIsDrawingBbox(false);
        }}
        onCancel={() => {
          setIsDrawingBbox(false);
        }}
        initialBbox={drawnBbox}
        viewer={cesiumRef.current?.viewer || null}
      />

      {/* Download Panel */}
      {downloadPanelOpen && (
        <DownloadPanel
          bbox={drawnBbox}
          selectedDate={selectedDate}
          variable={activeLayer?.variableId || 'sst'}
          onClose={() => {
            setDownloadPanelOpen(false);
            setDrawnBbox(null);
          }}
          onStartDrawing={() => setIsDrawingBbox(true)}
          isDrawingMode={isDrawingBbox}
        />
      )}

      {/* Map Controls - Bottom right (only when viewer ready) */}
      {viewerReady && cesiumRef.current && (
        <MapControls
          viewer={cesiumRef.current.viewer}
          currentBasemap={currentBasemap}
          onBasemapChange={handleBasemapChange}
          bottomOffset={timelineCollapsed ? 80 : 210}
          colorScaleOpen={colorScaleOpen}
          onColorScaleToggle={() => setColorScaleOpen(!colorScaleOpen)}
          onStartDrawing={() => {
            // Close info panels if open
            handleCloseSstPanel();
            handleCloseVariablePanel();
            setIsDrawingBbox(true);
            setDownloadPanelOpen(true);
          }}
          isDrawingMode={isDrawingBbox}
          labelsVisible={labelsVisible}
          onLabelsToggle={handleLabelsToggle}
        />
      )}

      {/* Mouse Coordinates - Bottom left */}
      {viewerReady && cesiumRef.current && (
        <MouseCoordinates
          viewer={cesiumRef.current.viewer}
          bottomOffset={timelineCollapsed ? 56 : 186}
          leftOffset={sidebarWidth + 24}
        />
      )}

      {/* Color Scale Controls - Bottom right, above map controls */}
      {colorScaleOpen && (
        <ColorScaleControls
          minTemp={colorScaleMin}
          maxTemp={colorScaleMax}
          colormap={colormap}
          onMinTempChange={setColorScaleMin}
          onMaxTempChange={setColorScaleMax}
          onColormapChange={setColormap}
          bottomOffset={timelineCollapsed ? 130 : 260}
          thresholdEnabled={thresholdEnabled}
          thresholdMin={thresholdMin}
          thresholdMax={thresholdMax}
          onThresholdEnabledChange={setThresholdEnabled}
          onThresholdMinChange={setThresholdMin}
          onThresholdMaxChange={setThresholdMax}
        />
      )}

      {/* Analytics Panel - Fullscreen variable browser */}
      <AnalyticsPanel 
        open={analyticsPanelOpen} 
        onClose={handleCloseAnalytics} 
      />

      {/* Settings Panel */}
      <SettingsPanel
        open={settingsPanelOpen}
        onClose={handleCloseSettings}
      />

      {/* About Panel */}
      <AboutPanel
        open={aboutPanelOpen}
        onClose={handleCloseAbout}
      />

      {/* Data Provenance Panel */}
      <DataProvenancePage
        open={dataProvenanceOpen}
        onClose={handleCloseDataProvenance}
      />

      {/* Terms of Use Panel */}
      <TermsOfUsePage
        open={termsOpen}
        onClose={handleCloseTerms}
      />

      {/* Bookmarks Panel */}
      <BookmarksPanel
        open={bookmarksPanelOpen}
        onClose={handleCloseBookmarks}
        currentLat={currentCameraPosition.lat}
        currentLon={currentCameraPosition.lon}
        currentHeight={currentCameraPosition.height}
        currentDate={selectedDate}
        currentLayers={visibleLayers}
        currentBasemap={currentBasemap}
        onLoadBookmark={handleLoadBookmark}
      />

      {/* SST Point Query Panel */}
      <SSTInfoPanel
        data={sstPointData}
        loading={sstPointLoading}
        onClose={handleCloseSstPanel}
        screenPosition={screenPosition}
      />

      {/* Variable (SIC/SLA) Point Query Panel */}
      <VariableInfoPanel
        data={variablePointData}
        loading={variablePointLoading}
        onClose={handleCloseVariablePanel}
        screenPosition={variableScreenPosition}
        topOffset={(sstPointData || sstPointLoading) ? 420 : 0}
      />

      {/* Data Layers Panel - with download, info, and details */}
      <LayersPanelPopup
        open={layersPanelOpen}
        onClose={() => setLayersPanelOpen(false)}
        layers={layers}
        onToggleLayer={handleToggleLayer}
        anchorTop={64}
        anchorLeft={sidebarWidth + 20}
        selectedDate={selectedDate}
        onOpenInfo={() => setLayerInfoOpen(true)}
        onStartDrawing={() => {
          handleCloseSstPanel();
          handleCloseVariablePanel();
          setIsDrawingBbox(true);
        }}
        drawnBbox={drawnBbox}
        isDrawingMode={isDrawingBbox}
        onOpenCatalog={() => {
          setLayersPanelOpen(false);
          handleOpenAnalytics();
        }}
      />

      {/* Layer Browser - Variable catalog (hidden for now, accessible via LayersPanelPopup) */}
      {/* <LayerBrowser
        open={layersPanelOpen}
        onClose={() => setLayersPanelOpen(false)}
        anchorTop={64}
        anchorLeft={sidebarWidth + 20}
        selectedDate={selectedDate}
        activeLayer={activeLayer}
        onLayerSelect={setActiveLayer}
        colorScaleMin={colorScaleMin}
        colorScaleMax={colorScaleMax}
        colormap={colormap}
        onOpenInfo={() => setLayerInfoOpen(true)}
        showLayerList={showLayerList}
        onToggleLayerList={() => setShowLayerList(!showLayerList)}
        onStartDrawing={() => {
          // Close SST panel if open
          handleCloseSstPanel();
          setIsDrawingBbox(true);
        }}
        drawnBbox={drawnBbox}
        isDrawingMode={isDrawingBbox}
      /> */}

      {/* Layer Info Dialog */}
      <LayerInfoDialog
        open={layerInfoOpen}
        onClose={() => setLayerInfoOpen(false)}
        variable={activeLayer?.variableId || 'sst'}
        layerName="Sea Surface Temperature"
      />

      {/* Floating Header */}
      <Header
        activeDataset={activeDataset}
        activeMode={activeMode}
        onOpenLocalModal={() => setLocalModalOpen(true)}
        onSwitchToOnline={handleDatasetDeactivated}
      />

      {/* Local Dataset Ingestion & Inspection Modal */}
      <LocalDatasetModal
        open={localModalOpen}
        onClose={() => setLocalModalOpen(false)}
        activeDataset={activeDataset}
        onDatasetActivated={handleDatasetActivated}
        onDatasetDeactivated={handleDatasetDeactivated}
      />

      {/* Floating Variable Selector for Local Multi-Variable Datasets */}
      {activeMode === 'local' && activeDataset && (
        <Box sx={{ position: 'absolute', top: 58, right: 12, zIndex: 1000 }}>
          <DatasetVariableSelector
            dataset={activeDataset}
            selectedVariable={localVariable}
            onSelectVariable={setLocalVariable}
          />
        </Box>
      )}

      {/* Floating Playback Controls for Multi-Frame Datasets */}
      {activeMode === 'local' && activeDataset && activeDataset.time_axis.count > 1 && (
        <Box sx={{ position: 'absolute', bottom: 85, left: sidebarWidth + 20, zIndex: 1000 }}>
          <PlaybackControls
            timestamps={activeDataset.time_axis.timestamps}
            currentIndex={localTimeIndex}
            onIndexChange={(idx) => {
              setLocalTimeIndex(idx);
              const ts = activeDataset.time_axis.timestamps[idx];
              if (ts) {
                setSelectedDate(ts);
                updateUrlState(ts);
              }
            }}
            datasetId={activeDataset.id}
            variable={localVariable}
            resolution={activeDataset.time_axis.resolution}
          />
        </Box>
      )}

      {/* Floating Sidebar */}
      <Box
        sx={{
          position: 'absolute',
          top: 52,
          left: 12,
          bottom: 80,
          width: sidebarWidth,
          bgcolor: 'rgba(8, 12, 18, 0.85)',
          backdropFilter: 'blur(16px)',
          borderRadius: 0,
          border: '1px solid rgba(255,255,255,0.04)',
          overflow: 'hidden',
          transition: 'width 0.2s ease',
          zIndex: 1000,
        }}
      >
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          onOpenLayers={() => setLayersPanelOpen(!layersPanelOpen)}
          onOpenAnalytics={handleOpenAnalytics}
          onFlyHome={() => cesiumRef.current?.flyHome()}
          onOpenSettings={handleOpenSettings}
          onOpenAbout={handleOpenAbout}
          onOpenBookmarks={handleOpenBookmarks}
        />
      </Box>

      {/* Error overlay */}
      {error && (
        <Box
          sx={{
            position: 'absolute',
            top: 72,
            left: sidebarWidth + 24,
            bgcolor: 'rgba(183, 28, 28, 0.9)',
            color: 'white',
            px: 2,
            py: 1,
            borderRadius: 0,
            fontSize: '0.8125rem',
            zIndex: 1000,
          }}
        >
          {error}
        </Box>
      )}

      {/* Floating Time Slider Panel - Bottom */}
      <Box
        sx={{
          position: 'absolute',
          bottom: 12,
          left: 12,
          right: 12,
          bgcolor: 'rgba(8, 12, 18, 0.85)',
          backdropFilter: 'blur(16px)',
          borderRadius: 0,
          border: '1px solid rgba(255,255,255,0.04)',
          overflow: 'hidden',
          zIndex: 1000,
        }}
      >
        <TimeSlider
          availableDates={timeRange?.available_dates?.length ? timeRange.available_dates : MOCK_DATES}
          selectedDate={selectedDate || MOCK_DATES[MOCK_DATES.length - 1]}
          onDateChange={handleDateChange}
          isLoading={isLoading}
          collapsed={timelineCollapsed}
          onToggleCollapsed={() => {
            const newValue = !timelineCollapsed;
            setTimelineCollapsed(newValue);
            localStorage.setItem('timeline-collapsed', String(newValue));
          }}
        />
      </Box>

      {/* Footer */}
      <Footer />
    </Box>
  );
}
