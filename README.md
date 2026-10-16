# Rogue DB

Rogue DB is a database of Free-Floating Planet candidates discovered by NASA's Nancy 
Grace Roman Space Telescope and other surveys.  The project is under development by the 
Roman Galactic Exoplanet Survey Project Investigation Team (RGES-PIT).  More information about our 
activities can be found on [our website](https://rges-pit.org/). 

## Contributors

William DeRocco [FFP Working Group lead for RGES-PIT]
Rachel Street [Rogue DB lead developer]
Katarzyna Kruzsyńska
Greg Olmshenk

## Statement of AI Usage

Claude Code has been used to accelerate the development of RogueDB, in particular for the development 
of the website itself, which is built using the TOM Toolkit and Django.  All model fitting and science 
analysis is developed and tested by humans. 

## Installation

RogueDB is a [TOM Toolkit](https://tom-toolkit.readthedocs.io/) (Django) project that uses a PostgreSQL
database. There are two ways to run it: with Docker, which brings the database and everything else,
or in a Python virtual environment, for which you provide the database.

### With Docker

You need [Docker](https://docs.docker.com/get-docker/) with Compose.

```bash
git clone https://github.com/rges-pit/rogue_db.git
cd rogue_db
cp .env.example .env
```

Edit `.env` and give `SECRET_KEY` a value (the file says how to make one). Then:

```bash
docker compose up --build
```

The first build takes several minutes: some of the scientific packages are compiled. When it has
started, RogueDB is at <http://localhost:8000> (change the port with `WEB_PORT` in `.env`). Make
yourself an account that can do everything:

```bash
docker compose run --rm web python manage.py createsuperuser
```

Four services run:

| Service   | What it is |
|-----------|------------|
| `db`      | PostgreSQL. Its data is kept in the volume `rogue_pgdata`. |
| `migrate` | Creates and updates the database's tables, then stops. Runs again on every `up`. |
| `web`     | The website, on port 8000. |
| `worker`  | `manage.py db_worker`, which does the tasks the website queues (a source's diagnostics, an event's thumbnail, the search for moving objects). Without it these are queued and never done. |

The pictures RogueDB makes are kept in the volume `rogue_data`. `docker compose down` stops everything and
keeps the data; **`docker compose down -v` deletes the database and the pictures.**

After changing the code, `docker compose up --build` rebuilds the image. The worker doesn't notice a change
of code by itself, so restart it if you don't rebuild: `docker compose restart worker`.

To ingest alerts, put their JSON files in a directory called `ingest` beside `docker-compose.yml`, then:

```bash
docker compose run --rm web python manage.py ingest_alerts /ingest --max-workers 4
```

This runs on the Django development server (`DEBUG` is on in `settings.py`). It is for trying RogueDB out and
for development; it isn't set up as a public deployment.

### In a virtual environment

You need Python (3.13 is what RogueDB is developed with; `pyproject.toml` allows 3.11 to 3.13) and a running
PostgreSQL server (the Docker setup uses version 16), with a role that can create databases (the tests create their own).

1. Create the database:

   ```bash
   createdb rogue_tom_db
   ```

2. Install the dependencies. They're listed in `pyproject.toml`, and the exact versions that are known to work
   are in `poetry.lock` and, for `pip`, in `requirements.txt`. Either:

   ```bash
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```

   or, with [Poetry](https://python-poetry.org/) (which makes the environment itself):

   ```bash
   poetry install --no-root
   poetry shell
   ```

   Some of the packages (`vbmicrolensing`, `george`, `kepler-py`) are compiled during installation if there is no
   ready-made one for your system, which needs a C/C++ compiler and `gfortran`: on macOS, the Xcode command line
   tools and `brew install gcc`; on Debian or Ubuntu, `sudo apt install build-essential gfortran`. `git` is
   needed too, as AltaiPony is installed from GitHub.

3. Set the settings. RogueDB reads them from environment variables (see below), not from a file, so put them in
   your environment. The simplest way is to copy `.env.example` to `.env`, fill it in, and load it into the shell
   you use for everything below:

   ```bash
   set -a; source .env; set +a
   ```

   At least `SECRET_KEY` is needed, and `DB_PASS` if your database has a password. Any setting can also be
   changed in a file called `local_settings.py` in the project's top directory (beside `manage.py`), which is read
   after `settings.py` if it exists, and is not committed.

4. Create the tables and an account, and run it. The website and the worker are separate processes, each in its
   own terminal (with the environment loaded in each):

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver        # the website, at http://localhost:8000
   python manage.py db_worker        # the tasks it queues; restart it after changing the code
   ```

### Settings

| Environment variable | What it is | Default |
|---|---|---|
| `SECRET_KEY` | Django's secret key. **Required.** | |
| `DB_NAME`, `DB_USER`, `DB_PASS` | The database, and who connects to it | `rogue_tom_db`, `postgres`, (none) |
| `DB_HOST`, `DB_PORT` | Where it is | `127.0.0.1`, `5432` |
| `ALLOWED_HOSTS` | The names the site is served as, comma-separated, if not just from the same computer | (none) |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | The Gmail account that sends email (see below) | (none) |

### Signing in, and email

Every user has to set up two-factor authentication (an authenticator app) the first time they sign in, and fill in
their name and email address. New people can ask for an account on the sign-in page; a superuser approves
them from the Users page.

Registration requests, their approval and password resets are sent by email, through Gmail (`smtp.gmail.com`, in
`settings.py`). Set `EMAIL_HOST_USER` to the address and `EMAIL_HOST_PASSWORD` to a Google
[App Password](https://support.google.com/accounts/answer/185833) for it (the account's own password doesn't
work: it needs 2-step verification on). Without them nothing is sent, and the Users page tells the superuser to
let people know themselves. To try the emails without sending any, run a local mail server
(`aiosmtpd`, which is in the development dependencies) and point `EMAIL_HOST` and `EMAIL_PORT` at it, with
`EMAIL_USE_TLS` off, in `local_settings.py`.

### Tests

```bash
python manage.py test custom_code.tests
```

(or `docker compose run --rm web python manage.py test custom_code.tests`.)

### Changing the dependencies

Edit `pyproject.toml`, then `poetry lock` to update `poetry.lock`, and make `requirements.txt` from it:

```bash
poetry export --without-hashes -o requirements.txt    # needs the poetry-plugin-export plugin
```

Both files are committed, so everyone gets the same versions.
