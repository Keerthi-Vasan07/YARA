"""Provider-independent scalar analysis and continuous RGB gradients."""
from typing import Literal, Optional
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class GradientStop(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    position: float = Field(ge=0, le=1)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class AnalysisOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["none", "exact", "range"] = "none"
    exact_temperature: float = 30
    tolerance: float = Field(default=0.1, ge=0)
    range_min: float = 30
    range_max: float = 35
    flat_color: str = Field(default="#ff4500", pattern=r"^#[0-9a-fA-F]{6}$")
    stops: Optional[list[GradientStop]] = Field(default=None, min_length=2, max_length=32)

    @model_validator(mode="after")
    def validate_range_and_stops(self):
        if self.range_min > self.range_max:
            raise ValueError("Range minimum must be <= maximum")
        if self.stops:
            self.stops = sorted(self.stops, key=lambda stop: stop.position)
            if any(a.position == b.position for a, b in zip(self.stops, self.stops[1:])):
                raise ValueError("Gradient stop positions must be distinct")
        return self


def rgb(color):
    return np.array([int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)])


def gradient_rgba(normalized, stops):
    stops = stops or [GradientStop(position=0, color="#0000ff"), GradientStop(position=1, color="#ff0000")]
    positions = [s.position for s in stops]
    colors = np.array([rgb(s.color) for s in stops])
    rgba = np.ones((*normalized.shape, 4), dtype=float)
    for channel in range(3):
        rgba[..., channel] = np.interp(normalized, positions, colors[:, channel])
    return rgba


def analysis_values(frame, options):
    """Filtering uses Celsius for known temperature units; points retain native units."""
    values = np.asarray(frame.data, dtype=float)
    units = (frame.units or "").lower().replace(" ", "").replace("_", "")
    if options.mode != "none":
        if units in {"k", "kelvin", "degreekelvin", "degreeskelvin"}:
            return values - 273.15, "°C"
        if units in {"f", "°f", "degf", "degreefahrenheit", "degreesfahrenheit"}:
            return (values - 32) * 5 / 9, "°C"
    return values, frame.units


def analyze_slice(frame, options=None):
    options = options or AnalysisOptions()
    values, units = analysis_values(frame, options)
    valid = np.isfinite(frame.data)
    if frame.mask is not None:
        valid &= ~frame.mask
    if frame.fill_value is not None:
        valid &= frame.data != frame.fill_value
    matching = valid.copy()
    if options.mode == "exact":
        matching &= np.abs(values - options.exact_temperature) <= options.tolerance
    elif options.mode == "range":
        matching &= (values >= options.range_min) & (values <= options.range_max)
    selected = values[matching]
    count, total = int(matching.sum()), int(valid.sum())
    stats = {
        "variable": frame.variable_name, "units": units,
        "timestamp": frame.timestamp, "time_index": frame.time_index,
        "matching_cells": count, "valid_cells": total,
        "total_cells": int(values.size),
        "matching_percent": 100 * count / total if total else 0,
        "min": float(selected.min()) if count else None,
        "max": float(selected.max()) if count else None,
        "mean": float(selected.mean()) if count else None,
        "message": None if count else "No dataset values found for the selected filter and frame.",
    }
    return values, matching, stats
