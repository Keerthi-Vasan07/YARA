/**
 * Data Provenance Page - Comprehensive documentation of data sources and processing
 * for audit and advanced user reference.
 */

import { useEffect, useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Link,
  Divider,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
} from '@mui/material';
import {
  Close as CloseIcon,
  ExpandMore as ExpandMoreIcon,
  Storage as StorageIcon,
  Transform as TransformIcon,
  Verified as VerifiedIcon,
  CloudDownload as DownloadIcon,
  Code as CodeIcon,
  Science as ScienceIcon,
} from '@mui/icons-material';

// Color scheme - match Settings/About panels
const ACCENT_COLOR = '#FFB347';
const BORDER_COLOR = 'rgba(255, 180, 50, 0.12)';
const BG_DARK = '#0a0a0a';
const TEXT_PRIMARY = 'rgba(255, 255, 255, 0.92)';
const TEXT_SECONDARY = 'rgba(255, 255, 255, 0.55)';
const CODE_BG = 'rgba(255, 255, 255, 0.05)';

interface DataProvenancePageProps {
  open: boolean;
  onClose: () => void;
}

// Define all variable data sources
const VARIABLE_SOURCES = [
  {
    id: 'sst',
    name: 'Sea Surface Temperature',
    abbrev: 'SST',
    unit: '°C',
    resolution: '0.05° (~6 km)',
    temporalRes: 'Daily',
    coverage: 'Global (-80° to 80° latitude)',
    source: 'CMEMS OSTIA L4',
    productId: 'SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001',
    datasetId: 'METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2',
    provider: 'UK Met Office',
    sensors: 'Multi-sensor: SLSTR, VIIRS, AVHRR, AMSR2, in-situ',
    processing: 'L4 gap-filled optimal interpolation analysis',
    algorithm: 'OSTIA (Operational Sea Surface Temperature and Ice Analysis)',
    reference: 'https://doi.org/10.48670/moi-00165',
    license: 'Copernicus Marine Service License',
    qcNotes: 'Land and sea ice masked. Kelvin to Celsius conversion applied.',
    encoding: 'int16 with scale=0.01 (0.01°C precision)',
  },
  {
    id: 'sic',
    name: 'Sea Ice Concentration',
    abbrev: 'SIC',
    unit: '%',
    resolution: '10 km (0.1° in COG)',
    temporalRes: 'Daily',
    coverage: 'Arctic (30°N–90°N) + Antarctic (90°S–30°S)',
    source: 'CMEMS OSI SAF',
    productId: 'SEAICE_GLO_SEAICE_L4_NRT_OBSERVATIONS_011_001',
    datasetId: 'Arctic: osisaf_obs-si_glo_phy-sic-north_nrt_amsr2_l4_P1D-m\nAntarctic: osisaf_obs-si_glo_phy-sic-south_nrt_amsr2_l4_P1D-m',
    provider: 'EUMETSAT OSI SAF',
    sensors: 'AMSR2 (passive microwave)',
    processing: 'L4 analysis combining multiple passes',
    algorithm: 'NASA Team 2 / Bootstrap hybrid',
    reference: 'https://doi.org/10.48670/moi-00132',
    license: 'Copernicus Marine Service License',
    qcNotes: 'Arctic and Antarctic merged to global grid. Values ≤15% rendered as transparent (open water).',
    encoding: 'uint8 (0–100%), nodata=255',
  },
  {
    id: 'sla',
    name: 'Sea Level Anomaly',
    abbrev: 'SLA',
    unit: 'm',
    resolution: '0.25° (~28 km)',
    temporalRes: 'Daily',
    coverage: 'Global',
    source: 'CMEMS DUACS L4',
    productId: 'SEALEVEL_GLO_PHY_L4_NRT_008_046',
    datasetId: 'cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.25deg_P1D',
    provider: 'CLS/CNES',
    sensors: 'Multi-altimeter: Sentinel-6, Jason-3, Sentinel-3A/B, CryoSat-2, SARAL',
    processing: 'L4 multi-altimeter gridded maps',
    algorithm: 'DUACS (Data Unification and Altimeter Combination System)',
    reference: 'https://doi.org/10.48670/moi-00148',
    license: 'Copernicus Marine Service License',
    qcNotes: 'SLA is anomaly from 1993–2012 mean sea surface. Typical range: ±0.5m.',
    encoding: 'int16 with scale=0.001 (1 mm precision)',
  },
  {
    id: 'chl',
    name: 'Chlorophyll-a Concentration',
    abbrev: 'CHL',
    unit: 'mg/m³',
    resolution: '4 km (~0.04°)',
    temporalRes: 'Daily',
    coverage: 'Global ocean',
    source: 'CMEMS Ocean Colour L4',
    productId: 'OCEANCOLOUR_GLO_BGC_L4_NRT_009_102',
    datasetId: 'cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D',
    provider: 'ACRI-ST',
    sensors: 'Multi-sensor: MODIS-Aqua, VIIRS, OLCI',
    processing: 'L4 gap-free interpolated analysis',
    algorithm: 'OC-CCI blended algorithm',
    reference: 'https://doi.org/10.48670/moi-00281',
    license: 'Copernicus Marine Service License',
    qcNotes: 'Log-scale visualization recommended. Range: 0.01–100 mg/m³. NaN for land/cloud.',
    encoding: 'float32, nodata=NaN',
  },
  {
    id: 'kd490',
    name: 'Diffuse Attenuation Coefficient',
    abbrev: 'Kd490',
    unit: 'm⁻¹',
    resolution: '4 km (~0.04°)',
    temporalRes: 'Daily',
    coverage: 'Global ocean',
    source: 'CMEMS Ocean Colour L4',
    productId: 'OCEANCOLOUR_GLO_BGC_L4_NRT_009_102',
    datasetId: 'cmems_obs-oc_glo_bgc-transp_nrt_l4-gapfree-multi-4km_P1D',
    provider: 'ACRI-ST',
    sensors: 'Multi-sensor: MODIS-Aqua, VIIRS, OLCI',
    processing: 'L4 gap-free interpolated analysis',
    algorithm: 'Derived from remote sensing reflectance at 490nm',
    reference: 'https://doi.org/10.48670/moi-00281',
    license: 'Copernicus Marine Service License',
    qcNotes: 'Measures light attenuation with depth. 0.01 = clear open ocean, 5+ = turbid coastal.',
    encoding: 'float32, nodata=NaN',
  },
  {
    id: 'rrs',
    name: 'Ocean Colour RGB',
    abbrev: 'Rrs RGB',
    unit: 'sr⁻¹ (pre-scaled)',
    resolution: '4 km (~0.04°)',
    temporalRes: 'Daily',
    coverage: 'Global ocean (with gaps)',
    source: 'CMEMS Ocean Colour L3',
    productId: 'OCEANCOLOUR_GLO_BGC_L3_NRT_009_101',
    datasetId: 'cmems_obs-oc_glo_bgc-reflectance_nrt_l3-multi-4km_P1D',
    provider: 'ACRI-ST',
    sensors: 'Multi-sensor: MODIS-Aqua, VIIRS, OLCI',
    processing: 'L3 multi-sensor merge (not gap-filled)',
    algorithm: 'RGB composite: R=670nm, G=555nm, B=443nm with gamma correction',
    reference: 'https://doi.org/10.48670/moi-00280',
    license: 'Copernicus Marine Service License',
    qcNotes: 'True-color-like visualization. Phytoplankton blooms appear green/brown. Has cloud gaps.',
    encoding: 'uint8 RGBA, alpha=0 for nodata',
  },
];

