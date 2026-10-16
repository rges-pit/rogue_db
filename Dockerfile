# RogueDB, for trying it out and for development. It runs Django's development server (DEBUG is on in
# settings.py), so it isn't a production deployment.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The dependencies first, so that a change to the code doesn't reinstall them.
#   git: AltaiPony is installed from a commit of its GitHub repository (see pyproject.toml)
#   build-essential, gfortran: vbmicrolensing, george and kepler-py (needed by pyLIMA and AltaiPony)
#     have no wheels for Linux and are compiled. They're removed again once installed, in the same
#     step so that they don't stay in the image.
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential gfortran \
    && pip install -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential gfortran \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# The pictures that RogueDB makes (thumbnails, corner plots, periodograms) are written to data/, which
# docker-compose.yml keeps in a volume
RUN useradd --create-home rogue \
    && mkdir -p /app/data \
    && chown -R rogue:rogue /app/data
USER rogue

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
