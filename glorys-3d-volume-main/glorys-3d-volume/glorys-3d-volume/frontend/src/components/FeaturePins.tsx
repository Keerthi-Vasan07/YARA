import React from 'react';

export interface FeaturePin {
  id?: string;
  type: 'chlorophyll' | 'salinity';
  lon: number;
  lat: number;
  depth: number;
  temperature?: number;
  salinity?: number;
  chlorophyll?: number;
  x?: number;
  y?: number;
  z?: number;
  profile?: any[];
}

export interface FeaturePinProps {
  pin: FeaturePin;
  onSelect: (pin: FeaturePin) => void;
}

export interface ThreeSyntheticEvent {
  stopPropagation: () => void;
  nativeEvent?: MouseEvent;
}

/**
 * FeaturePinMarker component for 3D marker display with explicit click & hover events.
 */
export const FeaturePinMarker: React.FC<FeaturePinProps> = ({ pin, onSelect }) => {
  const handleClick = (e: React.MouseEvent | ThreeSyntheticEvent) => {
    e.stopPropagation(); // Prevent camera controls or background clicks from overriding
    onSelect(pin);
  };

  return (
    <div
      onClick={handleClick}
      onPointerOver={(e) => {
        e.stopPropagation();
        document.body.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        document.body.style.cursor = 'auto';
      }}
      style={{ cursor: 'pointer' }}
    />
  );
};

export default FeaturePinMarker;
