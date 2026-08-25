FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN mkdir -p uploads
ENV COOKIE_SECURE=0
EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn_conf.py", "wsgi:app"]
