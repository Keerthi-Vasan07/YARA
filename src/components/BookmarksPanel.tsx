import { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  TextField,
  Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import BookmarkIcon from '@mui/icons-material/Bookmark';

export interface Bookmark {
  id: string;
  name: string;
  lat: number;
  lon: number;
  height: number;
  date: string;
  layers: string[];
  basemap: string;
}

interface BookmarksPanelProps {
  open: boolean;
  onClose: () => void;
  currentLat: number;
  currentLon: number;
  currentHeight: number;
  currentDate: string;
  currentLayers: string[];
  currentBasemap: string;
  onLoadBookmark: (bookmark: Bookmark) => void;
}

const STORAGE_KEY = 'yara-bookmarks';

export function BookmarksPanel({
  open,
  onClose,
  currentLat,
  currentLon,
  currentHeight,
  currentDate,
  currentLayers,
  currentBasemap,
  onLoadBookmark,
}: BookmarksPanelProps) {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [name, setName] = useState('');

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);

      if (saved) {
        setBookmarks(JSON.parse(saved));
      }
    } catch {
      setBookmarks([]);
    }
  }, []);

  const saveBookmarks = (items: Bookmark[]) => {
    setBookmarks(items);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  };

  const addBookmark = () => {
    const bookmark: Bookmark = {
      id: crypto.randomUUID(),
      name: name.trim() || `Bookmark ${bookmarks.length + 1}`,
      lat: currentLat,
      lon: currentLon,
      height: currentHeight,
      date: currentDate,
      layers: currentLayers,
      basemap: currentBasemap,
    };

    saveBookmarks([...bookmarks, bookmark]);
    setName('');
  };

  const deleteBookmark = (id: string) => {
    saveBookmarks(
      bookmarks.filter((bookmark) => bookmark.id !== id)
    );
  };

  const loadBookmark = (bookmark: Bookmark) => {
    onLoadBookmark(bookmark);
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
    >
      <DialogTitle>
        <Box display="flex" alignItems="center" gap={1}>
          <BookmarkIcon />
          Bookmarks
        </Box>
      </DialogTitle>

      <DialogContent>
        <Box
          display="flex"
          gap={1}
          sx={{ mt: 1, mb: 2 }}
        >
          <TextField
            fullWidth
            size="small"
            label="Bookmark name"
            value={name}
            onChange={(event) =>
              setName(event.target.value)
            }
          />

          <Button
            variant="contained"
            onClick={addBookmark}
          >
            Save
          </Button>
        </Box>

        {bookmarks.length === 0 ? (
          <Typography color="text.secondary">
            No bookmarks saved yet.
          </Typography>
        ) : (
          <Box>
            {bookmarks.map((bookmark) => (
              <Box
                key={bookmark.id}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  p: 1.5,
                  mb: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1,
                }}
              >
                <Box
                  sx={{ cursor: 'pointer', flex: 1 }}
                  onClick={() => loadBookmark(bookmark)}
                >
                  <Typography fontWeight={600}>
                    {bookmark.name}
                  </Typography>

                  <Typography
                    variant="body2"
                    color="text.secondary"
                  >
                    {bookmark.lat.toFixed(3)}°,{' '}
                    {bookmark.lon.toFixed(3)}°
                  </Typography>

                  <Typography
                    variant="caption"
                    color="text.secondary"
                  >
                    Date: {bookmark.date}
                  </Typography>

                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                  >
                    Basemap: {bookmark.basemap}
                  </Typography>
                </Box>

                <IconButton
                  aria-label={`Delete ${bookmark.name}`}
                  onClick={() =>
                    deleteBookmark(bookmark.id)
                  }
                >
                  <DeleteIcon />
                </IconButton>
              </Box>
            ))}
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
