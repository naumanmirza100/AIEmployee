FROM python:3.12-slim

# System dependencies.
#   * msodbcsql18 / unixodbc-dev  -> pyodbc, for DB_ENGINE=mssql
#   * default-libmysqlclient-dev  -> mysqlclient, for DB_ENGINE=mysql (Hostinger)
#     pkg-config is required by mysqlclient's build; without it pip fails with
#     "Can not find valid pkg-config name".
#   * cairo/gobject               -> PDF + chart rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg2 apt-transport-https ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev gcc \
    default-libmysqlclient-dev pkg-config \
    libcairo2-dev libgirepository1.0-dev gir1.2-pango-1.0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Default command = the web tier. The Celery worker and beat run from this same
# image with their own commands (see docker-compose.yml) — gunicorn does NOT
# start them, and core/apps.py only auto-starts Celery under `runserver`. Run
# all three or scheduled work silently never happens.
#
# `migrate` runs here so a single-service deploy still applies migrations; if
# you scale the web tier past one replica, move it to a release/pre-deploy step
# so replicas don't race each other.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn project_manager_ai.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 2 --timeout 120"]
