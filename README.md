# IKT-Portalen

Intern nettportal for IT-avdelingen. Ansatte kan melde inn IT-problemer (support-ticket), lese brukerveiledninger og sjekke driftsstatus. Admin-delen viser ticket-oversikt, enkel observability og helse for app og database.

Bygget med Python / Flask, SQLite og Gunicorn. Appen kan kjøres lokalt for utvikling eller som Docker-stack på en VM/server. Stacken inneholder også Grafana, Loki og Grafana Alloy for enkel logging og observability.

## Funksjoner

| Side | URL | Beskrivelse |
|------|-----|-------------|
| Forside | `/` | Oversikt og hurtiglenker |
| Support-ticket | `/ticket` | Meld inn IT-problem (lagres i SQLite) |
| Brukerveiledninger | `/brukerveiledninger` | Steg-for-steg IT-guider |
| Driftsstatus | `/driftsstatus` | Live status på bedriftens systemer |
| Admin / Tickets | `/tickets` | Se innsendte tickets, endre status og følge observability (krever innlogging) |
| Helse | `/health` | JSON-helsetest for app og database |
| Metrics | `/metrics` | Enkel intern statistikk for admin |

## Kom i gang (lokal utvikling)
## NB!!!! terminal issue når ssh "export TERM=xterm"
```bash
# 1. Klon repoet
git clone https://github.com/letmebeman/mappelevering.git
cd mappelevering

# 2. Opprett virtuelt miljø og installer avhengigheter
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Sett lokale miljøvariabler for admin-login
export SECRET_KEY=lokal-utviklingsnøkkel
export ADMIN_PASSWORD=admin123

# 4. Start applikasjonen
python app.py

```

Åpne http://localhost:5000 i nettleseren.

## Dockeroppsett

Dockerfile bygger en container som kjører appen med Gunicorn. SQLite lagres i `/data`, så Docker Compose bruker et volume for å beholde tickets etter restart eller rebuild.

1. Lag eller oppdater `.env`

```env
SECRET_KEY=tilfeldig-hemmelig-streng
ADMIN_PASSWORD_HASH=lim-inn-hash-fra-make-hash-password
ADMIN_PASSWORD=ditt-valgte-passord
TICKET_HASH_SALT=tilfeldig-streng-for-ticket-hashing
```

`SECRET_KEY` og enten `ADMIN_PASSWORD` eller `ADMIN_PASSWORD_HASH` må være satt. Hvis ikke blir admin-login blokkert.

2. Bygg image

```bash
make docker-build
```

3. Start container

```bash
make docker-run
```

Dette kjører tilsvarende:

```bash
docker run --rm -p 5000:5000 --env-file .env -e DATABASE_PATH=/data/ikt_portal.db -v ikt_portalen_data:/data ikt-portalen
```

Åpne `http://localhost:5000`. På en VM bruker du `http://<VM-IP>:5000`.

## Docker Compose / Portainer stack

`docker-compose.yml` starter fire tjenester:

| Tjeneste | Port | Beskrivelse |
|----------|------|-------------|
| `ikt-portal` | `5000` | Flask/Gunicorn-applikasjonen |
| `grafana` | `3000` | Dashboard og loggvisning |
| `loki` | intern | Lagrer logger |
| `alloy` | intern `12345` | Leser Docker-logger og sender dem til Loki |

Før stacken deployes i Portainer må disse miljøvariablene settes under stackens environment variables:

```env
SECRET_KEY=lang-tilfeldig-hemmelig-verdi
ADMIN_PASSWORD=ditt-admin-passord
```

Alternativt kan `ADMIN_PASSWORD_HASH` brukes i stedet for `ADMIN_PASSWORD`, men da må `docker-compose.yml` oppdateres til å sende inn hash-variabelen.

Viktig for Portainer:

- Hvis stacken deployes fra Git, må repoet inneholde både `docker-compose.yml` og `alloy/config.alloy`.
- Hvis compose-filen limes direkte inn i Portainer, finnes ikke `./alloy/config.alloy` automatisk på serveren. Da må Alloy-konfigurasjonen opprettes på serveren og mountes med absolutt sti.
- `build: .` krever at Portainer har tilgang til repoet som build context. Hvis du deployer uten Git-build, bygg og push imaget først og bruk `image:` i stedet.

