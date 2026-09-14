import { Box, Typography, Select, MenuItem, FormControl } from '@mui/material';
import LayersIcon from '@mui/icons-material/Layers';
import { DatasetInfo } from '../../types/dataset';

interface DatasetVariableSelectorProps {
  dataset: DatasetInfo;
  selectedVariable: string;
  onSelectVariable: (variable: string) => void;
}

export function DatasetVariableSelector({
  dataset,
  selectedVariable,
  onSelectVariable,
}: DatasetVariableSelectorProps) {
  const variables = Object.values(dataset.variables);
  if (variables.length <= 1) return null;

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        bgcolor: 'rgba(8, 12, 18, 0.88)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(0, 229, 255, 0.25)',
        px: 2,
        py: 0.75,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }}
    >
      <LayersIcon sx={{ color: '#00e5ff', fontSize: 18 }} />
      <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.8)', letterSpacing: '0.04em' }}>
        VARIABLE:
      </Typography>

      <FormControl size="small" variant="standard">
        <Select
          value={selectedVariable || dataset.default_variable || variables[0]?.name}
          onChange={(e) => onSelectVariable(e.target.value)}
          disableUnderline
          sx={{
            color: '#00e5ff',
            fontWeight: 600,
            fontSize: '0.8rem',
            '& .MuiSelect-icon': { color: '#00e5ff' },
          }}
        >
          {variables.map((v) => (
            <MenuItem
              key={v.name}
              value={v.name}
              sx={{
                fontSize: '0.8rem',
                display: 'flex',
                justifyContent: 'space-between',
                gap: 2,
              }}
            >
              <span>{v.name}</span>
              {v.units && <span style={{ opacity: 0.5, fontSize: '0.7rem' }}>({v.units})</span>}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Box>
  );
}
