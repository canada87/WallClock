from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import engine, SessionLocal
from . import models
from .routers import clock_api, admin_api

# Default servo positions (same as original firmware)
_H_ON  = [100, 310, 300, 300, 100, 130,  95, 100, 300, 300, 300, 100, 110, 120]
_H_OFF = [300, 100, 100, 100, 300, 320, 300, 300, 100, 100, 100, 300, 300, 300]
_M_ON  = [ 90, 310, 300, 300, 100, 100,  80, 100, 310, 300, 300,  90, 100, 130]
_M_OFF = [300, 100, 100, 100, 300, 300, 300, 300, 100, 100, 100, 300, 320, 300]


def _seed():
    db = SessionLocal()
    try:
        from .models import Setting, ServoPosition
        defaults = {
            "timezone_offset": "1",
            "daylight_saving": "1",
            "weekday_start":   "8",
            "weekday_end":     "21",
            "weekend_start":   "11",
            "weekend_end":     "23",
            "config_version":  "1",
            "mid_offset":      "150",
            "time_delay":      "100",
            "time_delay2":     "20",
            "active":          "1",
            "fetch_interval":  "30",
        }
        for k, v in defaults.items():
            if not db.query(Setting).filter(Setting.key == k).first():
                db.add(Setting(key=k, value=v))

        if db.query(ServoPosition).count() == 0:
            for ch in range(14):
                db.add(ServoPosition(board="H", channel=ch,
                                     pos_on=_H_ON[ch],  pos_off=_H_OFF[ch]))
                db.add(ServoPosition(board="M", channel=ch,
                                     pos_on=_M_ON[ch],  pos_off=_M_OFF[ch]))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    _seed()
    yield


app = FastAPI(title="WallClock Controller", lifespan=lifespan)
app.include_router(clock_api.router, prefix="/api")
app.include_router(admin_api.router, prefix="/api/admin")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
