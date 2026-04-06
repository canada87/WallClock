# WallClock

Orologio fisico a sbarrette mobili controllato da ESP32 e gestito via web app locale.

28 servo motori alzano e abbassano sbarrette bianche su un pannello nero per formare
cifre in stile 7 segmenti (formato HH:MM). Il microcontrollore non calcola più l'ora
autonomamente: la chiede ogni 30 secondi a un server HTTP ospitato in casa, che
centralizza tutta la logica di configurazione.

---

## Architettura

```
┌─────────────┐   GET /api/clock        ┌──────────────────┐
│    ESP32    │ ──────────────────────► │  FastAPI Server  │
│             │ ◄────────────────────── │  (Docker)        │
│  2× PCA9685 │   {hour, minute, mode}  │                  │
│  28 servo   │                         │  SQLite DB       │
└─────────────┘                         └──────┬───────────┘
                                               │ http://SERVER:8000
                                         ┌─────▼───────┐
                                         │   Web UI    │
                                         │  (browser)  │
                                         └─────────────┘
```

**Firmware** (`time_finale.cpp`) — Arduino/ESP32:
- Poll HTTP ogni 30 secondi
- Aggiorna il display solo se l'ora è cambiata
- Scarica la configurazione servo dal server se `config_version` è cambiata
- Gestisce l'animazione sveglia (88:88 ↔ 00:00)

**Server** (`server/`) — FastAPI + SQLite, deployato con Docker:
- Calcola l'ora locale, applica le regole di schedule, gestisce timer/sveglia
- Espone API REST per il firmware e per la web UI

---

## Prerequisiti

### Server
- Docker + Docker Compose

### Firmware
- Arduino IDE o PlatformIO con board ESP32
- Librerie:
  - `ArduinoJson` (Benoit Blanchon) — Library Manager
  - `Adafruit PWM Servo Driver` — Library Manager
  - `HTTPClient` — inclusa nell'ESP32 core

---

## Installazione

### 1. Server

```bash
git clone <repo>
cd WallClock
docker compose up --build -d
```

La web UI è disponibile su `http://<IP-SERVER>:8000`

### 2. Firmware

Aprire `time_finale.cpp` e impostare le variabili in cima al file:

```cpp
const char* ssid     = "TUO_SSID";
const char* password = "TUA_PASSWORD";
const char* SERVER   = "http://192.168.1.X:8000";  // IP del server
```

Compilare e caricare sull'ESP32.

---

## Web UI

Accessibile da browser su `http://<IP-SERVER>:8000`.

| Tab | Funzione |
|-----|----------|
| **Dashboard** | Visualizzazione dell'ora attuale sul display fisico, stato sistema |
| **Orario** | Orari di attività feriali/weekend, giorni di esclusione (festività) |
| **Calibrazione** | Posizioni ON/OFF per ognuno dei 28 servo, display SVG interattivo |
| **Timer / Sveglia** | Countdown timer con preset rapidi, sveglia oraria, dismiss |
| **Impostazioni** | Fuso orario, ora legale, parametri animazione servo |

---

## API (per il firmware)

### `GET /api/clock`

Risposta in modalità normale:
```json
{ "active": true,  "hour": 14, "minute": 30, "mode": "clock",  "config_version": 3 }
```
Risposta fuori orario / sistema disabilitato:
```json
{ "active": false, "hour": null, "minute": null, "mode": "clock", "config_version": 3 }
```
Risposta timer attivo:
```json
{ "active": true,  "hour": 0,  "minute": 45, "mode": "timer",  "config_version": 3 }
```
Risposta sveglia/timer scaduto:
```json
{ "active": true,  "hour": 88, "minute": 88, "mode": "alarm_ringing", "config_version": 3 }
```

### `GET /api/servo-config`

```json
{
  "h_on":  [100, 310, 300, ...],
  "h_off": [300, 100, 100, ...],
  "m_on":  [ 90, 310, 300, ...],
  "m_off": [300, 100, 100, ...],
  "mid_offset": 150,
  "time_delay": 100,
  "time_delay2": 20
}
```

---

## Hardware

| Componente | Dettaglio |
|------------|-----------|
| MCU | ESP32 |
| Driver PWM | 2× PCA9685 (I²C: `0x40` ore, `0x41` minuti) |
| Servo | 28× micro servo |
| Display | 4 cifre 7 segmenti a sbarrette fisiche |

### Mappatura canali PCA9685

```
Board H (0x40):  canali 0-6  → Ore Unità  (segmenti a-g)
                 canali 7-13 → Ore Decine (segmenti a-g)

Board M (0x41):  canali 0-6  → Min Unità  (segmenti a-g)
                 canali 7-13 → Min Decine (segmenti a-g)
```

Ordine segmenti: `0=top  1=top-right  2=bot-right  3=bottom  4=bot-left  5=top-left  6=middle`

---

## Struttura del progetto

```
WallClock/
├── time_finale.cpp          # Firmware ESP32
├── docker-compose.yml
├── CLAUDE.md                # Contesto per Claude Code
└── server/
    ├── Dockerfile
    ├── requirements.txt
    ├── app/
    │   ├── main.py          # Entry point FastAPI
    │   ├── database.py      # SQLite su volume Docker (/data/wallclock.db)
    │   ├── models.py        # ORM models
    │   └── routers/
    │       ├── clock_api.py   # Endpoint per ESP32
    │       └── admin_api.py   # Endpoint per web UI
    └── static/
        └── index.html       # SPA (Tailwind + Alpine.js, zero build)
```

---

## Note di calibrazione

Dopo aver sostituito un servo per manutenzione, usare il tab **Calibrazione** per
riallinearlo:

1. Selezionare la cifra dal pannello sinistro
2. Cliccare il segmento da calibrare nel display SVG (si illumina in arancione)
3. Regolare "Posizione ON" e "Posizione OFF" con i slider
4. Premere **Salva Servo** — il firmware scaricherà i nuovi valori entro 30 secondi
