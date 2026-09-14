/**
 * Analytics Panel - Professional Zarr Variable Browser
 * 
 * A sophisticated data browser for oceanographic ECV datasets stored as Zarr.
 * Features:
 * - Multi-dataset catalog browser
 * - Full Zarr metadata inspection
 * - Chunk and storage information
 * - Pre-computed statistics display
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Paper,
  Typography,
  CircularProgress,
  IconButton,
  Alert,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Collapse,
  TextField,
  InputAdornment,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  LinearProgress,
} from '@mui/material';
import {
  Close as CloseIcon,
  ExpandMore as ExpandMoreIcon,
  ChevronRight as ChevronRightIcon,
  Search as SearchIcon,
  Folder as FolderIcon,
  FolderOpen as FolderOpenIcon,
  Dataset as DatasetIcon,
  GridOn as GridOnIcon,
  Schedule as ScheduleIcon,
  TrendingUp as TrendUpIcon,
  Functions as FunctionsIcon,
  Straighten as StraightenIcon,
  WaterDrop as WaterIcon,
  Storage as StorageIcon,
  Memory as MemoryIcon,
  Code as CodeIcon,
  Info as InfoIcon,
  Assessment as AssessmentIcon,
  ViewModule as ViewModuleIcon,
  Public as PublicIcon,
  InsertDriveFile as InsertDriveFileIcon,
} from '@mui/icons-material';

// Types
interface DatasetCatalogItem {
  id: string;
  name: string;
  description: string;
  n_arrays: number;
  n_timesteps: number;
  size_bytes: number;
  time_range: { start: string | null; end: string | null } | null;
}

interface ZarrArrayInfo {
  shape: number[];
  dtype: string;
  chunks: number[] | null;
  attrs?: Record<string, unknown>;
}

interface ZarrInfo {
  variable: string;
  title: string;
  source: string;
  created: string;
  global_stats: {
    temporal_mean: number;
    temporal_std: number;
    temporal_min: number;
    temporal_max: number;
    n_timesteps: number;
    date_range: [string, string] | null;
  };
  arrays: Record<string, ZarrArrayInfo>;
  bounds: {
    lat: [number, number];
    lon: [number, number];
  };
  time_range: {
    start: string;
    end: string;
    count: number;
  };
}

interface AnalyticsPanelProps {
  open: boolean;
  onClose: () => void;
}

// File tree item for Zarr file browser
interface FileTreeItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number;
  children?: FileTreeItem[];
}

interface ZarrFilesResponse {
  variable: string;
  root: string;
  total_size: number;
  tree: FileTreeItem[];
}

const API_BASE = '/api';

// Format days-since-epoch to "Mon YYYY" string
function formatDateRange(timeRange: { start: string | null; end: string | null } | null): string {
  if (!timeRange || !timeRange.start || !timeRange.end) return 'No data';
  
  const formatDate = (daysStr: string) => {
    const days = parseInt(daysStr, 10);
    if (isNaN(days)) return daysStr;
    const date = new Date(days * 24 * 60 * 60 * 1000);
    const month = date.toLocaleString('en-US', { month: 'short' });
    const year = date.getFullYear();
    return `${month} ${year}`;
  };
  
  const start = formatDate(timeRange.start);
  const end = formatDate(timeRange.end);
  
  return start === end ? start : `${start} – ${end}`;
}

// Color scheme - warm amber/orange accent on dark gray
const ACCENT_COLOR = '#FFB347';
const ACCENT_MUTED = 'rgba(255, 180, 50, 0.4)';
const BG_DARK = '#222222';
const BG_PANEL = '#1a1a1a';
const BORDER_COLOR = 'rgba(255, 180, 50, 0.15)';
const TEXT_PRIMARY = 'rgba(255, 255, 255, 0.92)';
const TEXT_SECONDARY = 'rgba(255, 255, 255, 0.55)';
const TEXT_MUTED = 'rgba(255, 255, 255, 0.35)';

// Variable type icons with semantic colors
const getVariableIcon = (name: string, isData: boolean = false) => {
  const dataColor = isData ? ACCENT_COLOR : TEXT_MUTED;
  if (name === 'sst') return <WaterIcon sx={{ fontSize: 16, color: ACCENT_COLOR }} />;
  if (name === 'chl' || name === 'chlorophyll') return <WaterIcon sx={{ fontSize: 16, color: '#4CAF50' }} />;
  if (name.includes('mean') || name.includes('std')) return <FunctionsIcon sx={{ fontSize: 16, color: dataColor }} />;
  if (name === 'trend') return <TrendUpIcon sx={{ fontSize: 16, color: dataColor }} />;
  if (name === 'valid_count') return <GridOnIcon sx={{ fontSize: 16, color: dataColor }} />;
  if (name === 'time') return <ScheduleIcon sx={{ fontSize: 16, color: TEXT_MUTED }} />;
  if (name === 'lat' || name === 'lon') return <StraightenIcon sx={{ fontSize: 16, color: TEXT_MUTED }} />;
  return <DatasetIcon sx={{ fontSize: 16, color: TEXT_MUTED }} />;
};

// Format bytes to human readable
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

// Estimate array size
const estimateSize = (shape: number[] | null, dtype: string): number => {
  if (!shape || shape.length === 0) return 0;
  const total = shape.reduce((a, b) => a * b, 1);
  const bytesPerElement = dtype.includes('float32') || dtype.includes('int32') ? 4 :
                         dtype.includes('float64') || dtype.includes('int64') ? 8 :
                         dtype.includes('int16') ? 2 : 4;
  return total * bytesPerElement;
};

// Calculate number of chunks
const countChunks = (shape: number[], chunks: number[] | null): number => {
  if (!chunks) return 1;
  return shape.reduce((acc, size, i) => acc * Math.ceil(size / (chunks[i] || size)), 1);
};

// Tab panel component
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel({ children, value, index }: TabPanelProps) {
  return (
    <div role="tabpanel" hidden={value !== index} style={{ height: '100%' }}>
      {value === index && <Box sx={{ pt: 2, height: '100%' }}>{children}</Box>}
    </div>
  );
}

// Monospace font family (apply fontSize separately to avoid conflicts)
const monoFont = {
  fontFamily: '"JetBrains Mono", "Fira Code", "SF Mono", Monaco, monospace',
  letterSpacing: '-0.02em',
};

// Full mono style with default size
const monoStyle = {
  ...monoFont,
  fontSize: '0.75rem',
};

// File tree view component for Zarr file browser
interface FileTreeViewProps {
  items: FileTreeItem[];
  depth: number;
  expandedPaths: Set<string>;
  onToggle: (path: string) => void;
}

const FileTreeView: React.FC<FileTreeViewProps> = ({ items, depth, expandedPaths, onToggle }) => {
  const getFileIcon = (name: string, type: 'file' | 'directory') => {
    if (type === 'directory') {
      return expandedPaths.has(name) 
        ? <FolderOpenIcon sx={{ fontSize: 14, color: ACCENT_COLOR }} />
        : <FolderIcon sx={{ fontSize: 14, color: TEXT_MUTED }} />;
    }
    // File type icons based on name
    if (name === '.zattrs' || name === '.zgroup' || name === '.zarray') {
      return <CodeIcon sx={{ fontSize: 12, color: '#4FC3F7' }} />;
    }
    // Chunk files (numeric names like 0.0.0)
    if (/^\d/.test(name)) {
      return <DatasetIcon sx={{ fontSize: 12, color: TEXT_MUTED }} />;
    }
    return <InsertDriveFileIcon sx={{ fontSize: 12, color: TEXT_MUTED }} />;
  };

  return (
    <List dense disablePadding sx={{ pl: depth > 0 ? 1.5 : 0 }}>
      {items.map((item) => (
        <React.Fragment key={item.path}>
          <ListItem disablePadding>
            <ListItemButton
              onClick={() => item.type === 'directory' && onToggle(item.path)}
              sx={{
                py: 0.25,
                px: 1,
                minHeight: 24,
                cursor: item.type === 'directory' ? 'pointer' : 'default',
                '&:hover': { bgcolor: item.type === 'directory' ? 'rgba(255,255,255,0.04)' : 'transparent' },
              }}
            >
              {item.type === 'directory' && (
                <ListItemIcon sx={{ minWidth: 16 }}>
                  {expandedPaths.has(item.path) ? (
                    <ExpandMoreIcon sx={{ fontSize: 12, color: TEXT_MUTED }} />
                  ) : (
                    <ChevronRightIcon sx={{ fontSize: 12, color: TEXT_MUTED }} />
                  )}
                </ListItemIcon>
              )}
              <ListItemIcon sx={{ minWidth: 20, ml: item.type === 'file' ? 2 : 0 }}>
                {getFileIcon(item.name, item.type)}
              </ListItemIcon>
              <ListItemText
                primary={item.name}
                primaryTypographyProps={{
                  fontSize: '0.68rem',
                  color: item.type === 'directory' ? TEXT_PRIMARY : TEXT_SECONDARY,
                  ...monoFont,
                }}
              />
              <Typography variant="caption" sx={{ color: TEXT_MUTED, ...monoStyle, fontSize: '0.55rem' }}>
                {formatBytes(item.size)}
              </Typography>
            </ListItemButton>
          </ListItem>
          {item.type === 'directory' && item.children && expandedPaths.has(item.path) && (
            <FileTreeView 
              items={item.children} 
              depth={depth + 1} 
              expandedPaths={expandedPaths} 
              onToggle={onToggle} 
            />
          )}
        </React.Fragment>
      ))}
    </List>
  );
};

export const AnalyticsPanel: React.FC<AnalyticsPanelProps> = ({ open, onClose }) => {
  // State
  const [catalog, setCatalog] = useState<DatasetCatalogItem[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [selectedDataset, setSelectedDataset] = useState<string>('sst');
  const [datasetInfo, setDatasetInfo] = useState<ZarrInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadTime, setLoadTime] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['data', 'coordinates', 'statistics']));
  const [selectedVariable, setSelectedVariable] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState(0);
  
  // File browser state
  const [fileTree, setFileTree] = useState<ZarrFilesResponse | null>(null);
  const [fileTreeLoading, setFileTreeLoading] = useState(false);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());

  // Fetch catalog when panel opens
  useEffect(() => {
    if (!open) return;
    
    const fetchCatalog = async () => {
      setCatalogLoading(true);
      try {
        const res = await fetch(`${API_BASE}/zarr/catalog`);
        if (res.ok) {
          const data = await res.json();
          setCatalog(data.datasets || []);
        }
      } catch (err) {
        console.error('Failed to fetch catalog:', err);
      } finally {
        setCatalogLoading(false);
      }
    };
    
    fetchCatalog();
  }, [open]);

  // Fetch dataset info when dataset changes
  useEffect(() => {
    if (!open || !selectedDataset) return;
    
    const fetchInfo = async () => {
      setLoading(true);
      setError(null);
      setSelectedVariable(null);
      const startTime = performance.now();
      
      try {
        const res = await fetch(`${API_BASE}/zarr/${selectedDataset}/info`);
        const elapsed = performance.now() - startTime;
        setLoadTime(elapsed);
        
        if (res.ok) {
          const data = await res.json();
          setDatasetInfo(data);
        } else {
          setError(`Failed to fetch ${selectedDataset} info`);
        }
      } catch (err) {
        console.error('Failed to fetch Zarr info:', err);
        setError('Network error - is the server running?');
      } finally {
        setLoading(false);
      }
    };
    
    fetchInfo();
  }, [open, selectedDataset]);

  // Fetch file tree when dataset changes
  useEffect(() => {
    if (!open || !selectedDataset) return;
    
    const fetchFileTree = async () => {
      setFileTreeLoading(true);
      try {
        const res = await fetch(`${API_BASE}/zarr/${selectedDataset}/files`);
        if (res.ok) {
          const data = await res.json();
          setFileTree(data);
          // Auto-expand root directories
          setExpandedPaths(new Set(data.tree.filter((item: FileTreeItem) => item.type === 'directory').map((item: FileTreeItem) => item.path)));
        }
      } catch (err) {
        console.error('Failed to fetch file tree:', err);
      } finally {
        setFileTreeLoading(false);
      }
    };
    
    fetchFileTree();
  }, [open, selectedDataset]);

  // Reset tab to 0 if Files tab (4) is selected but variable is not a data variable
  useEffect(() => {
    if (tabValue === 4 && selectedVariable) {
      const isData = selectedVariable === selectedDataset || 
                     selectedVariable === 'sst' || 
                     selectedVariable === 'chl';
      if (!isData) {
        setTabValue(0);
      }
    }
  }, [selectedVariable, selectedDataset, tabValue]);

  const toggleGroup = useCallback((group: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  }, []);

  const toggleFilePath = useCallback((path: string) => {
    setExpandedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  // Categorize variables
  const categories = useMemo(() => {
    if (!datasetInfo?.arrays) return { data: [], coordinates: [], statistics: [] };
    
    const cats: Record<string, string[]> = {
      data: [],
      coordinates: [],
      statistics: [],
    };
    
    Object.keys(datasetInfo.arrays).forEach(name => {
      if (name === selectedDataset || name === 'sst' || name === 'chl') {
        cats.data.push(name);
      } else if (['lat', 'lon', 'time'].includes(name)) {
        cats.coordinates.push(name);
      } else {
        cats.statistics.push(name);
      }
    });
    
    return cats;
  }, [datasetInfo, selectedDataset]);

  // Filter arrays by search
  const filteredCategories = useMemo(() => {
    if (!searchQuery) return categories;
    const query = searchQuery.toLowerCase();
    
    const filterCategory = (varNames: string[]) => 
      varNames.filter(name => {
        const arr = datasetInfo?.arrays[name];
        const attrs = arr?.attrs as Record<string, unknown> | undefined;
        return name.toLowerCase().includes(query) ||
               (attrs?.long_name as string)?.toLowerCase().includes(query) ||
               (attrs?.units as string)?.toLowerCase().includes(query);
      });
    
    return {
      data: filterCategory(categories.data),
      coordinates: filterCategory(categories.coordinates),
      statistics: filterCategory(categories.statistics),
    };
  }, [searchQuery, categories, datasetInfo]);

  if (!open) return null;

  const selectedArray = selectedVariable && datasetInfo?.arrays[selectedVariable];
  const totalArrays = Object.keys(datasetInfo?.arrays || {}).length;
  const totalSize = datasetInfo ? Object.entries(datasetInfo.arrays).reduce(
    (sum, [, arr]) => sum + estimateSize(arr.shape, arr.dtype), 0
  ) : 0;
  
  // Determine if selected variable is a "data" variable (show Files tab only for data)
  const isDataVariable = selectedVariable ? categories.data.includes(selectedVariable) : false;

  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        zIndex: 1200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {/* Backdrop */}
      <Box
        onClick={onClose}
        sx={{
          position: 'absolute',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
        }}
      />
      
      {/* Main Panel */}
      <Paper
        elevation={0}
        sx={{
          position: 'relative',
          width: '92vw',
          maxWidth: 1600,
          height: '92vh',
          maxHeight: 1000,
          backgroundColor: BG_DARK,
          borderRadius: 0,
          border: `1px solid ${BORDER_COLOR}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            px: 2.5,
            py: 1.25,
            borderBottom: `1px solid ${BORDER_COLOR}`,
            bgcolor: 'rgba(0,0,0,0.4)',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <StorageIcon sx={{ color: ACCENT_COLOR, fontSize: 22 }} />
            <Box>
              <Typography variant="subtitle1" fontWeight={600} sx={{ lineHeight: 1.2, color: TEXT_PRIMARY }}>
                Variable Browser
              </Typography>
              <Typography variant="caption" sx={{ color: TEXT_MUTED, ...monoFont, fontSize: '0.68rem' }}>
                zarr://ocean-ecv/{selectedDataset}
              </Typography>
            </Box>
          </Box>
          
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {loadTime !== null && (
              <Chip 
                size="small" 
                label={`${loadTime.toFixed(0)}ms`}
                sx={{ 
                  height: 20,
                  bgcolor: 'rgba(255,255,255,0.05)', 
                  color: TEXT_MUTED,
                  ...monoFont,
                  fontSize: '0.65rem',
                }}
              />
            )}
            <IconButton 
              onClick={onClose} 
              size="small"
              sx={{ 
                color: TEXT_MUTED,
                '&:hover': { color: '#fff', bgcolor: 'rgba(255,255,255,0.08)' },
                borderRadius: 0.5,
              }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>

        {/* Content */}
        <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
          {/* Left Panel: Dataset Catalog */}
          <Box
            sx={{
              width: 200,
              borderRight: `1px solid ${BORDER_COLOR}`,
              display: 'flex',
              flexDirection: 'column',
              bgcolor: BG_PANEL,
            }}
          >
            <Box sx={{ px: 1.5, py: 1, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <Typography variant="caption" sx={{ color: TEXT_MUTED, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.6rem' }}>
                Datasets
              </Typography>
            </Box>
            
            <Box sx={{ flex: 1, overflow: 'auto' }}>
              {catalogLoading ? (
                <Box sx={{ p: 2 }}><LinearProgress sx={{ bgcolor: 'rgba(255,255,255,0.05)', '& .MuiLinearProgress-bar': { bgcolor: ACCENT_COLOR } }} /></Box>
              ) : (
                <List dense disablePadding>
                  {catalog.map(ds => (
                    <ListItem key={ds.id} disablePadding>
                      <ListItemButton
                        selected={selectedDataset === ds.id}
                        onClick={() => setSelectedDataset(ds.id)}
                        sx={{
                          py: 1,
                          px: 1.5,
                          borderRadius: 0,
                          borderLeft: selectedDataset === ds.id ? `2px solid ${ACCENT_COLOR}` : '2px solid transparent',
                          '&.Mui-selected': {
                            bgcolor: 'rgba(255, 180, 50, 0.08)',
                            '&:hover': { bgcolor: 'rgba(255, 180, 50, 0.12)' },
                          },
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 28 }}>
                          <PublicIcon sx={{ fontSize: 16, color: selectedDataset === ds.id ? ACCENT_COLOR : TEXT_MUTED }} />
                        </ListItemIcon>
                        <ListItemText
                          primary={ds.id.toUpperCase()}
                          secondary={formatDateRange(ds.time_range)}
                          primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 600, color: TEXT_PRIMARY }}
                          secondaryTypographyProps={{ fontSize: '0.65rem', color: TEXT_MUTED }}
                        />
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              )}
            </Box>
          </Box>

          {/* Middle Panel: Variable Tree */}
          <Box
            sx={{
              width: 300,
              borderRight: '1px solid rgba(255, 255, 255, 0.06)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              bgcolor: 'rgba(0,0,0,0.2)',
            }}
          >
            {/* Search */}
            <Box sx={{ p: 1.5 }}>
              <TextField
                fullWidth
                size="small"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon sx={{ color: TEXT_MUTED, fontSize: 18 }} />
                    </InputAdornment>
                  ),
                }}
                sx={{
                  '& .MuiOutlinedInput-root': {
                    backgroundColor: 'rgba(0,0,0,0.3)',
                    borderRadius: 0,
                    fontSize: '0.8rem',
                    '& fieldset': { borderColor: 'rgba(255,255,255,0.06)' },
                    '&:hover fieldset': { borderColor: 'rgba(255,255,255,0.12)' },
                    '&.Mui-focused fieldset': { borderColor: ACCENT_MUTED },
                  },
                  '& .MuiInputBase-input': { py: 0.75 },
                }}
              />
            </Box>

            {/* Variable tree */}
            <Box sx={{ flex: 1, overflow: 'auto', px: 0.5 }}>
              {loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress size={28} sx={{ color: ACCENT_COLOR }} />
                </Box>
              ) : error ? (
                <Alert severity="error" sx={{ m: 1, borderRadius: 0 }}>{error}</Alert>
              ) : (
                <List dense disablePadding>
                  {Object.entries(filteredCategories).map(([category, variables]) => (
                    variables.length > 0 && (
                      <React.Fragment key={category}>
                        <ListItem disablePadding>
                          <ListItemButton
                            onClick={() => toggleGroup(category)}
                            sx={{ borderRadius: 0, py: 0.5, px: 1.5 }}
                          >
                            <ListItemIcon sx={{ minWidth: 24 }}>
                              {expandedGroups.has(category) ? (
                                <ExpandMoreIcon sx={{ fontSize: 14, color: ACCENT_COLOR }} />
                              ) : (
                                <ChevronRightIcon sx={{ fontSize: 14, color: TEXT_MUTED }} />
                              )}
                            </ListItemIcon>
                            <ListItemIcon sx={{ minWidth: 24 }}>
                              {expandedGroups.has(category) ? (
                                <FolderOpenIcon sx={{ fontSize: 15, color: ACCENT_COLOR }} />
                              ) : (
                                <FolderIcon sx={{ fontSize: 15, color: TEXT_MUTED }} />
                              )}
                            </ListItemIcon>
                            <ListItemText 
                              primary={category.toUpperCase()}
                              primaryTypographyProps={{ 
                                fontSize: '0.7rem',
                                fontWeight: 600,
                                letterSpacing: 0.8,
                                color: TEXT_SECONDARY,
                              }}
                            />
                            <Typography variant="caption" sx={{ color: TEXT_MUTED, fontSize: '0.6rem' }}>
                              {variables.length}
                            </Typography>
                          </ListItemButton>
                        </ListItem>
                        <Collapse in={expandedGroups.has(category)}>
                          <List dense disablePadding sx={{ pl: 2 }}>
                            {variables.map(varName => {
                              const arr = datasetInfo?.arrays[varName];
                              const attrs = arr?.attrs as Record<string, unknown> | undefined;
                              const isDataVar = category === 'data';
                              return (
                                <ListItem key={varName} disablePadding>
                                  <ListItemButton
                                    selected={selectedVariable === varName}
                                    onClick={() => setSelectedVariable(varName)}
                                    sx={{ 
                                      borderRadius: 0, 
                                      py: 0.5, 
                                      px: 1,
                                      borderLeft: selectedVariable === varName ? `2px solid ${ACCENT_COLOR}` : '2px solid transparent',
                                      '&.Mui-selected': {
                                        bgcolor: 'rgba(255, 180, 50, 0.08)',
                                        '&:hover': { bgcolor: 'rgba(255, 180, 50, 0.12)' },
                                      },
                                    }}
                                  >
                                    <ListItemIcon sx={{ minWidth: 26 }}>
                                      {getVariableIcon(varName, isDataVar)}
                                    </ListItemIcon>
                                    <ListItemText
                                      primary={varName}
                                      secondary={attrs?.long_name as string || arr?.dtype}
                                      primaryTypographyProps={{ fontSize: '0.78rem', fontWeight: 500, color: TEXT_PRIMARY }}
                                      secondaryTypographyProps={{ fontSize: '0.62rem', noWrap: true, sx: { color: TEXT_MUTED } }}
                                    />
                                    {arr && (
                                      <Typography variant="caption" sx={{ color: TEXT_MUTED, ...monoStyle, fontSize: '0.58rem' }}>
                                        {formatBytes(estimateSize(arr.shape, arr.dtype))}
                                      </Typography>
                                    )}
                                  </ListItemButton>
                                </ListItem>
                              );
                            })}
                          </List>
                        </Collapse>
                      </React.Fragment>
                    )
                  ))}
                </List>
              )}
            </Box>

            {/* Summary footer */}
            {datasetInfo && (
              <Box sx={{ px: 1.5, py: 1, borderTop: '1px solid rgba(255,255,255,0.05)', bgcolor: 'rgba(0,0,0,0.2)' }}>
                <Typography variant="caption" sx={{ color: TEXT_MUTED, ...monoStyle, fontSize: '0.62rem' }}>
                  {totalArrays} arrays · {datasetInfo.time_range.count} timesteps · {formatBytes(totalSize)}
                </Typography>
              </Box>
            )}
          </Box>

          {/* Right Panel: Variable Details */}
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {selectedVariable && selectedArray ? (
              <>
                {/* Variable header */}
                <Box sx={{ p: 2.5, borderBottom: '1px solid rgba(255,255,255,0.06)', bgcolor: 'rgba(0,0,0,0.15)' }}>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, mb: 2 }}>
                    <Box sx={{ 
                      p: 1, 
                      bgcolor: 'rgba(255, 180, 50, 0.1)', 
                      border: `1px solid ${ACCENT_MUTED}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      {getVariableIcon(selectedVariable, categories.data.includes(selectedVariable))}
                    </Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="h6" fontWeight={600} sx={{ lineHeight: 1.2, color: TEXT_PRIMARY, ...monoFont, fontSize: '1.1rem' }}>
                        {selectedVariable}
                      </Typography>
                      <Typography variant="body2" sx={{ color: TEXT_SECONDARY, mt: 0.5 }}>
                        {(selectedArray.attrs as Record<string, unknown>)?.long_name as string || 'Variable'}
                      </Typography>
                    </Box>
                    <Box sx={{ textAlign: 'right' }}>
                      <Typography sx={{ color: ACCENT_COLOR, fontWeight: 600, ...monoStyle, fontSize: '1rem' }}>
                        {formatBytes(estimateSize(selectedArray.shape, selectedArray.dtype))}
                      </Typography>
                      <Typography variant="caption" sx={{ color: TEXT_MUTED, fontSize: '0.65rem' }}>
                        uncompressed
                      </Typography>
                    </Box>
                  </Box>
                  
                  {/* Quick metadata chips */}
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {selectedArray.shape && (
                      <Chip 
                        size="small" 
                        icon={<ViewModuleIcon sx={{ fontSize: 14 }} />}
                        label={`Shape: [${selectedArray.shape.join(' × ')}]`}
                        sx={{ height: 24, bgcolor: 'rgba(255,255,255,0.04)', color: TEXT_SECONDARY, ...monoFont, fontSize: '0.7rem' }}
                      />
                    )}
                    <Chip 
                      size="small" 
                      icon={<CodeIcon sx={{ fontSize: 14 }} />}
                      label={`dtype: ${selectedArray.dtype}`}
                      sx={{ height: 24, bgcolor: 'rgba(255,255,255,0.04)', color: TEXT_SECONDARY, ...monoFont, fontSize: '0.7rem' }}
                    />
                    {selectedArray.chunks && selectedArray.shape && (
                      <Chip 
                        size="small" 
                        icon={<MemoryIcon sx={{ fontSize: 14 }} />}
                        label={`${countChunks(selectedArray.shape, selectedArray.chunks).toLocaleString()} chunks`}
                        sx={{ height: 24, bgcolor: 'rgba(255,255,255,0.04)', color: TEXT_SECONDARY, ...monoFont, fontSize: '0.7rem' }}
                      />
                    )}
                    {typeof (selectedArray.attrs as Record<string, unknown>)?.units === 'string' && (
                      <Chip 
                        size="small" 
                        label={`Units: ${(selectedArray.attrs as Record<string, string>).units}`}
                        sx={{ height: 24, bgcolor: 'rgba(255,255,255,0.04)', color: TEXT_SECONDARY, fontSize: '0.7rem' }}
                      />
                    )}
                  </Box>
                </Box>

                {/* Tabs */}
                <Box sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  <Tabs 
                    value={tabValue} 
                    onChange={(_, v) => setTabValue(v)}
                    sx={{
                      minHeight: 38,
                      '& .MuiTabs-indicator': { bgcolor: ACCENT_COLOR, height: 2 },
                      '& .MuiTab-root': { 
                        minHeight: 38, 
                        py: 0, 
                        px: 2,
                        fontSize: '0.75rem',
                        textTransform: 'none',
                        color: TEXT_SECONDARY,
                        '&.Mui-selected': { color: ACCENT_COLOR },
                      },
                    }}
                  >
                    <Tab icon={<InfoIcon sx={{ fontSize: 16 }} />} iconPosition="start" label="Attributes" />
                    <Tab icon={<AssessmentIcon sx={{ fontSize: 16 }} />} iconPosition="start" label="Statistics" />
                    <Tab icon={<ViewModuleIcon sx={{ fontSize: 16 }} />} iconPosition="start" label="Dimensions" />
                    <Tab icon={<MemoryIcon sx={{ fontSize: 16 }} />} iconPosition="start" label="Chunks" />
                    {isDataVariable && (
                      <Tab icon={<FolderIcon sx={{ fontSize: 16 }} />} iconPosition="start" label="Files" />
                    )}
                  </Tabs>
                </Box>

                {/* Tab content */}
                <Box sx={{ flex: 1, overflow: 'auto', p: 2.5 }}>
                  <TabPanel value={tabValue} index={0}>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell sx={{ fontWeight: 600, width: '35%', color: TEXT_SECONDARY, borderColor: 'rgba(255,255,255,0.06)', ...monoStyle, fontSize: '0.72rem' }}>Key</TableCell>
                            <TableCell sx={{ fontWeight: 600, color: TEXT_SECONDARY, borderColor: 'rgba(255,255,255,0.06)', ...monoStyle, fontSize: '0.72rem' }}>Value</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {selectedArray.attrs && Object.entries(selectedArray.attrs).map(([key, value]) => (
                            <TableRow key={key} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                              <TableCell sx={{ ...monoStyle, color: ACCENT_COLOR, borderColor: 'rgba(255,255,255,0.04)' }}>{key}</TableCell>
                              <TableCell sx={{ ...monoStyle, color: TEXT_PRIMARY, borderColor: 'rgba(255,255,255,0.04)', wordBreak: 'break-all' }}>
                                {Array.isArray(value) ? `[${value.join(', ')}]` : String(value)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </TabPanel>

                  <TabPanel value={tabValue} index={1}>
                    {(selectedVariable === 'sst' || selectedVariable === selectedDataset) && datasetInfo?.global_stats && datasetInfo.global_stats.temporal_mean !== undefined ? (
                      <Box>
                        <Typography variant="caption" sx={{ color: TEXT_MUTED, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.62rem' }}>
                          Pre-computed Global Statistics
                        </Typography>
                        <TableContainer sx={{ mt: 1.5 }}>
                          <Table size="small">
                            <TableBody>
                              {[
                                { label: 'Temporal Mean', value: `${datasetInfo.global_stats.temporal_mean?.toFixed(4) ?? '—'} °C` },
                                { label: 'Temporal Std Dev', value: `${datasetInfo.global_stats.temporal_std?.toFixed(4) ?? '—'} °C` },
                                { label: 'Global Minimum', value: `${datasetInfo.global_stats.temporal_min?.toFixed(4) ?? '—'} °C` },
                                { label: 'Global Maximum', value: `${datasetInfo.global_stats.temporal_max?.toFixed(4) ?? '—'} °C` },
                                { label: 'Time Steps', value: datasetInfo.global_stats.n_timesteps?.toLocaleString() ?? '—' },
                                { label: 'Date Range', value: datasetInfo.global_stats.date_range?.join(' → ') || '—' },
                              ].map(({ label, value }) => (
                                <TableRow key={label} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                                  <TableCell sx={{ fontSize: '0.78rem', color: TEXT_SECONDARY, borderColor: 'rgba(255,255,255,0.04)', width: '40%' }}>{label}</TableCell>
                                  <TableCell sx={{ color: TEXT_PRIMARY, borderColor: 'rgba(255,255,255,0.04)', ...monoStyle, fontSize: '0.78rem' }}>{value}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </Box>
                    ) : (
                      <Box sx={{ py: 4, textAlign: 'center' }}>
                        <AssessmentIcon sx={{ fontSize: 40, color: 'rgba(255,255,255,0.08)', mb: 1 }} />
                        <Typography sx={{ color: TEXT_MUTED, fontSize: '0.85rem' }}>
                          Statistics available for main data variables only.
                        </Typography>
                      </Box>
                    )}
                  </TabPanel>

                  <TabPanel value={tabValue} index={2}>
                    <Typography variant="caption" sx={{ color: TEXT_MUTED, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.62rem' }}>
                      Array Dimensions
                    </Typography>
                    {selectedArray.shape ? (
                    <TableContainer sx={{ mt: 1.5 }}>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell sx={{ color: TEXT_MUTED, borderColor: 'rgba(255,255,255,0.06)', ...monoStyle, fontSize: '0.68rem', width: 60 }}>Axis</TableCell>
                            <TableCell sx={{ color: TEXT_MUTED, borderColor: 'rgba(255,255,255,0.06)', ...monoStyle, fontSize: '0.68rem' }}>Name</TableCell>
                            <TableCell sx={{ color: TEXT_MUTED, borderColor: 'rgba(255,255,255,0.06)', ...monoStyle, fontSize: '0.68rem', textAlign: 'right' }}>Size</TableCell>
                            <TableCell sx={{ color: TEXT_MUTED, borderColor: 'rgba(255,255,255,0.06)', ...monoStyle, fontSize: '0.68rem', textAlign: 'right' }}>Chunk</TableCell>
                            <TableCell sx={{ color: TEXT_MUTED, borderColor: 'rgba(255,255,255,0.06)', ...monoStyle, fontSize: '0.68rem', textAlign: 'right' }}>Blocks</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {selectedArray.shape.map((size, i) => {
                            const dims = (selectedArray.attrs as Record<string, unknown>)?._ARRAY_DIMENSIONS as string[] | undefined;
                            const dimName = dims?.[i] || `dim_${i}`;
                            const chunkSize = selectedArray.chunks?.[i] || size;
                            const numBlocks = Math.ceil(size / chunkSize);
                            return (
                              <TableRow key={i} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                                <TableCell sx={{ ...monoStyle, color: TEXT_MUTED, borderColor: 'rgba(255,255,255,0.04)' }}>{i}</TableCell>
                                <TableCell sx={{ ...monoStyle, color: ACCENT_COLOR, borderColor: 'rgba(255,255,255,0.04)' }}>{dimName}</TableCell>
                                <TableCell sx={{ ...monoStyle, color: TEXT_PRIMARY, borderColor: 'rgba(255,255,255,0.04)', textAlign: 'right' }}>{size.toLocaleString()}</TableCell>
                                <TableCell sx={{ ...monoStyle, color: TEXT_PRIMARY, borderColor: 'rgba(255,255,255,0.04)', textAlign: 'right' }}>{chunkSize.toLocaleString()}</TableCell>
                                <TableCell sx={{ ...monoStyle, color: TEXT_MUTED, borderColor: 'rgba(255,255,255,0.04)', textAlign: 'right' }}>{numBlocks.toLocaleString()}</TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </TableContainer>
                    ) : (
                      <Typography sx={{ color: TEXT_MUTED, fontSize: '0.8rem', mt: 2 }}>
                        Dimension info not available for COG datasets
                      </Typography>
                    )}
                  </TabPanel>

                  <TabPanel value={tabValue} index={3}>
                    <Typography variant="caption" sx={{ color: TEXT_MUTED, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.62rem' }}>
                      Chunk Configuration
                    </Typography>
                    {selectedArray.chunks && selectedArray.shape ? (
                      <Box sx={{ mt: 2 }}>
                        <Box sx={{ display: 'flex', gap: 3, mb: 3 }}>
                          <Box>
                            <Typography sx={{ color: TEXT_MUTED, fontSize: '0.7rem', mb: 0.5 }}>Chunk Shape</Typography>
                            <Typography sx={{ color: TEXT_PRIMARY, ...monoFont, fontSize: '1rem' }}>
                              [{selectedArray.chunks.join(' × ')}]
                            </Typography>
                          </Box>
                          <Box>
                            <Typography sx={{ color: TEXT_MUTED, fontSize: '0.7rem', mb: 0.5 }}>Total Chunks</Typography>
                            <Typography sx={{ color: ACCENT_COLOR, ...monoFont, fontSize: '1rem' }}>
                              {countChunks(selectedArray.shape, selectedArray.chunks).toLocaleString()}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography sx={{ color: TEXT_MUTED, fontSize: '0.7rem', mb: 0.5 }}>Chunk Size</Typography>
                            <Typography sx={{ color: TEXT_PRIMARY, ...monoFont, fontSize: '1rem' }}>
                              {formatBytes(estimateSize(selectedArray.chunks, selectedArray.dtype))}
                            </Typography>
                          </Box>
                        </Box>
                        
                        {/* Visual chunk grid representation */}
                        <Typography variant="caption" sx={{ color: TEXT_MUTED, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.62rem', display: 'block', mb: 1.5 }}>
                          Chunk Layout (per dimension)
                        </Typography>
                        {selectedArray.shape.map((size, i) => {
                          const dims = (selectedArray.attrs as Record<string, unknown>)?._ARRAY_DIMENSIONS as string[] | undefined;
                          const dimName = dims?.[i] || `dim_${i}`;
                          const chunkSize = selectedArray.chunks?.[i] || size;
                          const numBlocks = Math.ceil(size / chunkSize);
                          
                          return (
                            <Box key={i} sx={{ mb: 1.5 }}>
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                                <Typography sx={{ color: ACCENT_COLOR, ...monoFont, fontSize: '0.75rem' }}>{dimName}</Typography>
                                <Typography sx={{ color: TEXT_MUTED, ...monoFont, fontSize: '0.7rem' }}>
                                  {numBlocks} blocks × {chunkSize.toLocaleString()}
                                </Typography>
                              </Box>
                              <Box sx={{ 
                                height: 8, 
                                bgcolor: 'rgba(255,255,255,0.05)', 
                                borderRadius: 0,
                                overflow: 'hidden',
                                display: 'flex',
                                gap: '1px',
                              }}>
                                {Array.from({ length: Math.min(numBlocks, 50) }).map((_, blockIdx) => (
                                  <Box 
                                    key={blockIdx}
                                    sx={{ 
                                      flex: 1, 
                                      bgcolor: `rgba(255, 180, 50, ${0.3 + (blockIdx % 2) * 0.15})`,
                                    }} 
                                  />
                                ))}
                                {numBlocks > 50 && (
                                  <Box sx={{ flex: 1, bgcolor: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <Typography sx={{ fontSize: '0.5rem', color: TEXT_MUTED }}>+{numBlocks - 50}</Typography>
                                  </Box>
                                )}
                              </Box>
                            </Box>
                          );
                        })}
                      </Box>
                    ) : (
                      <Box sx={{ py: 4, textAlign: 'center' }}>
                        <MemoryIcon sx={{ fontSize: 40, color: 'rgba(255,255,255,0.08)', mb: 1 }} />
                        <Typography sx={{ color: TEXT_MUTED, fontSize: '0.85rem' }}>
                          This array is not chunked.
                        </Typography>
                      </Box>
                    )}
                  </TabPanel>

                  {isDataVariable && (
                    <TabPanel value={tabValue} index={4}>
                      <Typography variant="caption" sx={{ color: TEXT_MUTED, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.62rem' }}>
                        Zarr Store Files
                      </Typography>
                      {fileTreeLoading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                          <CircularProgress size={28} sx={{ color: ACCENT_COLOR }} />
                        </Box>
                      ) : fileTree ? (
                        <Box sx={{ mt: 2 }}>
                          <Box sx={{ display: 'flex', gap: 3, mb: 2 }}>
                            <Box>
                              <Typography sx={{ color: TEXT_MUTED, fontSize: '0.7rem', mb: 0.5 }}>Store Path</Typography>
                              <Typography sx={{ color: TEXT_PRIMARY, ...monoFont, fontSize: '0.85rem' }}>
                                {fileTree.root}
                              </Typography>
                            </Box>
                            <Box>
                              <Typography sx={{ color: TEXT_MUTED, fontSize: '0.7rem', mb: 0.5 }}>Total Size</Typography>
                              <Typography sx={{ color: ACCENT_COLOR, ...monoFont, fontSize: '0.85rem' }}>
                                {formatBytes(fileTree.total_size)}
                              </Typography>
                            </Box>
                          </Box>
                          <Box sx={{ 
                            mt: 2, 
                            maxHeight: 400, 
                            overflow: 'auto',
                            bgcolor: 'rgba(0,0,0,0.2)',
                            border: '1px solid rgba(255,255,255,0.06)',
                            p: 1,
                          }}>
                            <FileTreeView 
                              items={fileTree.tree} 
                              depth={0} 
                              expandedPaths={expandedPaths} 
                              onToggle={toggleFilePath} 
                            />
                          </Box>
                        </Box>
                      ) : (
                        <Box sx={{ py: 4, textAlign: 'center' }}>
                          <FolderIcon sx={{ fontSize: 40, color: 'rgba(255,255,255,0.08)', mb: 1 }} />
                          <Typography sx={{ color: TEXT_MUTED, fontSize: '0.85rem' }}>
                            No file information available.
                          </Typography>
                        </Box>
                      )}
                    </TabPanel>
                  )}
                </Box>
              </>
            ) : (
              <Box
                sx={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexDirection: 'column',
                  gap: 1.5,
                }}
              >
                <DatasetIcon sx={{ fontSize: 56, color: 'rgba(255,255,255,0.06)' }} />
                <Typography variant="body2" sx={{ color: TEXT_MUTED }}>
                  Select a variable
                </Typography>
              </Box>
            )}
          </Box>
        </Box>
      </Paper>
    </Box>
  );
};

export default AnalyticsPanel;
