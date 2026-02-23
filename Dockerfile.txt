# Use official Python 3.11 slim (Debian 12/Bookworm base)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install prerequisites + Microsoft ODBC Driver 18
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    apt-transport-https \
    unixodbc-dev \
    build-essential \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

# Set STATIC_ROOT if still needed (from earlier)
ENV DJANGO_STATIC_ROOT=/app/staticfiles
RUN python manage.py collectstatic --noinput --clear

EXPOSE 8000

CMD ["gunicorn", "project_manager_ai.wsgi:application", "--bind", "0.0.0.0:8000", "--timeout", "120", "--workers", "1", "--log-level", "info"]