Alloy-konfigurasjonen ligger i `alloy/config.alloy`. Compose-filen mounter hele mappen:

```yaml
- ./alloy:/etc/alloy:ro
```

Da leser Alloy konfigurasjonen fra:

```text
/etc/alloy/config.alloy
```

## Docker drift og feilsøking

Bygg på nytt etter kodeendringer:

```bash
make docker-build
```

Start appen:

```bash
make docker-run
```

Se container-logger:

```bash
docker logs -f <container-id>
```

Vanlige feil og løsninger:

| Feil | Løsning |
|------|---------|
| Port `5000` er opptatt | Kjør `PORT=5001 make docker-run` |
| Admin-login virker ikke | Sjekk at `SECRET_KEY` og `ADMIN_PASSWORD` eller `ADMIN_PASSWORD_HASH` er satt i miljøvariabler |
| `Admin password is not configured` | Legg til `ADMIN_PASSWORD` eller `ADMIN_PASSWORD_HASH` i Portainer stack environment variables og redeploy |
| Alloy feiler med `not a directory` ved mount | Sjekk at `alloy/config.alloy` finnes som fil i Git-repoet eller på serveren, ikke som mappe |
| Tickets forsvinner etter rebuild | Sjekk at containeren startes med `-v ikt_portalen_data:/data` |
| `/health` viser databasefeil | Sjekk at `DATABASE_PATH=/data/ikt_portal.db` og at volumet er skrivbart |

## Slik bruker du admin-dashboardet

1. Gå til `/admin/login` og logg inn med passordet fra `.env`.
2. Dashboardet viser antall tickets, statusfordeling og høy prioritet.
3. Filtrer tickets med statusknappene for å vise åpne, under arbeid eller løste saker.
4. Endre status direkte i tabellen og lagre per ticket.
5. Bruk lenkene til `/brukerveiledninger`, `/driftsstatus`, `/health`, `/metrics` og Grafana for å forklare drift og feilsøking.

## Observability og logging

`/health` sjekker to ting:

- Flask-appen svarer
- SQLite-databasen kan åpnes og kjøre en enkel spørring

Eksempel på svar:

```json
{
    "status": "ok",
    "app": "ok",
    "database": "ok",
    "service": "ikt-portalen"
}
```

`/metrics` gir enkel intern statistikk for admin, blant annet antall tickets per status og kategori.

Logger skrives til standard output/stderr, så de kan leses med:

```bash
docker logs -f <container-id>
```

I Docker Compose-stack samles containerlogger også av Grafana Alloy. Alloy leser Docker-loggene fra:

```text
/var/lib/docker/containers/*/*.log
```

Loggene prosesseres med `stage.docker {}` og sendes til Loki:

```text
http://loki:3100/loki/api/v1/push
```

I Grafana kan Loki legges til som datasource med URL:

```text
http://loki:3100
```

Typiske hendelser som logges:

- Ticket opprettet
- Admin innlogging vellykket eller mislykket
- Ticket-status endret
- Ticket slettet
- Health check feilet

Hvis du bruker Grafana, legg inn URL-en som `GRAFANA_URL` i `.env` og vis den som en lenke i admin-dashboardet.

## Demo for eksamen

En enkel live-demonstrasjon kan være:

1. Åpne forsiden og vis kort hva portalen brukes til.
2. Opprett en ticket som normal bruker.
3. Vis at saken lagres i SQLite ved å åpne admin-dashboardet.
4. Logg inn som admin og endre status til `under arbeid` eller `løst`.
5. Åpne `/health` og vis at app og database er `ok`.
6. Vis `docker logs -f <container-id>` og forklar loggene.
7. Åpne Grafana eller annen serverovervåking og forklar hvordan drift følges.

## Simuler og fiks en vanlig feil

Den enkleste feilen å vise i en eksamensdemo er at databasen ikke er tilgjengelig.

### Simulere feilen

