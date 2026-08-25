FROM python:3.12-slim

WORKDIR /app

# Copy the full source so the editable install is self-contained; it must
# fail loudly (no `|| true`) if dependencies cannot be installed.
COPY . .

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
