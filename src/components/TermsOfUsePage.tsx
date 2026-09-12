/**
 * Terms of Use Page - Application terms, data licensing, and disclaimers
 */

import { useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Link,
  Divider,
} from '@mui/material';
import {
  Close as CloseIcon,
  Gavel as GavelIcon,
  Security as SecurityIcon,
  CloudDownload as DataIcon,
  Copyright as CopyrightIcon,
} from '@mui/icons-material';

// Color scheme - match Settings/About panels
const ACCENT_COLOR = '#FFB347';
const BORDER_COLOR = 'rgba(255, 180, 50, 0.12)';
const BG_DARK = '#0a0a0a';
const TEXT_PRIMARY = 'rgba(255, 255, 255, 0.92)';
const TEXT_SECONDARY = 'rgba(255, 255, 255, 0.55)';

interface TermsOfUsePageProps {
  open: boolean;
  onClose: () => void;
}

export function TermsOfUsePage({ open, onClose }: TermsOfUsePageProps) {
  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

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
          width: '90vw',
          maxWidth: 800,
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
            <GavelIcon sx={{ color: ACCENT_COLOR }} />
            <Typography
              variant="h6"
              sx={{
                color: TEXT_PRIMARY,
                fontWeight: 500,
                letterSpacing: '0.02em',
              }}
            >
              Terms of Use
            </Typography>
          </Box>
          <IconButton onClick={onClose} size="small" sx={{ color: TEXT_SECONDARY }}>
            <CloseIcon />
          </IconButton>
        </Box>

        {/* Content */}
        <Box sx={{ p: 4, overflow: 'auto', flexGrow: 1 }}>
          {/* Last Updated */}
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)', display: 'block', mb: 3, textAlign: 'center' }}>
            Last updated: 8 February 2026
          </Typography>

          {/* Introduction */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="body1" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8 }}>
              Welcome to OceanStream Physics & Biogeochem ("the Application"). By accessing or using this Application, 
              you agree to be bound by these Terms of Use. If you do not agree to these terms, please do not use the Application.
            </Typography>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Section 1: Service Description */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1, fontSize: '1rem' }}>
              <SecurityIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              1. Service Description
            </Typography>
            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8, mb: 1.5 }}>
              OceanStream provides interactive visualization of satellite-derived Essential Climate Variables (ECVs) 
              from the Copernicus Climate Change Service (C3S) and Copernicus Marine Service (CMEMS). 
              The Application allows users to:
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 2, color: TEXT_SECONDARY, '& li': { mb: 0.5 } }}>
              <li>Visualize ocean variables on a 3D globe</li>
              <li>Query point values and time series</li>
              <li>Download data subsets in various formats</li>
              <li>Export visualizations as images</li>
            </Box>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Section 2: Data Licensing */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1, fontSize: '1rem' }}>
              <DataIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              2. Data Sources & Licensing
            </Typography>
            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8, mb: 1.5 }}>
              The data displayed in this Application is sourced from:
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 2, color: TEXT_SECONDARY, '& li': { mb: 0.5 } }}>
              <li>
                <strong>Copernicus Marine Service (CMEMS)</strong> – Sea Surface Temperature (SST), Sea Ice Concentration (SIC), 
                Sea Level Anomaly (SLA), Chlorophyll-a (CHL), Kd490, Ocean Color (Rrs)
              </li>
              <li>
                <strong>ERA5 Reanalysis</strong> – Atmospheric and ocean reanalysis data via ECMWF Climate Data Store
              </li>
            </Box>
            
            <Box sx={{ mt: 2, p: 2, bgcolor: 'rgba(255, 179, 71, 0.1)', border: `1px solid ${BORDER_COLOR}`, borderRadius: 1 }}>
              <Typography variant="subtitle2" sx={{ color: ACCENT_COLOR, mb: 1 }}>
                Copernicus Marine Service License
              </Typography>
              <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8, mb: 1 }}>
                All Copernicus Marine data is provided under the{' '}
                <Link
                  href="https://marine.copernicus.eu/services-portfolio/service-commitments-and-licence"
                  target="_blank"
                  rel="noopener noreferrer"
                  sx={{ color: ACCENT_COLOR }}
                >
                  Copernicus Marine Service License
                </Link>
                . This license permits free access and redistribution with attribution.
              </Typography>
              <Typography variant="body2" sx={{ color: TEXT_SECONDARY, fontStyle: 'italic' }}>
                Required citation: "This study/application has been conducted using E.U. Copernicus Marine Service Information."
              </Typography>
            </Box>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Section 3: User Obligations */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1, fontSize: '1rem' }}>
              <GavelIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              3. User Obligations
            </Typography>
            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8, mb: 1.5 }}>
              By using this Application, you agree to:
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 2, color: TEXT_SECONDARY, '& li': { mb: 0.5, lineHeight: 1.7 } }}>
              <li>Acknowledge the data source when using downloaded data or screenshots in publications, presentations, or derived works</li>
              <li>Not redistribute the data in a manner that competes with the original data providers</li>
              <li>Use the Application for lawful purposes only</li>
              <li>Not attempt to circumvent any access controls or security measures</li>
            </Box>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Section 4: Disclaimer */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1, fontSize: '1rem' }}>
              <SecurityIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              4. Disclaimer of Warranties
            </Typography>
            <Box sx={{ p: 2, bgcolor: 'rgba(255, 255, 255, 0.04)', borderRadius: 1 }}>
              <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8 }}>
                THE APPLICATION AND DATA ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, 
                INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, 
                ACCURACY, OR NON-INFRINGEMENT.
              </Typography>
              <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8, mt: 1.5 }}>
                The data providers and application developers do not guarantee the accuracy, completeness, 
                or timeliness of any data or service. Users assume all responsibility for the use of any 
                data or information obtained through this Application.
              </Typography>
            </Box>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Section 5: Limitation of Liability */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, fontSize: '1rem' }}>
              5. Limitation of Liability
            </Typography>
            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8 }}>
              In no event shall Pine View Software AS, the data providers, or their affiliates be liable for any 
              direct, indirect, incidental, special, consequential, or punitive damages arising from the use of 
              or inability to use this Application or the data it provides.
            </Typography>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Section 6: Changes to Terms */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, fontSize: '1rem' }}>
              6. Changes to Terms
            </Typography>
            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8 }}>
              We reserve the right to modify these Terms of Use at any time. Changes will be posted on this page 
              with an updated revision date. Continued use of the Application after any changes constitutes 
              acceptance of the new terms.
            </Typography>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Section 7: Contact */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h6" sx={{ color: TEXT_PRIMARY, mb: 2, display: 'flex', alignItems: 'center', gap: 1, fontSize: '1rem' }}>
              <CopyrightIcon sx={{ color: ACCENT_COLOR, fontSize: 20 }} />
              7. Contact & Governing Law
            </Typography>
            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8, mb: 1.5 }}>
              For questions about these Terms of Use, please contact us at{' '}
              <Link href="https://oceanstream.io/contact/" target="_blank" rel="noopener" sx={{ color: ACCENT_COLOR }}>
                oceanstream.io/contact
              </Link>
            </Typography>
            <Typography variant="body2" sx={{ color: TEXT_SECONDARY, lineHeight: 1.8 }}>
              These Terms of Use shall be governed by and construed in accordance with the laws of Norway, 
              without regard to its conflict of law provisions.
            </Typography>
          </Box>

          <Divider sx={{ borderColor: BORDER_COLOR, my: 3 }} />

          {/* Footer */}
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.35)' }}>
              © 2026 Pine View Software AS. All Rights Reserved.
            </Typography>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
