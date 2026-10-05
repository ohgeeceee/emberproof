FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The inventory lives here. Mount it, back it up, encrypt it.
VOLUME ["/data"]
ENV EMBERPROOF_DATA=/data
EXPOSE 8787

# Bind 0.0.0.0 inside the container so the port mapping works.
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8787", "--data-dir", "/data"]