const PROCESSING_STEPS = [
  {
    step: 1,
    title: 'Data Acquisition',
    icon: <DownloadIcon sx={{ color: ACCENT_COLOR }} />,
    description: 'Download from Copernicus Marine Service using copernicusmarine CLI',
    details: [
      'Authenticate via ~/.copernicusmarine credentials',
      'Subset by date, bounding box, and variables',
      'Download as NetCDF4 with CF conventions',
      'Automatic fallback from NRT to REP stream if NRT unavailable',
    ],
  },
  {
    step: 2,
    title: 'Format Conversion',
    icon: <TransformIcon sx={{ color: ACCENT_COLOR }} />,
    description: 'Convert NetCDF to Cloud-Optimized GeoTIFF (COG)',
    details: [
      'Reproject to EPSG:4326 (WGS84 Geographic)',
      'Apply scale factors (e.g., Kelvin→Celsius for SST)',
      'Set appropriate nodata values per variable',
      'Tiled internal structure: 512×512 blocks',
      'DEFLATE compression with predictor=2',
    ],
  },
  {
    step: 3,
    title: 'Overview Generation',
    icon: <StorageIcon sx={{ color: ACCENT_COLOR }} />,
    description: 'Build image pyramids for efficient multi-scale access',
    details: [
      'Generate overviews at 2×, 4×, 8×, 16×, 32× decimation',
      'Average resampling for continuous variables',
      'Stored within the same COG file',
      'Enables fast zoom-level tile serving',
    ],
  },
  {
    step: 4,
    title: 'Tile Rendering',
    icon: <CodeIcon sx={{ color: ACCENT_COLOR }} />,
    description: 'Server-side colormap application and tile serving',
    details: [
      'XYZ tile scheme (Web Mercator compatible addressing)',
      'Colormap applied at request time (cmocean.thermal, etc.)',
      'Optional contour lines at zoom ≥6 with labels at zoom ≥7',
      'Transparent pixels for nodata → basemap shows through',
      'PNG output with 24-hour cache headers',
    ],
  },
];

