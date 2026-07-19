FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render does not guarantee runtime environment variables during the Docker
# build. Force Django's production staticfiles backend here so WhiteNoise gets
# the hashed manifest required when DJANGO_DEBUG=0 at runtime.
RUN DJANGO_DEBUG=0 \
    DJANGO_SECRET_KEY=build-only-staticfiles-key \
    python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/health/', timeout=3)"

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py ensure_admin && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 60 --access-logfile - --error-logfile -"]
