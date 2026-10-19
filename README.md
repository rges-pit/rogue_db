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

RogueDB is a [TOM Toolkit](https://tom-toolkit.readthedocs.io/) project, based on the Django webframework that uses a PostgreSQL
database. There are two ways to install and run it on a local server: 

* Build the docker container, which includes both the codebase and the database, or
* Build a Python virtual environment, and spin up your own database following the instructions below.

Both options require `git` to be installed. 

RogueDB includes scripts to automate the ingest of sets of alerts for analysis.  

Be aware that this runs on the Django development server (`DEBUG` is on in `settings.py`).  

### Configuration and required parameters

There are a few necessary parameters that must be declared during the installation.  These are 
listed in the file ``.env.example``, and the file's role in the installation is described below.  
Regardless of which method you choose, you need to set some of these parameters (see the file for details). 
The optional parameters are only required if you want to activate user registration with email approval. 
Full documentation on that process is [here](https://tom-toolkit.readthedocs.io/en/stable/common/email_configuration.html).  


### With Docker

RogueDB's repo includes ``Dockerfile'' that can be used to build a Docker container with all the necessary 
dependencies installed.  For this path, you will need [Docker](https://docs.docker.com/get-docker/) installed with Compose.

First, clone the repository from Github:

```bash
git clone https://github.com/rges-pit/rogue_db.git
cd rogue_db
cp .env.example .env
```

Edit the `.env` file and generate a `SECRET_KEY` value following the instructions in the file. 

Then build the container from the ``docker-compose.yml`` file:

```bash
docker compose up --build
```

The first build will likely take several minutes, since not all of the scientific packages used by RogueDB 
provide PyPI wheels and have to be compiled.  Once the build has finished, open a browser and enter 
http://localhost:8000 into the navigation bar.  Note that you can change the port number by editing the  
`WEB_PORT` variable in `.env`. 

Leave the terminal with this container running open since it is running the webservice for RogueDB's user 
interface.  All subsequent commands can be run in a different terminal. 

BEFORE YOU PROCEED: You will need to make a superuser account for the system by running the following at the 
commandline prompt:

```bash
docker compose run --rm web python manage.py createsuperuser
```

The container creates four services:

| Name      | Service                                                                                                                                                                                   |
|-----------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `db`      | PostgreSQL. Its data is kept in the volume `rogue_pgdata`.                                                                                                                                |
| `migrate` | Creates and updates the database's tables, then stops. Runs again on every `up`.                                                                                                          |
| `web`     | The website, on port 8000.                                                                                                                                                                |
| `worker`  | `manage.py db_worker`, which does the tasks the website queues (a source's diagnostics, an event's thumbnail, the search for moving objects). Without it these are queued and never done. |

Image files created by RogueDB (e.g. lightcurve thumbnails) makes are kept in the volume `rogue_data`.

`docker compose up` starts the existing container image

`docker compose down` stops everything and keeps the data; 

**`docker compose down -v` deletes the database and the pictures.**

After changing the code, `docker compose up --build` rebuilds the image. The worker doesn't notice a change
of code by itself, so restart it if you don't rebuild: `docker compose restart worker`.

To ingest alerts, put their JSON files in a directory called `ingest` beside `docker-compose.yml`, then:

```bash
docker compose run --rm web python manage.py ingest_alerts /ingest --max-workers 4
```


### With a virtual environment

You need Python (3.13 is what RogueDB is developed with; `pyproject.toml` allows 3.11 to 3.13) and a running
PostgreSQL server (the Docker setup uses version 16), with a role that can create databases (the tests create their own).

1. Create the database:

   ```bash
   git clone https://github.com/rges-pit/rogue_db.git
   cd rogue_db
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

   Some of the packages (`vbmicrolensing`, `george`, `kepler-py`) do not distribute wheels to PyPI and therefore have 
   to be compiled during installation.  This requires a C/C++ compiler and `gfortran`: on macOS, the Xcode command line
   tools and `brew install gcc`; on Debian or Ubuntu, `sudo apt install build-essential gfortran`. `git` is
   needed too, as AltaiPony is installed from GitHub.

3. The configuration for RogueDB is set by the `~/rogue_db/settings.py` file.  However, this includes a number of 
   sensitive parameters such as passwords.  Rather than set these directly in the file (where they could be committed to 
   a public repository) some of the parameters are configured as environment variables.  
   The simplest way is to add the parameters described in the `.env.example` file to your environment script 
   (i.e. `env/bin/activate/`):

   ```bash
   SECRET_KEY="..."
   export SECRET_KEY
   ...
   ```
   
   Parameters set in the environment this way are immediately set as soon as you activate the environment.     

   Any setting can also be changed in a file called `local_settings.py` in the project's top directory 
   (beside `manage.py`), which is read after `settings.py` if it exists, and is not committed.

4. Create the tables and an account, and run it. The website and the worker are separate processes, each in its
   own terminal (with the environment loaded in each):

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver        # the website, at http://localhost:8000
   python manage.py db_worker        # the tasks it queues; restart it after changing the code
   ```

To ingest alerts, you can run the ingest script as before, but the JSON files for the alerts 
can be in any directory you wish.  

```bash
docker python manage.py ingest_alerts <path to alerts directory> --max-workers 4
```

### Settings

| Environment variable | What it is | Default                                 |
|---|---|-----------------------------------------|
| `SECRET_KEY` | Django's secret key. **Required.** |                                         |
| `DB_NAME`, `DB_USER`, `DB_PASS` | The database, and who connects to it | e.g. `rogue_tom_db`, `postgres`, (none) |
| `DB_HOST`, `DB_PORT` | Where it is | `127.0.0.1`, `5432`                     |
| `ALLOWED_HOSTS` | The names the site is served as, comma-separated, if not just from the same computer | (none)                                  |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | The Gmail account that sends email (see below) | (none)                                  |

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
