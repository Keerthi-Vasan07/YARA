/**
 * License Acknowledgement Dialog - Shown before data downloads
 * Ensures users acknowledge the Copernicus Marine Service license terms.
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Checkbox,
  FormControlLabel,
  Link,
  Box,
  Divider,
} from '@mui/material';
import {
  Gavel as GavelIcon,
  Download as DownloadIcon,
} from '@mui/icons-material';

const ACCENT_COLOR = '#FFB347';
const BG_DARK = 'rgba(8, 12, 18, 0.98)';
const BORDER_COLOR = 'rgba(255, 180, 50, 0.15)';

// Session storage key to remember acknowledgement
const LICENSE_ACKNOWLEDGED_KEY = 'cmems-license-acknowledged';

interface LicenseDialogProps {
  open: boolean;
  onAccept: () => void;
  onCancel: () => void;
  dataSource?: string; // e.g., "SST", "SIC", etc.
}

/**
 * Check if user has already acknowledged the license this session
 */
export function hasAcknowledgedLicense(): boolean {
  return sessionStorage.getItem(LICENSE_ACKNOWLEDGED_KEY) === 'true';
}

/**
 * Record that user has acknowledged the license
 */
export function setLicenseAcknowledged(): void {
  sessionStorage.setItem(LICENSE_ACKNOWLEDGED_KEY, 'true');
}

export function LicenseDialog({ open, onAccept, onCancel, dataSource = 'ECV' }: LicenseDialogProps) {
  const [checked, setChecked] = useState(false);

  // Reset checkbox when dialog opens
  useEffect(() => {
    if (open) {
      setChecked(false);
    }
  }, [open]);

  const handleAccept = () => {
    setLicenseAcknowledged();
    onAccept();
  };

  return (
    <Dialog
      open={open}
      onClose={onCancel}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: BG_DARK,
          border: `1px solid ${BORDER_COLOR}`,
          borderRadius: 0,
          backgroundImage: 'none',
        },
      }}
    >
      <DialogTitle
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          borderBottom: `1px solid ${BORDER_COLOR}`,
          pb: 2,
        }}
      >
        <GavelIcon sx={{ color: ACCENT_COLOR }} />
        <Typography variant="h6" sx={{ fontWeight: 500 }}>
          Data License Acknowledgement
        </Typography>
      </DialogTitle>

      <DialogContent sx={{ pt: 3 }}>
        <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.8)', mb: 2 }}>
          The {dataSource} data you are about to download is provided by the{' '}
          <strong>Copernicus Marine Service (CMEMS)</strong> and is subject to their license terms.
        </Typography>

        <Box
          sx={{
            p: 2,
            bgcolor: 'rgba(255, 179, 71, 0.08)',
            border: `1px solid ${BORDER_COLOR}`,
            borderRadius: 1,
            mb: 2,
          }}
        >
          <Typography variant="subtitle2" sx={{ color: ACCENT_COLOR, mb: 1 }}>
            Required Attribution
          </Typography>
          <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.7)', fontStyle: 'italic' }}>
            "This study has been conducted using E.U. Copernicus Marine Service Information."
          </Typography>
        </Box>

        <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.6)', mb: 2 }}>
          By downloading, you agree to:
        </Typography>

        <Box component="ul" sx={{ m: 0, pl: 2.5, mb: 2, '& li': { color: 'rgba(255,255,255,0.6)', mb: 0.5 } }}>
          <li>Include the required attribution in any publication or derived work</li>
          <li>Not redistribute the data in a manner that competes with CMEMS</li>
          <li>Accept that the data is provided "as is" without warranty</li>
        </Box>

        <Link
          href="https://marine.copernicus.eu/services-portfolio/service-commitments-and-licence"
          target="_blank"
          rel="noopener noreferrer"
          sx={{ color: ACCENT_COLOR, fontSize: '0.875rem' }}
        >
          View full Copernicus Marine Service License →
        </Link>

        <Divider sx={{ my: 2, borderColor: BORDER_COLOR }} />

        <FormControlLabel
          control={
            <Checkbox
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              sx={{
                color: 'rgba(255,255,255,0.4)',
                '&.Mui-checked': { color: ACCENT_COLOR },
              }}
            />
          }
          label={
            <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.8)' }}>
              I acknowledge the license terms and agree to provide proper attribution
            </Typography>
          }
        />
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2, borderTop: `1px solid ${BORDER_COLOR}` }}>
        <Button
          onClick={onCancel}
          sx={{ color: 'rgba(255,255,255,0.6)' }}
        >
          Cancel
        </Button>
        <Button
          onClick={handleAccept}
          disabled={!checked}
          variant="contained"
          startIcon={<DownloadIcon />}
          sx={{
            bgcolor: ACCENT_COLOR,
            color: '#0A0E14',
            fontWeight: 600,
            '&:hover': { bgcolor: '#FFA726' },
            '&:disabled': { bgcolor: 'rgba(255, 179, 71, 0.3)', color: 'rgba(255,255,255,0.3)' },
          }}
        >
          Accept & Download
        </Button>
      </DialogActions>
    </Dialog>
  );
}
