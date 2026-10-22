FROM python:3.12.10-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN pip install --no-deps -e .
RUN useradd --create-home --uid 10001 platform
USER platform
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
