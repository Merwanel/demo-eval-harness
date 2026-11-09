FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY harness/ harness/
COPY prompts/ prompts/

# campaign.json is bind-mounted at runtime
RUN touch /app/campaign.json

ENTRYPOINT ["python", "-m", "harness.runner"]
