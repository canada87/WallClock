from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime
from .database import Base


class Setting(Base):
    __tablename__ = "settings"
    key   = Column(String, primary_key=True)
    value = Column(String, nullable=True)


class ServoPosition(Base):
    __tablename__ = "servo_positions"
    id       = Column(Integer, primary_key=True, autoincrement=True)
    board    = Column(String)   # 'H' or 'M'
    channel  = Column(Integer)  # 0-13
    pos_on   = Column(Integer)
    pos_off  = Column(Integer)


class Holiday(Base):
    __tablename__ = "holidays"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    date        = Column(Date, unique=True)
    description = Column(String, default="")


class TimerAlarm(Base):
    __tablename__ = "timer_alarm"
    id         = Column(Integer, primary_key=True)
    mode       = Column(String, default="clock")   # 'clock' | 'timer' | 'alarm'
    timer_end  = Column(DateTime, nullable=True)   # naive UTC
    alarm_time = Column(String,   nullable=True)   # "HH:MM"
    ringing    = Column(Boolean,  default=False)
