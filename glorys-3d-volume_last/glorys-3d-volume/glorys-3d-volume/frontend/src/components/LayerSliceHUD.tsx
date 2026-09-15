import React, { useState, useMemo } from 'react';
import { NumericLayerData, exportLayersToExcel } from '../utils/layerSegmentation';

export interface LayerSliceHUDProps {
  layers: NumericLayerData[];
  selectedLayerNumber: number;
  onSelectLayer: (layerNum: number) => void;
  datasetName?: string;
  dateStr?: string;
}

export const LayerSliceHUD: React.FC<LayerSliceHUDProps> = ({
  layers,
  selectedLayerNumber,
  onSelectLayer,
  datasetName = 'GLORYS12V1',
  dateStr = '2026-06-23',
}) => {
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportMode, setExportMode] = useState<'all' | 'current' | 'range'>('all');
  const [rangeFrom, setRangeFrom] = useState<number>(1);
  const [rangeTo, setRangeTo] = useState<number>(layers.length || 1);

  const activeLayer = useMemo(() => {
    return layers.find((l) => l.layerNumber === selectedLayerNumber) || layers[0];
  }, [layers, selectedLayerNumber]);

  const handleDownloadExcel = () => {
    let toExport: NumericLayerData[] = [];

    if (exportMode === 'all') {
      toExport = layers;
    } else if (exportMode === 'current') {
      toExport = activeLayer ? [activeLayer] : [];
    } else if (exportMode === 'range') {
      const from = Math.max(1, Math.min(rangeFrom, layers.length));
      const to = Math.max(from, Math.min(rangeTo, layers.length));
      toExport = layers.filter((l) => l.layerNumber >= from && l.layerNumber <= to);
    }

    if (toExport.length > 0) {
      exportLayersToExcel(toExport, `Ocean_Layer_Report_${datasetName}_${dateStr}`);
    }
    setShowExportModal(false);
  };

  if (!activeLayer) return null;

  return (
    <>
      {/* FLOATING TOP-RIGHT NUMERIC LAYER HUD */}
      <div
        className="absolute top-16 right-[330px] z-30 pointer-events-auto bg-slate-950/95 backdrop-blur-md border border-fuchsia-500/50 rounded-xl p-3 shadow-2xl w-[300px] text-white transition-all duration-150"
        style={{
          position: 'absolute',
          top: 64,
          right: 330,
          zIndex: 30,
          pointerEvents: 'auto',
          background: 'rgba(2, 6, 23, 0.95)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(217, 70, 239, 0.5)',
          borderRadius: 12,
          padding: 12,
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8), 0 0 15px rgba(217, 70, 239, 0.15)',
          width: 300,
          color: '#ffffff',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          boxSizing: 'border-box',
          transition: 'all 150ms ease-in-out',
        }}
      >
        {/* Header with Numerical Dropdown */}
        <div
          className="flex items-center justify-between border-b border-slate-800 pb-2 mb-1"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid rgba(30, 41, 59, 0.8)',
            paddingBottom: 8,
            marginBottom: 4,
          }}
        >
          <div className="flex items-center gap-1.5" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              className="w-2 h-2 rounded-full bg-fuchsia-400 animate-pulse"
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: '#e879f9',
                display: 'inline-block',
              }}
            />
            <span
              className="text-xs font-bold text-fuchsia-300 font-mono tracking-wider uppercase"
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: '#f0abfc',
                fontFamily: 'IBM Plex Mono, monospace',
                letterSpacing: '0.05em',
              }}
            >
              LAYER SELECT
            </span>
          </div>

          <select
            value={activeLayer.layerNumber}
            onChange={(e) => onSelectLayer(Number(e.target.value))}
            className="bg-slate-900 border border-fuchsia-500/50 text-fuchsia-200 text-xs rounded-md px-2 py-1 outline-none font-mono cursor-pointer focus:border-fuchsia-300"
            style={{
              background: '#0f172a',
              border: '1px solid rgba(217, 70, 239, 0.5)',
              color: '#f5d0fe',
              fontSize: 11,
              borderRadius: 6,
              padding: '4px 8px',
              fontFamily: 'IBM Plex Mono, monospace',
              cursor: 'pointer',
            }}
          >
            {layers.map((l) => (
              <option key={l.layerNumber} value={l.layerNumber} style={{ background: '#020617', color: '#f8fafc' }}>
                Layer {l.layerNumber} ({l.depthMin}m–{l.depthMax}m)
              </option>
            ))}
          </select>
        </div>

        {/* Coordinates & Layer Depth Information */}
        <div
          className="grid grid-cols-2 gap-2 text-[11px] font-mono bg-slate-900/80 p-2 rounded-lg mb-1 border border-slate-800"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: 8,
            fontSize: 11,
            fontFamily: 'IBM Plex Mono, monospace',
            background: 'rgba(15, 23, 42, 0.8)',
            padding: 8,
            borderRadius: 8,
            border: '1px solid rgba(30, 41, 59, 0.8)',
          }}
        >
          <div>
            <span className="text-[9px] text-slate-500 block uppercase" style={{ fontSize: 9, color: '#64748b', display: 'block' }}>
              Layer Depth
            </span>
            <strong className="text-fuchsia-300" style={{ color: '#f0abfc' }}>
              {activeLayer.depthMin}m – {activeLayer.depthMax}m
            </strong>
            <span className="text-[9px] text-slate-400 block font-sans" style={{ fontSize: 9, color: '#94a3b8', display: 'block', marginTop: 2 }}>
              Layer #{activeLayer.layerNumber} of {layers.length}
            </span>
          </div>
          <div>
            <span className="text-[9px] text-slate-500 block uppercase" style={{ fontSize: 9, color: '#64748b', display: 'block' }}>
              Geo Coordinates
            </span>
            <span className="text-slate-300 block" style={{ color: '#cbd5e1', display: 'block' }}>
              LAT: {activeLayer.latMin.toFixed(1)}°–{activeLayer.latMax.toFixed(1)}°N
            </span>
            <span className="text-slate-300 block" style={{ color: '#cbd5e1', display: 'block' }}>
              LON: {activeLayer.lonMin.toFixed(1)}°–{activeLayer.lonMax.toFixed(1)}°E
            </span>
          </div>
        </div>

        {/* Dataset Telemetry Data */}
        <div
          className="grid grid-cols-3 gap-2 mb-1"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 8,
          }}
        >
          <div
            className="bg-slate-900/90 border border-red-500/30 rounded-lg p-1.5 text-center"
            style={{
              background: 'rgba(15, 23, 42, 0.9)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 8,
              padding: 6,
              textAlign: 'center',
            }}
          >
            <span className="text-[9px] text-red-400 font-bold block uppercase" style={{ fontSize: 9, color: '#f87171', fontWeight: 700, display: 'block' }}>
              Avg Temp
            </span>
            <div className="text-xs font-mono font-bold text-red-200" style={{ fontSize: 12, fontFamily: 'IBM Plex Mono, monospace', fontWeight: 700, color: '#fecaca' }}>
              {activeLayer.avgTemp}°C
            </div>
            <span className="text-[8px] text-slate-400 font-mono" style={{ fontSize: 8, color: '#94a3b8', fontFamily: 'IBM Plex Mono, monospace' }}>
              {activeLayer.minTemp}–{activeLayer.maxTemp}°C
            </span>
          </div>

          <div
            className="bg-slate-900/90 border border-cyan-500/30 rounded-lg p-1.5 text-center"
            style={{
              background: 'rgba(15, 23, 42, 0.9)',
              border: '1px solid rgba(6, 182, 212, 0.3)',
              borderRadius: 8,
              padding: 6,
              textAlign: 'center',
            }}
          >
            <span className="text-[9px] text-cyan-400 font-bold block uppercase" style={{ fontSize: 9, color: '#22d3ee', fontWeight: 700, display: 'block' }}>
              Salinity
            </span>
            <div className="text-xs font-mono font-bold text-cyan-200" style={{ fontSize: 12, fontFamily: 'IBM Plex Mono, monospace', fontWeight: 700, color: '#cffafe' }}>
              {activeLayer.avgSalinity}
            </div>
            <span className="text-[8px] text-slate-400 font-mono" style={{ fontSize: 8, color: '#94a3b8', fontFamily: 'IBM Plex Mono, monospace' }}>
              PSU
            </span>
          </div>

          <div
            className="bg-slate-900/90 border border-emerald-500/30 rounded-lg p-1.5 text-center"
            style={{
              background: 'rgba(15, 23, 42, 0.9)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: 8,
              padding: 6,
              textAlign: 'center',
            }}
          >
            <span className="text-[9px] text-emerald-400 font-bold block uppercase" style={{ fontSize: 9, color: '#34d399', fontWeight: 700, display: 'block' }}>
              Chl-a
            </span>
            <div className="text-xs font-mono font-bold text-emerald-200" style={{ fontSize: 12, fontFamily: 'IBM Plex Mono, monospace', fontWeight: 700, color: '#a7f3d0' }}>
              {activeLayer.avgChlorophyll}
            </div>
            <span className="text-[8px] text-slate-400 font-mono" style={{ fontSize: 8, color: '#94a3b8', fontFamily: 'IBM Plex Mono, monospace' }}>
              mg/m³
            </span>
          </div>
        </div>

        {/* Excel Download Trigger Button */}
        <button
          onClick={() => setShowExportModal(true)}
          className="w-full py-1.5 px-3 bg-fuchsia-950/60 hover:bg-fuchsia-900/80 border border-fuchsia-500/50 rounded-lg text-xs font-semibold text-fuchsia-200 flex items-center justify-center gap-1.5 transition-colors shadow-sm"
          style={{
            width: '100%',
            padding: '6px 12px',
            background: 'rgba(74, 4, 78, 0.6)',
            border: '1px solid rgba(217, 70, 239, 0.5)',
            borderRadius: 8,
            fontSize: 11,
            fontWeight: 600,
            color: '#f5d0fe',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            cursor: 'pointer',
            marginTop: 2,
          }}
        >
          <span>📊</span> Download Excel Report (.xlsx)
        </button>
      </div>

      {/* EXCEL EXPORT CONFIGURATION MODAL */}
      {showExportModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm pointer-events-auto"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(6px)',
            pointerEvents: 'auto',
          }}
        >
          <div
            className="bg-slate-950 border border-cyan-500/40 rounded-2xl p-5 shadow-2xl w-[360px] text-white"
            style={{
              background: '#020617',
              border: '1px solid rgba(6, 182, 212, 0.4)',
              borderRadius: 16,
              padding: 20,
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)',
              width: 360,
              color: '#ffffff',
            }}
          >
            {/* Modal Header */}
            <div
              className="flex justify-between items-center border-b border-slate-800 pb-2.5 mb-3"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderBottom: '1px solid #1e293b',
                paddingBottom: 10,
                marginBottom: 12,
              }}
            >
              <h3
                className="text-sm font-bold text-cyan-300 flex items-center gap-2"
                style={{
                  margin: 0,
                  fontSize: 14,
                  fontWeight: 700,
                  color: '#67e8f9',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span>📑</span> Export Oceanographic Report
              </h3>
              <button
                onClick={() => setShowExportModal(false)}
                className="text-slate-400 hover:text-white text-xs font-mono p-1"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  fontSize: 14,
                }}
              >
                ✕
              </button>
            </div>

            <div
              className="space-y-2.5 mb-4 text-xs font-sans"
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                marginBottom: 16,
                fontSize: 12,
              }}
            >
              {/* Option 1: All Layers */}
              <label
                className="flex items-center gap-2 p-2 rounded-lg bg-slate-900/80 border border-slate-800 hover:border-slate-700 cursor-pointer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: 8,
                  borderRadius: 8,
                  background: 'rgba(15, 23, 42, 0.8)',
                  border: '1px solid #1e293b',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="exportMode"
                  checked={exportMode === 'all'}
                  onChange={() => setExportMode('all')}
                  className="accent-cyan-400"
                />
                <span className="font-semibold text-slate-200">
                  1. Download All Layers ({layers.length} total)
                </span>
              </label>

              {/* Option 2: Current Layer */}
              <label
                className="flex items-center gap-2 p-2 rounded-lg bg-slate-900/80 border border-slate-800 hover:border-slate-700 cursor-pointer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: 8,
                  borderRadius: 8,
                  background: 'rgba(15, 23, 42, 0.8)',
                  border: '1px solid #1e293b',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="exportMode"
                  checked={exportMode === 'current'}
                  onChange={() => setExportMode('current')}
                  className="accent-cyan-400"
                />
                <span className="font-semibold text-slate-200">
                  2. Download Current Layer (Layer {activeLayer.layerNumber})
                </span>
              </label>

              {/* Option 3: Layer Range */}
              <div
                className="p-2 rounded-lg bg-slate-900/80 border border-slate-800"
                style={{
                  padding: 8,
                  borderRadius: 8,
                  background: 'rgba(15, 23, 42, 0.8)',
                  border: '1px solid #1e293b',
                }}
              >
                <label
                  className="flex items-center gap-2 mb-2 cursor-pointer"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    marginBottom: exportMode === 'range' ? 8 : 0,
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    name="exportMode"
                    checked={exportMode === 'range'}
                    onChange={() => setExportMode('range')}
                    className="accent-cyan-400"
                  />
                  <span className="font-semibold text-slate-200">
                    3. From Layer – To Layer
                  </span>
                </label>

                {exportMode === 'range' && (
                  <div
                    className="flex items-center gap-2 pl-5 font-mono text-xs"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      paddingLeft: 20,
                      fontSize: 12,
                      fontFamily: 'IBM Plex Mono, monospace',
                    }}
                  >
                    <span>From:</span>
                    <input
                      type="number"
                      min={1}
                      max={layers.length}
                      value={rangeFrom}
                      onChange={(e) => setRangeFrom(Math.max(1, Number(e.target.value)))}
                      className="w-14 bg-slate-950 border border-cyan-500/40 rounded px-1.5 py-0.5 text-center text-cyan-300 outline-none"
                      style={{
                        width: 56,
                        background: '#020617',
                        border: '1px solid rgba(6, 182, 212, 0.4)',
                        borderRadius: 4,
                        padding: '2px 6px',
                        textAlign: 'center',
                        color: '#67e8f9',
                      }}
                    />
                    <span>To:</span>
                    <input
                      type="number"
                      min={rangeFrom}
                      max={layers.length}
                      value={rangeTo}
                      onChange={(e) => setRangeTo(Math.min(layers.length, Number(e.target.value)))}
                      className="w-14 bg-slate-950 border border-cyan-500/40 rounded px-1.5 py-0.5 text-center text-cyan-300 outline-none"
                      style={{
                        width: 56,
                        background: '#020617',
                        border: '1px solid rgba(6, 182, 212, 0.4)',
                        borderRadius: 4,
                        padding: '2px 6px',
                        textAlign: 'center',
                        color: '#67e8f9',
                      }}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex gap-2" style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setShowExportModal(false)}
                className="flex-1 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg text-xs font-semibold"
                style={{
                  flex: 1,
                  padding: '6px 12px',
                  background: '#0f172a',
                  border: '1px solid #1e293b',
                  color: '#94a3b8',
                  borderRadius: 8,
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleDownloadExcel}
                className="flex-1 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold rounded-lg text-xs transition-colors shadow"
                style={{
                  flex: 1,
                  padding: '6px 12px',
                  background: '#0891b2',
                  border: 'none',
                  color: '#020617',
                  borderRadius: 8,
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Export .xlsx
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default LayerSliceHUD;
