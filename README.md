# IKT-Portalen

Intern nettportal for IT-avdelingen. Ansatte kan melde inn IT-problemer (support-ticket), lese brukerveiledninger og sjekke driftsstatus.

Bygget med **Python / Flask** og **SQLite**.

---

## Funksjoner

| Side | URL | Beskrivelse |
|------|-----|-------------|
| Forside | `/` | Oversikt og hurtiglenker |
| Support-ticket | `/ticket` | Meld inn IT-problem (lagres i SQLite) |
| Brukerveiledninger | `/brukerveiledninger` | Steg-for-steg IT-guider |
| Driftsstatus | `/driftsstatus` | Status på bedriftens systemer |

---

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
python app.py
```

Åpne `http://localhost:5000` i nettleseren.

---

## Serveroppsett (Proxmox / Ubuntu Server)

Kjør `server_setup.sh` på serveren for automatisk oppsett:

```bash
chmod +x server_setup.sh
sudo ./server_setup.sh
```

Skriptet:
1. Installerer Python 3, pip og git
2. Lager en dedikert systembruker (`iktportal`)
3. Kopierer appfiler til `/opt/ikt-portalen`
4. Setter opp et Python virtuelt miljø og installerer avhengigheter (inkl. Gunicorn)
5. Initialiserer SQLite-databasen
6. Registrerer og starter en `systemd`-tjeneste som starter automatisk ved omstart

Sett en fast IP-adresse på VM-en/containeren via Netplan (Ubuntu) eller Proxmox-grensesnittet før du kjører skriptet.

---

## Prosjektstruktur

```
mappelevering/
├── app.py                   # Flask-applikasjon og ruter
├── requirements.txt         # Python-avhengigheter
├── server_setup.sh          # Bash-oppsettskript for Ubuntu/Proxmox
├── ikt_portal.db            # SQLite-database (opprettes automatisk)
├── templates/
│   ├── base.html            # Felles layout (header/footer/nav)
│   ├── index.html           # Forside
│   ├── ticket.html          # Support-skjema
│   ├── success.html         # Bekreftelsesside etter innsending
│   ├── brukerveiledninger.html  # IT-guider
│   └── driftsstatus.html    # Systemstatus-tabell
└── static/
    └── css/
        └── style.css        # Stilark
```

---

## Sikkerhet og personvern

- Flask bruker Jinja2-maler som automatisk escaper brukerinput, noe som hindrer XSS.
- Alle SQL-spørringer bruker parametriserte verdier (`?`-plassholdere) for å unngå SQL-injeksjon.
- Brukeren må huke av samtykkeboks før skjemaet kan sendes inn (GDPR).
- Databasefilen (`ikt_portal.db`) bør ikke eksponeres offentlig – den ligger utenfor `static/`-mappen.