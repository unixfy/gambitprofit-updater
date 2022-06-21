FROM python:3-buster
ENV PYTHONUNBUFFERED=1

WORKDIR /app
# Copy everything from update-from-gambitrewards-script to the workdir (/app)
COPY . ./
RUN chmod 0777 /app/update-from-gambitrewards.py

# Install deps
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Run cron
CMD yacron -c /app/crontab.yaml