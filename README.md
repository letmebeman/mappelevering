# IKT-Portalen

Intern nettportal for IT-avdelingen. Ansatte kan melde inn IT-problemer (support-ticket), lese brukerveiledninger og sjekke driftsstatus. Admin-delen viser ticket-oversikt, enkel observability og helse for app og database.

Bygget med Python / Flask, SQLite og Gunicorn, og kjører som en systemd-tjeneste på Ubuntu Server i Proxmox.

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

## Serveroppsett (Proxmox / Ubuntu Server)

For produksjon bruker du vanligvis Gunicorn via systemd, ikke Flask sin innebygde utviklingsserver.

1. Klon repoet på serveren

```bash
git clone https://github.com/letmebeman/mappelevering.git /opt/ikt-portalen
cd /opt/ikt-portalen
```

2. Opprett virtuelt miljø og installer avhengigheter

```bash
sudo python3 -m venv /opt/ikt-portalen/venv
sudo /opt/ikt-portalen/venv/bin/pip install -r requirements.txt
sudo /opt/ikt-portalen/venv/bin/pip install gunicorn
sudo chown -R iktportal:iktportal /opt/ikt-portalen
```

Merk: `server_setup.sh` installerer `gunicorn` automatisk. Denne manuelle kommandoen er bare nødvendig hvis du setter opp tjenesten uten skriptet.

3. Opprett systemd-tjeneste

```bash
sudo tee /etc/systemd/system/ikt-portalen.service > /dev/null << 'EOF'
[Unit]
Description=IKT-Portalen Flask App
After=network.target

[Service]
User=iktportal
Group=iktportal
WorkingDirectory=/opt/ikt-portalen
Environment="PATH=/opt/ikt-portalen/venv/bin"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=-/opt/ikt-portalen/.env
ExecStart=/opt/ikt-portalen/venv/bin/gunicorn --workers 2 --bind 0.0.0.0:5000 --access-logfile - --error-logfile - app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

4. Konfigurer miljøvariabler

```bash
sudo nano /opt/ikt-portalen/.env
```

Minimal `.env` for skoleprosjekt:

```env
SECRET_KEY=tilfeldig-hemmelig-streng
ADMIN_PASSWORD=ditt-valgte-passord

DRIFTSSTATUS_TEAMS_URL=https://teams.microsoft.com
```

Valgfrie driftsstatus-variabler (sett kun de du faktisk har):

```env
DRIFTSSTATUS_EMAIL_URL=https://mail.domene.no
DRIFTSSTATUS_VPN_HOST=vpn.domene.no
DRIFTSSTATUS_VPN_PORT=443
DRIFTSSTATUS_FILESERVER_HOST=192.168.1.10
DRIFTSSTATUS_FILESERVER_PORT=445
DRIFTSSTATUS_PRINTER_HOST=192.168.1.20
DRIFTSSTATUS_PRINTER_PORT=9100
```

Variabler som ikke er satt bruker automatisk fallback-statusen fra koden ("Normal drift").

Sett riktige tilganger på filen:

```bash
sudo chmod 600 /opt/ikt-portalen/.env
sudo chown iktportal:iktportal /opt/ikt-portalen/.env
```

5. Initialiser databasen

```bash
cd /opt/ikt-portalen
sudo -u iktportal /opt/ikt-portalen/venv/bin/python -c "from app import init_db; init_db()"
```

6. Start tjenesten

```bash
sudo systemctl daemon-reload
sudo systemctl enable ikt-portalen
sudo systemctl start ikt-portalen
sudo systemctl status ikt-portalen
```

Appen er nå tilgjengelig på `http://<VM-IP>:5000`.

Stopp, start og restart:

```bash
sudo systemctl stop ikt-portalen
sudo systemctl start ikt-portalen
sudo systemctl restart ikt-portalen
```

7. (Valgfritt) Nginx som reverse proxy på port 80

```bash
sudo apt install nginx -y

sudo tee /etc/nginx/sites-available/ikt-portalen > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/ikt-portalen /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl restart nginx
```

## Oppdatere appen etter nye endringer

```bash
cd /opt/ikt-portalen
sudo -u iktportal git pull
sudo systemctl restart ikt-portalen
```

Hvis du har lagt til nye Python-pakker:

```bash
sudo /opt/ikt-portalen/venv/bin/pip install -r requirements.txt
```

Hvis du har endret databasestrukturen:

```bash
sudo -u iktportal /opt/ikt-portalen/venv/bin/python -c "from app import init_db; init_db()"
```

## Feilsøking

Se live logger:

```bash
sudo journalctl -u ikt-portalen -f
```

Vanlige feil og løsninger:

| Feil | Løsning |
|------|---------|
| `status=203/EXEC` | Gunicorn mangler — kjør `pip install gunicorn` i venv |
| `no such table: tickets` | Database ikke initialisert — kjør `init_db()` |
| `nano` krasjer i terminal | Bruk `export TERM=xterm` eller bruk `tee` med heredoc i stedet |

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
sudo journalctl -u ikt-portalen -f
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
6. Vis `journalctl -u ikt-portalen -f` og forklar loggene.
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
├── app.py                       # Flask-applikasjon og ruter
├── requirements.txt             # Python-avhengigheter
├── server_setup.sh              # Bash-oppsettskript for Ubuntu/Proxmox
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

- Kjøre Flask-applikasjonen som systemd-tjeneste med Gunicorn.
- Bruke Linux-verktøy som `systemctl` og `journalctl` for drift og feilsøking.
- Dokumentere installasjon, loggvurdering og enkel overvåking med Grafana.

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
- SQLite lagrer support tickets lokalt på Linux-serveren.
- Gunicorn kjører appen som en stabil WSGI-tjeneste bak systemd.
- Nginx kan brukes som reverse proxy hvis du vil vise en mer realistisk produksjonsløsning.