export function DataProvenancePage({ open, onClose }: DataProvenancePageProps) {
  const [expanded, setExpanded] = useState<string | false>(false);

  // Escape key handler
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const handleAccordionChange = (panel: string) => (_: React.SyntheticEvent, isExpanded: boolean) => {
    setExpanded(isExpanded ? panel : false);
  };

  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        zIndex: 1200,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        pt: 4,
        pb: 4,
        overflow: 'auto',
      }}
    >
      {/* Backdrop */}
      <Box
        onClick={onClose}
        sx={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.85)',
        }}
      />

      {/* Main Panel */}
      <Paper
        elevation={0}
        sx={{
          position: 'relative',
          width: '95vw',
          maxWidth: 1000,
          maxHeight: '92vh',
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
            px: 3,
            py: 2,
            borderBottom: `1px solid ${BORDER_COLOR}`,
            flexShrink: 0,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <ScienceIcon sx={{ color: ACCENT_COLOR }} />
            <Typography
              variant="h6"
              sx={{
                color: TEXT_PRIMARY,
                fontWeight: 500,
                letterSpacing: '0.02em',
              }}
            >
              Data Provenance & Processing
            </Typography>
          </Box>
          <IconButton onClick={onClose} size="small" sx={{ color: TEXT_SECONDARY }}>
            <CloseIcon />
          </IconButton>
        </Box>

        {/* Content */}
        <Box sx={{ p: 4, overflow: 'auto', flexGrow: 1 }}>
          {/* Introduction */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="body1" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8, mb: 2 }}>
              This document provides comprehensive traceability for all data displayed in OceanStream Physics & Biogeochem.
              All Essential Climate Variables (ECVs) are sourced from authoritative providers through the
              Copernicus Marine Service (CMEMS) and processed using reproducible, versioned pipelines.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Chip
                icon={<VerifiedIcon />}
                label="CF-1.8 Compliant"
                size="small"
                sx={{ bgcolor: 'rgba(110, 242, 252, 0.1)', color: '#6EF2FC' }}
              />
              <Chip
                label="FAIR Principles"
                size="small"
                sx={{ bgcolor: 'rgba(110, 242, 252, 0.1)', color: '#6EF2FC' }}
              />
              <Chip
                label="Cloud-Optimized GeoTIFF"
                size="small"
                sx={{ bgcolor: 'rgba(110, 242, 252, 0.1)', color: '#6EF2FC' }}
              />
            </Box>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Data Sources Section */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              <StorageIcon sx={{ color: ACCENT_COLOR }} />
              Data Sources
            </Typography>

            {VARIABLE_SOURCES.map((v) => (
              <Accordion
                key={v.id}
                expanded={expanded === v.id}
                onChange={handleAccordionChange(v.id)}
                sx={{
                  bgcolor: 'transparent',
                  border: `1px solid ${BORDER_COLOR}`,
                  mb: 1,
                  '&:before': { display: 'none' },
                  '&.Mui-expanded': { mb: 1 },
                }}
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreIcon sx={{ color: TEXT_SECONDARY }} />}
                  sx={{
                    '& .MuiAccordionSummary-content': {
                      alignItems: 'center',
                      gap: 2,
                    },
                  }}
                >
                  <Typography sx={{ color: ACCENT_COLOR, fontWeight: 600, minWidth: 70 }}>
                    {v.abbrev}
                  </Typography>
                  <Typography sx={{ color: TEXT_PRIMARY, flexGrow: 1 }}>
                    {v.name}
                  </Typography>
                  <Chip label={v.resolution} size="small" sx={{ color: TEXT_SECONDARY, fontSize: '0.7rem' }} />
                </AccordionSummary>
                <AccordionDetails sx={{ pt: 0 }}>
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', width: 160, pl: 0 }}>Unit</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.unit}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Resolution</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.resolution} / {v.temporalRes}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Coverage</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.coverage}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Source</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.source}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Provider</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.provider}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Sensors</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.sensors}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Processing Level</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.processing}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Algorithm</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.algorithm}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Product ID</TableCell>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                            {v.productId}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Dataset ID</TableCell>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', fontFamily: 'monospace', fontSize: '0.75rem', whiteSpace: 'pre-wrap' }}>
                            {v.datasetId}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>QC / Masking</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.qcNotes}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>COG Encoding</TableCell>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                            {v.encoding}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>License</TableCell>
                          <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>{v.license}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ color: TEXT_SECONDARY, border: 'none', pl: 0 }}>Reference</TableCell>
                          <TableCell sx={{ border: 'none' }}>
                            <Link
                              href={v.reference}
                              target="_blank"
                              rel="noopener noreferrer"
                              sx={{ color: ACCENT_COLOR, fontSize: '0.75rem' }}
                            >
                              {v.reference}
                            </Link>
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Processing Pipeline Section */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              <TransformIcon sx={{ color: ACCENT_COLOR }} />
              Processing Pipeline
            </Typography>

            {PROCESSING_STEPS.map((step, idx) => (
              <Box
                key={step.step}
                sx={{
                  display: 'flex',
                  gap: 2,
                  mb: 2,
                  pl: 1,
                  borderLeft: `2px solid ${idx === PROCESSING_STEPS.length - 1 ? 'transparent' : BORDER_COLOR}`,
                }}
              >
                <Box
                  sx={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    bgcolor: 'rgba(255, 179, 71, 0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    ml: -2.1,
                  }}
                >
                  {step.icon}
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" sx={{ color: TEXT_PRIMARY, mb: 0.5 }}>
                    Step {step.step}: {step.title}
                  </Typography>
                  <Typography variant="body2" sx={{ color: TEXT_SECONDARY, mb: 1 }}>
                    {step.description}
                  </Typography>
                  <Box
                    component="ul"
                    sx={{
                      m: 0,
                      pl: 2,
                      '& li': {
                        color: TEXT_SECONDARY,
                        fontSize: '0.8rem',
                        mb: 0.25,
                      },
                    }}
                  >
                    {step.details.map((detail, i) => (
                      <li key={i}>{detail}</li>
                    ))}
                  </Box>
                </Box>
              </Box>
            ))}
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Technical Specifications */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              <CodeIcon sx={{ color: ACCENT_COLOR }} />
              Technical Specifications
            </Typography>

            <Box sx={{ bgcolor: CODE_BG, p: 2, borderRadius: 1, mb: 2 }}>
              <Typography variant="subtitle2" sx={{ color: ACCENT_COLOR, mb: 1 }}>
                COG Profile
              </Typography>
              <Box component="pre" sx={{ color: TEXT_SECONDARY, fontSize: '0.75rem', m: 0, whiteSpace: 'pre-wrap' }}>
{`Driver: GTiff (Cloud-Optimized)
Tiling: 512×512 internal blocks
Compression: DEFLATE with predictor=2
Overviews: [2, 4, 8, 16, 32] with average resampling
CRS: EPSG:4326 (WGS84 Geographic)
Interleave: Band`}
              </Box>
            </Box>

            <Box sx={{ bgcolor: CODE_BG, p: 2, borderRadius: 1, mb: 2 }}>
              <Typography variant="subtitle2" sx={{ color: ACCENT_COLOR, mb: 1 }}>
                Tile Serving
              </Typography>
              <Box component="pre" sx={{ color: TEXT_SECONDARY, fontSize: '0.75rem', m: 0, whiteSpace: 'pre-wrap' }}>
{`Scheme: XYZ (Web Mercator tile addressing)
Tile Size: 256×256 pixels
Format: PNG with alpha transparency
Cache Headers: public, max-age=86400 (24 hours)
Colormaps: cmocean (thermal, algae, ice, balance, deep)
Contours: Marching squares at zoom ≥6, labels at zoom ≥7`}
              </Box>
            </Box>

            <Box sx={{ bgcolor: CODE_BG, p: 2, borderRadius: 1 }}>
              <Typography variant="subtitle2" sx={{ color: ACCENT_COLOR, mb: 1 }}>
                Pipeline Framework
              </Typography>
              <Box component="pre" sx={{ color: TEXT_SECONDARY, fontSize: '0.75rem', m: 0, whiteSpace: 'pre-wrap' }}>
{`Orchestration: Prefect 3 (Python)
Download: copernicusmarine CLI
Conversion: rasterio, xarray, numpy
Tile Rendering: rasterio, PIL, scikit-image
Web Framework: FastAPI + uvicorn
Frontend: React, CesiumJS, Vite`}
              </Box>
            </Box>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Data Access & Licensing */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              <VerifiedIcon sx={{ color: ACCENT_COLOR }} />
              Data Access & Licensing
            </Typography>

            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, mb: 2, lineHeight: 1.8 }}>
              All source data is obtained from the Copernicus Marine Service (CMEMS) under the
              <Link
                href="https://marine.copernicus.eu/services-portfolio/service-commitments-and-licence"
                target="_blank"
                rel="noopener noreferrer"
                sx={{ color: ACCENT_COLOR, mx: 0.5 }}
              >
                Copernicus Marine Service License
              </Link>
              which permits free access and redistribution with attribution. Original data providers retain
              intellectual property rights.
            </Typography>

            <Typography variant="subtitle2" sx={{ color: TEXT_PRIMARY, mt: 2, mb: 1 }}>
              Required Citation
            </Typography>
            <Box sx={{ bgcolor: CODE_BG, p: 2, borderRadius: 1 }}>
              <Typography variant="body2" sx={{ color: TEXT_SECONDARY, fontStyle: 'italic', fontSize: '0.8rem' }}>
                "This study has been conducted using E.U. Copernicus Marine Service Information."
              </Typography>
            </Box>

            <Typography variant="subtitle2" sx={{ color: TEXT_PRIMARY, mt: 2, mb: 1 }}>
              Data Provider DOIs
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              <Link href="https://doi.org/10.48670/moi-00165" target="_blank" rel="noopener" sx={{ color: ACCENT_COLOR, fontSize: '0.8rem' }}>
                SST: doi.org/10.48670/moi-00165
              </Link>
              <Link href="https://doi.org/10.48670/moi-00132" target="_blank" rel="noopener" sx={{ color: ACCENT_COLOR, fontSize: '0.8rem' }}>
                SIC: doi.org/10.48670/moi-00132
              </Link>
              <Link href="https://doi.org/10.48670/moi-00148" target="_blank" rel="noopener" sx={{ color: ACCENT_COLOR, fontSize: '0.8rem' }}>
                SLA: doi.org/10.48670/moi-00148
              </Link>
              <Link href="https://doi.org/10.48670/moi-00281" target="_blank" rel="noopener" sx={{ color: ACCENT_COLOR, fontSize: '0.8rem' }}>
                CHL/Kd490: doi.org/10.48670/moi-00281
              </Link>
              <Link href="https://doi.org/10.48670/moi-00280" target="_blank" rel="noopener" sx={{ color: ACCENT_COLOR, fontSize: '0.8rem' }}>
                Rrs: doi.org/10.48670/moi-00280
              </Link>
            </Box>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Update Frequency */}
          <Box sx={{ mb: 2 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              <DownloadIcon sx={{ color: ACCENT_COLOR }} />
              Update Frequency
            </Typography>

            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ color: TEXT_SECONDARY, borderBottom: `1px solid ${BORDER_COLOR}` }}>Variable</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, borderBottom: `1px solid ${BORDER_COLOR}` }}>NRT Latency</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, borderBottom: `1px solid ${BORDER_COLOR}` }}>Reprocessing</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>SST</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>~24 hours</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>Annual (REP stream)</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>SIC</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>~24 hours</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>Annual</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>SLA</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>~5 days</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>Quarterly</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>CHL/Kd490</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>~24 hours</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>Annual</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ color: TEXT_PRIMARY, border: 'none' }}>Rrs RGB</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>~24 hours</TableCell>
                    <TableCell sx={{ color: TEXT_SECONDARY, border: 'none' }}>Annual</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Box>

          {/* Footer */}
          <Box sx={{ textAlign: 'center', mt: 4 }}>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)' }}>
              Document generated from OceanStream source code. Last updated: February 2026.
            </Typography>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
