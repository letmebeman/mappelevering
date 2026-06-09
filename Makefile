PYTHON := $(shell if [ -x venv/bin/python ]; then printf 'venv/bin/python'; else printf 'python3'; fi)
IMAGE ?= ikt-portalen
PORT ?= 5000

.PHONY: run hash-password docker-build docker-run

run:
	$(PYTHON) app.py

hash-password:
	$(PYTHON) -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Admin password: ')))"

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p $(PORT):5000 --env-file .env -e DATABASE_PATH=/data/ikt_portal.db -v ikt_portalen_data:/data $(IMAGE)
