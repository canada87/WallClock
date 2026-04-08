from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..database import get_db
from ..models import Setting, ServoPosition, Holiday, TimerAlarm

router = APIRouter()


def _get(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


def _set(db: Session, key: str, value) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = str(value)
    else:
        db.add(Setting(key=key, value=str(value)))


def _local_dt(db: Session) -> datetime:
    """Return naive local datetime based on stored timezone settings."""
    tz  = int(_get(db, "timezone_offset", "1"))
    dst = int(_get(db, "daylight_saving",  "1"))
    return datetime.utcnow() + timedelta(hours=tz + dst)


def _display_frozen(db: Session, fetch_interval: int) -> bool:
    """True se l'intervallo non è ancora scaduto dall'ultimo aggiornamento display."""
    last_str = _get(db, "last_display_update", "")
    if not last_str:
        return False
    try:
        elapsed = (datetime.utcnow() - datetime.fromisoformat(last_str)).total_seconds()
        return elapsed < fetch_interval
    except ValueError:
        return False


def _record_display_update(db: Session, hour: int, minute: int) -> None:
    _set(db, "last_display_update", datetime.utcnow().isoformat())
    _set(db, "last_sent_hour",   str(hour))
    _set(db, "last_sent_minute", str(minute))
    db.commit()


@router.get("/clock")
def get_clock(db: Session = Depends(get_db)):
    # Registra il timestamp di ogni richiesta dall'ESP32
    _set(db, "last_esp_ping", datetime.utcnow().isoformat())
    db.commit()

    config_version  = int(_get(db, "config_version",  "1"))
    fetch_interval  = int(_get(db, "fetch_interval",  "30"))
    system_active   = _get(db, "active", "1") == "1"

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
            return _ringing(config_version, fetch_interval)
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        return {"active": True, "hour": min(h, 99), "minute": m,
                "mode": "timer", "config_version": config_version,
                "fetch_interval": fetch_interval}

    if ta and ta.mode == "alarm" and ta.alarm_time:
        ah, am = map(int, ta.alarm_time.split(":"))
        if local.hour == ah and local.minute == am:
            ta.ringing = True
            db.commit()

    if ta and ta.ringing:
        return _ringing(config_version, fetch_interval)

    # ── Force-update flag (bypassa schedule e freeze per un solo poll) ─
    if _get(db, "force_update", "0") == "1":
        row = db.query(Setting).filter(Setting.key == "force_update").first()
        if row:
            row.value = "0"
        _record_display_update(db, local.hour, local.minute)
        return {
            "active": True,
            "hour":   local.hour,
            "minute": local.minute,
            "mode":   "clock",
            "config_version":  config_version,
            "fetch_interval":  fetch_interval,
        }

    # ── Schedule check ───────────────────────────────────────────────
    if not system_active:
        return _inactive(config_version, local, fetch_interval)

    is_weekend = local.weekday() >= 5
    start = int(_get(db, "weekend_start" if is_weekend else "weekday_start",
                     "11" if is_weekend else "8"))
    end   = int(_get(db, "weekend_end"   if is_weekend else "weekday_end",
                     "23" if is_weekend else "21"))

    holiday = db.query(Holiday).filter(Holiday.date == local.date()).first()
    if holiday or not (start <= local.hour < end):
        return _inactive(config_version, local, fetch_interval)

    # ── Freeze display se l'intervallo non è scaduto ────────────────────
    if _display_frozen(db, fetch_interval):
        h = int(_get(db, "last_sent_hour",   str(local.hour)))
        m = int(_get(db, "last_sent_minute", str(local.minute)))
    else:
        _record_display_update(db, local.hour, local.minute)
        h, m = local.hour, local.minute

    return {
        "active": True,
        "hour":   h,
        "minute": m,
        "mode":   "clock",
        "config_version": config_version,
        "fetch_interval": fetch_interval,
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

def _ringing(cv: int, fi: int):
    return {"active": True, "hour": 88, "minute": 88,
            "mode": "alarm_ringing", "config_version": cv, "fetch_interval": fi}


def _inactive(cv: int, local: datetime, fi: int):
    return {"active": False, "hour": local.hour, "minute": local.minute,
            "mode": "clock", "config_version": cv, "fetch_interval": fi}
