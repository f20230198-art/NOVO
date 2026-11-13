from fastapi import APIRouter, HTTPException, Query

from ..services import sea_grid
from ..services.forecast import ForecastUnavailable

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("/grid")
async def get_grid(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    """Wave height/direction and wind speed/direction over a 9x9 grid of sea points around
    (lat, lon), next 24 hours. For drawing the map only: it carries no verdict and the
    verdict never reads it. Public data, so no token is needed (the harbour is sent, not a boat)."""
    try:
        return await sea_grid.get_grid(lat, lon)
    except ForecastUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Sea grid unavailable: {exc}")
