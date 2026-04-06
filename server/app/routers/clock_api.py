from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..database import get_db
from ..models import Setting, ServoPosition, Holiday, TimerAlarm

router = APIRouter()


def _get(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


def _local_dt(db: Session) -> datetime:
    """Return naive local datetime based on stored timezone settings."""
    tz  = int(_get(db, "timezone_offset", "1"))
    dst = int(_get(db, "daylight_saving",  "1"))
    return datetime.utcnow() + timedelta(hours=tz + dst)


@router.get("/clock")
def get_clock(db: Session = Depends(get_db)):
    config_version = int(_get(db, "config_version", "1"))
    system_active  = _get(db, "active", "1") == "1"

    local = _local_dt(db)

    # ── Timer / Alarm ────────────────────────────────────────────────
    ta = db.query(TimerAlarm).filter(TimerAlarm.id == 1).first()

    if ta and ta.mode == "timer" and ta.timer_end:
        remaining = ta.timer_end - datetime.utcnow()
        secs = remaining.total_seconds()
        if secs <= 0:
            ta.ringing = True
            ta.mode    = "clock"
            db.commit()
            return _ringing(config_version)
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        return {"active": True, "hour": min(h, 99), "minute": m,
                "mode": "timer", "config_version": config_version}

    if ta and ta.mode == "alarm" and ta.alarm_time:
        ah, am = map(int, ta.alarm_time.split(":"))
        if local.hour == ah and local.minute == am:
            ta.ringing = True
            db.commit()

    if ta and ta.ringing:
        return _ringing(config_version)

    # ── Force-update flag (bypassa schedule per un solo poll) ───────
    if _get(db, "force_update", "0") == "1":
        row = db.query(Setting).filter(Setting.key == "force_update").first()
        if row:
            row.value = "0"
        db.commit()
        return {
            "active": True,
            "hour":   local.hour,
            "minute": local.minute,
            "mode":   "clock",
            "config_version": config_version,
        }

    # ── Schedule check ───────────────────────────────────────────────
    if not system_active:
        return _inactive(config_version, local)

    is_weekend = local.weekday() >= 5
    start = int(_get(db, "weekend_start" if is_weekend else "weekday_start",
                     "11" if is_weekend else "8"))
    end   = int(_get(db, "weekend_end"   if is_weekend else "weekday_end",
                     "23" if is_weekend else "21"))

    holiday = db.query(Holiday).filter(Holiday.date == local.date()).first()
    if holiday or not (start <= local.hour < end):
        return _inactive(config_version, local)

    return {
        "active": True,
        "hour":   local.hour,
        "minute": local.minute,
        "mode":   "clock",
        "config_version": config_version,
    }


@router.get("/servo-config")
def get_servo_config(db: Session = Depends(get_db)):
    def _arr(board: str, which: str):
        rows = (db.query(ServoPosition)
                  .filter(ServoPosition.board == board)
                  .order_by(ServoPosition.channel)
                  .all())
        return [r.pos_on if which == "on" else r.pos_off for r in rows]

    return {
        "h_on":       _arr("H", "on"),
        "h_off":      _arr("H", "off"),
        "m_on":       _arr("M", "on"),
        "m_off":      _arr("M", "off"),
        "mid_offset": int(_get(db, "mid_offset",  "150")),
        "time_delay":  int(_get(db, "time_delay",  "100")),
        "time_delay2": int(_get(db, "time_delay2", "20")),
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _ringing(cv: int):
    return {"active": True, "hour": 88, "minute": 88,
            "mode": "alarm_ringing", "config_version": cv}


def _inactive(cv: int, local: datetime):
    return {"active": False, "hour": local.hour, "minute": local.minute,
            "mode": "clock", "config_version": cv}
