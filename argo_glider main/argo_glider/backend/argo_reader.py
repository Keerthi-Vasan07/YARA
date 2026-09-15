import truststore
truststore.inject_into_ssl()
import pandas as pd
import requests
from dataclasses import dataclass,field
from typing import Optional
from .config import *

@dataclass
class FloatObservation:
    lat: float
    lon: float
    time: str
    temperature: Optional[float]
    salinity: Optional[float]
    pressure: Optional[float]
    cycle: Optional[int]
    index: int

@dataclass
class FloatTrajectory:
    float_id: str
    source: str
    points: list[FloatObservation]=field(default_factory=list)

def fetch_argo_dataframe():
    variables=",".join(ERDDAP_VARIABLES)
    constraints=f"time>={DATA_START_DATE}&PRES>=0&PRES<={SURFACE_PRESSURE_MAX}"
    url=f"{ERDDAP_BASE_URL}.json?{variables}&{constraints}"
    r=requests.get(url,timeout=REQUEST_TIMEOUT_SECONDS)
    r.raise_for_status()
    payload=r.json()["table"]
    df=pd.DataFrame(payload["rows"],columns=payload["columnNames"])
    if df.empty: return df
    for c in ["latitude","longitude","TEMP","PSAL","PRES","CYCLE_NUMBER"]:
        df[c]=pd.to_numeric(df[c],errors="coerce")
    df["time_parsed"]=pd.to_datetime(df["time"],utc=True,errors="coerce")
    df=df.dropna(subset=["PLATFORM_NUMBER","time_parsed","latitude","longitude"])
    df=df[df.latitude.between(-90,90)&df.longitude.between(-180,180)]
    df=df[df.TEMP.isna()|df.TEMP.between(-3,40)]
    df=df.sort_values(["PLATFORM_NUMBER","time_parsed"])
    df=df.drop_duplicates(["PLATFORM_NUMBER","CYCLE_NUMBER"],keep="last")
    return df.sort_values("time_parsed",ascending=False).head(MAX_TOTAL_OBSERVATIONS)

def get_float_trajectories():
    df=fetch_argo_dataframe()
    result=[]
    for fid,g in df.groupby("PLATFORM_NUMBER",sort=True):
        g=g.sort_values("time_parsed").tail(MAX_OBSERVATIONS_PER_FLOAT)
        points=[]
        for i,(_,row) in enumerate(g.iterrows()):
            def num(x): return None if pd.isna(x) else float(x)
            cyc=None if pd.isna(row.CYCLE_NUMBER) else int(row.CYCLE_NUMBER)
            points.append(FloatObservation(float(row.latitude),float(row.longitude),
                row.time_parsed.strftime("%Y-%m-%dT%H:%M:%SZ"),num(row.TEMP),
                num(row.PSAL),num(row.PRES),cyc,i))
        if points: result.append(FloatTrajectory(str(fid),
            "INCOIS ERDDAP - Indian_ARGO_Floats",points))
    return result
