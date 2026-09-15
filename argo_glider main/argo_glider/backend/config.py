ERDDAP_BASE_URL="https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats"

ERDDAP_VARIABLES=[
    "PLATFORM_NUMBER",
    "time",
    "latitude",
    "longitude",
    "TEMP",
    "PSAL",
    "PRES",
    "CYCLE_NUMBER"
]

DATA_START_DATE="2024-01-01T00:00:00Z"

SURFACE_PRESSURE_MAX=5.0

MAX_TOTAL_OBSERVATIONS=50000

MAX_OBSERVATIONS_PER_FLOAT=1000


# Dynamic Glider discovery through official IFREMER FTP.
# No individual glider deployment ID is hardcoded.

GLIDER_FTP_HOST="ftp.ifremer.fr"
GLIDER_FTP_ROOT="/ifremer/glider/v2"

GLIDER_MAX_FILES=4
GLIDER_MAX_POINTS_PER_FILE=250
GLIDER_MAX_TOTAL_POINTS=1000

GLIDER_CACHE_SECONDS=900

REQUEST_TIMEOUT_SECONDS=120


ALLOWED_ORIGINS=[
    "http://127.0.0.1:5500",
    "http://localhost:5500"
]