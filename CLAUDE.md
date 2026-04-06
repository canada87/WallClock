# WallClock — Contesto per Claude Code

## Cos'è questo progetto

Orologio fisico a 28 servo motori controllato da un ESP32. I servo alzano e abbassano
sbarrette bianche su uno sfondo nero per formare cifre in stile 7 segmenti (HH:MM).
L'ESP32 non calcola più l'ora localmente: la chiede ogni 30 secondi a un server HTTP
locale che gestisce tutta la logica.

## Hardware

- **Microcontrollore**: ESP32
- **Driver servo**: 2× PCA9685 PWM I²C
  - Indirizzo `0x40` (`pwmH`) → board ore (14 servo, canali 0-13)
  - Indirizzo `0x41` (`pwmM`) → board minuti (14 servo, canali 0-13)
- **28 servo totali** — ogni servo muove una sbarretta (segmento)

### Mappatura canali → segmenti

| Canali | Cifra        | Segmenti |
|--------|--------------|----------|
| H 0-6  | Ore Unità    | a-g      |
| H 7-13 | Ore Decine   | a-g      |
| M 0-6  | Min Unità    | a-g      |
| M 7-13 | Min Decine   | a-g      |

Ordine segmenti nell'array `digits[digit][i]`:
`0=top(a)  1=top-right(b)  2=bot-right(c)  3=bottom(d)  4=bot-left(e)  5=top-left(f)  6=middle(g)`

### Posizioni servo

Ogni servo ha due posizioni memorizzate negli array a 14 elementi:
- `segmentHOn/MOff` — posizione "segmento acceso"
- `segmentHOff/MOff` — posizione "segmento spento"

I valori sono nell'unità raw del PCA9685 (range tipico 80–320, frequenza 50Hz).

### Logica di collisione segmento centrale

Il segmento centrale (g, indice 6) può collidere fisicamente con i segmenti b (top-right)
e f (top-left). La funzione `updateMid()` gestisce questo: prima sposta gli adiacenti
`midOffset` unità "fuori strada", poi muove il centrale, poi `updateDisplay()` li rimette
al posto corretto.

**Non toccare `updateMid()` e `updateDisplay()` a meno di bug evidenti.**

## Struttura repository

```
WallClock/
├── time_finale.cpp          # Firmware ESP32 (Arduino/PlatformIO)
├── docker-compose.yml       # Avvia il server
└── server/
    ├── Dockerfile
    ├── requirements.txt     # fastapi, uvicorn, sqlalchemy, pydantic
    ├── app/
    │   ├── main.py          # FastAPI app + seed DB
    │   ├── database.py      # SQLite su /data/wallclock.db
    │   ├── models.py        # Setting, ServoPosition, Holiday, TimerAlarm
    │   └── routers/
    │       ├── clock_api.py   # /api/clock  /api/servo-config  (per ESP32)
    │       └── admin_api.py   # /api/admin/*  (per la web UI)
    └── static/
        └── index.html       # SPA — Tailwind CSS + Alpine.js v3
```

## API per il microcontrollore

### `GET /api/clock`
```json
{
  "active": true,
  "hour": 14,
  "minute": 30,
  "mode": "clock",          // "clock" | "timer" | "alarm_ringing"
  "config_version": 3
}
```
- `active: false` → fuori orario o sistema disabilitato → non aggiornare il display
- `hour: 88, minute: 88` + `mode: "alarm_ringing"` → fare animazione 88:88 ↔ 00:00
- `mode: "timer"` → `hour` e `minute` sono i minuti/ore rimanenti al countdown

### `GET /api/servo-config`
```json
{
  "h_on":  [14 interi],
  "h_off": [14 interi],
  "m_on":  [14 interi],
  "m_off": [14 interi],
  "mid_offset": 150,
  "time_delay": 100,
  "time_delay2": 20
}
```
Recuperato all'avvio e ogni volta che `config_version` cambia.

## Logica firmware (time_finale.cpp)

1. **Boot**: init PCA9685 → tutti segmenti OFF → connetti WiFi → `fetchServoConfig()` → `fetchClockData()`
2. **Loop ogni 30s**: `ensureWiFi()` → `fetchClockData()`
3. `fetchClockData()`:
   - Se `config_version` diversa → `fetchServoConfig()` + aggiorna `lastConfigVersion`
   - Se `active: false` → skip
   - Se `mode == "alarm_ringing"` → `doAlarmAnimation()` (5 cicli 88:88↔00:00)
   - Altrimenti → se ora/minuto cambiati → `updateDisplay()`

## Database (SQLite)

| Tabella         | Contenuto                                              |
|-----------------|--------------------------------------------------------|
| `settings`      | key-value: timezone_offset, daylight_saving, weekday_start/end, weekend_start/end, mid_offset, time_delay, time_delay2, active, config_version |
| `servo_positions` | 28 righe: board (H/M), channel (0-13), pos_on, pos_off |
| `holidays`      | date, description — giorni in cui l'orologio non si aggiorna |
| `timer_alarm`   | mode (clock/timer/alarm), timer_end (UTC naive), alarm_time (HH:MM), ringing |

Il DB viene pre-popolato con i valori default del firmware originale al primo avvio.

## Web UI (index.html)

SPA con 5 tab:
- **Dashboard**: visualizzazione SVG 7-segmenti dell'ora attuale, stato modalità
- **Orario**: orari attivi feriali/weekend, gestione giorni di esclusione
- **Calibrazione**: editor visuale per le posizioni ON/OFF di ciascuno dei 28 servo
- **Timer / Sveglia**: countdown timer con preset, sveglia oraria, dismiss
- **Impostazioni**: fuso orario, DST, parametri animazione (mid_offset, time_delay, time_delay2)

Framework: Tailwind CSS + Alpine.js v3 via CDN. Zero build step.

## Come avviare

```bash
# dalla root del progetto
docker compose up --build
# UI disponibile su http://SERVER_IP:8000
```

## Librerie Arduino necessarie

- `HTTPClient.h` — inclusa nell'ESP32 Arduino core
- `ArduinoJson` — installare da Library Manager (Benoit Blanchon)
- `Adafruit_PWMServoDriver` — installare da Library Manager

Prima di flashare: impostare `ssid`, `password` e `SERVER` in `time_finale.cpp`.

## Cose da non fare

- Non riscrivere `updateMid()` e `updateDisplay()` — la logica di collisione è
  calibrata sull'hardware fisico
- Non cambiare il DB path (`/data/wallclock.db`) senza aggiornare il volume Docker
- Non togliere `config_version` dal bump quando si salva la configurazione servo —
  è il meccanismo con cui il firmware sa che deve scaricare i nuovi valori