```bash
sudo chmod 000 /opt/ikt-portalen/ikt_portal.db
curl http://127.0.0.1:5000/health
```

Forventet resultat: `/health` viser databasefeil og loggen viser at helsesjekken feilet.

### Fikse feilen

```bash
sudo chmod 660 /opt/ikt-portalen/ikt_portal.db
sudo chown iktportal:iktportal /opt/ikt-portalen/ikt_portal.db
curl http://127.0.0.1:5000/health
```

Dette er en god demo fordi du kan bruke både logger, statuskommandoer og helse-endepunktet for å finne årsaken.

## Prosjektstruktur

```text
mappelevering/
├── alloy/
│   └── config.alloy              # Grafana Alloy-konfigurasjon for Docker-logger
├── app.py                       # Flask-applikasjon og ruter
├── docker-compose.yml            # Stack med app, Grafana, Loki og Alloy
├── Dockerfile                   # Docker-image for Gunicorn
├── Makefile                     # Lokale kommandoer for run, hashing og Docker
├── requirements.txt             # Python-avhengigheter
├── ikt_portal.db                # SQLite-database (opprettes automatisk)
├── templates/
│   ├── base.html                # Felles layout (header/footer/nav)
│   ├── index.html               # Forside
│   ├── ticket.html              # Support-skjema
│   ├── success.html             # Bekreftelsesside etter innsending
│   ├── brukerveiledninger.html  # IT-guider
│   └── driftsstatus.html        # Systemstatus-tabell
└── static/
    └── css/
        └── style.css            # Stilark
```

## Fagkobling til yrkesfaglige IT-emner

### Utvikling

- Modellere databasen for ticket-flyt med status, prioritet og kategori.
- Bruke testmiljø og enkel verifikasjon av `/health` og SQLite.
- Lage teknisk dokumentasjon for installasjon, bruk og drift.

### Brukerstøtte

- Feilsøke med logger, helseendepunkt og driftsstatus.
- Kartlegge brukerbehov gjennom supportskjema og brukerveiledninger.
- Bruke portalen som samarbeidsverktøy mellom bruker og IT-support.

### Driftsstøtte

- Kjøre Flask-applikasjonen som Docker-container med Gunicorn.
- Bruke Docker-kommandoer og container-logger for drift og feilsøking.
- Dokumentere installasjon, loggvurdering og enkel overvåking med Grafana, Loki og Alloy.

## Sikkerhet og personvern

- Flask bruker Jinja2-maler som automatisk escaper brukerinput, noe som hindrer XSS.
- Alle SQL-spørringer bruker parametriserte verdier (?-plassholdere) for å unngå SQL-injeksjon.
- Brukeren må huke av samtykkeboks før skjemaet kan sendes inn (GDPR).
- Databasefilen (`ikt_portal.db`) ligger utenfor `static/` og eksponeres ikke offentlig.
- `.env` skal aldri committes til Git — den er listet i `.gitignore`.
- Admin-passord og hemmelige nøkler skal settes i miljøvariabler, ikke hardkodes.
- Portalens data bør begrenses til det som er nødvendig for å løse support-saken.

Hvis du ved et uhell har committet hemmeligheter, roter dem umiddelbart og fjern dem fra git-historikken med BFG eller `git filter-repo`.

## Driftsstatus — slik fungerer det

`/driftsstatus` utfører live sjekker mot tjenestene dine hver gang siden lastes:

- `http`: Gjør en HTTP-forespørsel — grønn hvis den får svar under 400
- `tcp`: Åpner en TCP-tilkobling — grønn hvis porten svarer
- `env-var`: Viser hardkodet fallback-melding fra koden

## Kort forklaring av arkitekturen

- Flask håndterer web-ruter, validering og logging.
- SQLite lagrer support tickets i Docker-volumet på serveren.
- Gunicorn kjører appen som en stabil WSGI-tjeneste i Docker-containeren.
- Et Docker-volume lagrer SQLite-data utenfor containerens filsystem.
- Grafana Alloy leser Docker-containerlogger og sender dem til Loki.
- Grafana brukes til å utforske og vise loggene fra Loki.
