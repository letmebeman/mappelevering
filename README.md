# IKT-Portalen

Intern nettportal for IT-avdelingen. Ansatte kan melde inn IT-problemer (support-ticket), lese brukerveiledninger og sjekke driftsstatus.

Bygget med Python / Flask, SQLite og Gunicorn, og kjører som en systemd-tjeneste på Ubuntu Server i Proxmox.

## Funksjoner

| Side | URL | Beskrivelse |
|------|-----|-------------|
| Forside | `/` | Oversikt og hurtiglenker |
| Support-ticket | `/ticket` | Meld inn IT-problem (lagres i SQLite) |
| Brukerveiledninger | `/brukerveiledninger` | Steg-for-steg IT-guider |
| Driftsstatus | `/driftsstatus` | Live status på bedriftens systemer |
| Admin / Tickets | `/tickets` | Se innsendte tickets (krever innlogging) |

## Kom i gang (lokal utvikling)

```bash
# 1. Klon repoet
git clone https://github.com/letmebeman/mappelevering.git
cd mappelevering

# 2. Opprett virtuelt miljø og installer avhengigheter
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Start applikasjonen
cd /home/kubus/Documents/GitHub/mappelevering && . venv/bin/activate && set -a && source .env && set +a && python - <<'PY'
from app import app, init_db
init_db()
app.run(debug=False, use_reloader=False, host='127.0.0.1', port=5003)
PY

```

Åpne http://localhost:5000 i nettleseren.

## Serveroppsett (Proxmox / Ubuntu Server)

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

Merk: `gunicorn` må installeres manuelt da det ikke er i `requirements.txt`.

3. Opprett systemd-tjeneste

```bash
sudo tee /etc/systemd/system/ikt-portalen.service > /dev/null << 'EOF'
[Unit]
Description=IKT-Portalen Flask App
After=network.target

[Service]
User=iktportal
WorkingDirectory=/opt/ikt-portalen
Environment="PATH=/opt/ikt-portalen/venv/bin"
EnvironmentFile=-/opt/ikt-portalen/.env
ExecStart=/opt/ikt-portalen/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 app:app
Restart=always

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

Appen er nå tilgjengelig på `http://<VM-IP>:8000`.

7. (Valgfritt) Nginx som reverse proxy på port 80

```bash
sudo apt install nginx -y

sudo tee /etc/nginx/sites-available/ikt-portalen > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
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
sudo journalctl -u ikt-portalen -n 50 --no-pager
```

Vanlige feil og løsninger:

| Feil | Løsning |
|------|---------|
| `status=203/EXEC` | Gunicorn mangler — kjør `pip install gunicorn` i venv |
| `no such table: tickets` | Database ikke initialisert — kjør `init_db()` |
| `nano` krasjer i terminal | Bruk `export TERM=xterm` eller bruk `tee` med heredoc i stedet |

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

## Sikkerhet og personvern

- Flask bruker Jinja2-maler som automatisk escaper brukerinput, noe som hindrer XSS.
- Alle SQL-spørringer bruker parametriserte verdier (?-plassholdere) for å unngå SQL-injeksjon.
- Brukeren må huke av samtykkeboks før skjemaet kan sendes inn (GDPR).
- Databasefilen (`ikt_portal.db`) ligger utenfor `static/` og eksponeres ikke offentlig.
- `.env` skal aldri committes til Git — den er listet i `.gitignore`.

Hvis du ved et uhell har committet hemmeligheter, roter dem umiddelbart og fjern dem fra git-historikken med BFG eller `git filter-repo`.

## Driftsstatus — slik fungerer det

`/driftsstatus` utfører live sjekker mot tjenestene dine hver gang siden lastes:

- `http`: Gjør en HTTP-forespørsel — grønn hvis den får svar under 400
- `tcp`: Åpner en TCP-tilkobling — grønn hvis porten svarer
- `env-var`: Viser hardkodet fallback-melding fra koden
