import {
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  ChevronLeft,
  ChevronRight,
  Public as GlobeIcon,
  Layers as LayersIcon,
  Timeline as TimelineIcon,
  Settings as SettingsIcon,
  Info as InfoIcon,
  DataObject as VariablesIcon,
} from '@mui/icons-material';

const SIDEBAR_WIDTH = 180;
const SIDEBAR_WIDTH_COLLAPSED = 48;

interface SidebarItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  onClick?: () => void;
}

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  onOpenLayers: () => void;
  onOpenAnalytics: () => void;
  onFlyHome?: () => void;
  onOpenSettings?: () => void;
  onOpenAbout?: () => void;
  onOpenBookmarks?: () => void;
}

export function Sidebar({
  collapsed,
  onToggle,
  onOpenLayers,
  onOpenAnalytics,
  onFlyHome,
  onOpenSettings,
  onOpenAbout,
}: SidebarProps) {
  const menuItems: SidebarItem[] = [
    { id: 'globe', label: 'Globe', icon: <GlobeIcon sx={{ fontSize: 22 }} />, onClick: onFlyHome },
    { id: 'layers', label: 'Layers', icon: <LayersIcon sx={{ fontSize: 22 }} />, onClick: onOpenLayers },
    { id: 'analytics', label: 'Variables', icon: <VariablesIcon sx={{ fontSize: 22 }} />, onClick: onOpenAnalytics },
    { id: 'timeline', label: 'Timeline', icon: <TimelineIcon sx={{ fontSize: 22 }} /> },
    { id: 'settings', label: 'Settings', icon: <SettingsIcon sx={{ fontSize: 22 }} />, onClick: onOpenSettings },
    { id: 'about', label: 'About', icon: <InfoIcon sx={{ fontSize: 22 }} />, onClick: onOpenAbout },
  ];

  const renderItem = (item: SidebarItem) => (
    <ListItem key={item.id} disablePadding sx={{ display: 'block' }}>
      <Tooltip title={collapsed ? item.label : ''} placement="right" arrow>
        <ListItemButton
          onClick={item.onClick}
          sx={{
            minHeight: 36,
            justifyContent: collapsed ? 'center' : 'initial',
            px: collapsed ? 1 : 1.5,
            mx: 0.5,
            borderRadius: 0,
            '&:hover': {
              bgcolor: 'rgba(255,255,255,0.06)',
            },
          }}
        >
          <ListItemIcon
            sx={{
              minWidth: 0,
              mr: collapsed ? 0 : 1.5,
              justifyContent: 'center',
              color: 'rgba(255,255,255,0.85)',
            }}
          >
            {item.icon}
          </ListItemIcon>
          {!collapsed && (
            <ListItemText
              primary={item.label}
              primaryTypographyProps={{
                fontSize: '0.75rem',
                fontWeight: 500,
              }}
            />
          )}
        </ListItemButton>
      </Tooltip>
    </ListItem>
  );

  return (
    <Box
      component="aside"
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Toggle button */}
      <Box
        sx={{
          display: 'flex',
          justifyContent: collapsed ? 'center' : 'flex-end',
          p: 0.5,
        }}
      >
        <IconButton 
          size="small" 
          onClick={onToggle}
          sx={{ 
            color: 'rgba(255,255,255,0.5)',
            '&:hover': { bgcolor: 'rgba(255,255,255,0.08)' },
          }}
        >
          {collapsed ? <ChevronRight sx={{ fontSize: 16 }} /> : <ChevronLeft sx={{ fontSize: 16 }} />}
        </IconButton>
      </Box>

      {/* Main menu */}
      <Box sx={{ flexGrow: 1, py: 0.5 }}>
        <List disablePadding>
          {menuItems.map(renderItem)}
        </List>
      </Box>

      {/* Version info */}
      {!collapsed && (
        <Box sx={{ px: 1.5, py: 1, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.3)', fontSize: '0.65rem' }}>
            v0.1.0
          </Typography>
        </Box>
      )}
    </Box>
  );
}

export { SIDEBAR_WIDTH, SIDEBAR_WIDTH_COLLAPSED };

