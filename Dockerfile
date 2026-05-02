FROM python:3.12-slim

WORKDIR /code

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system --no-cache ".[dev]"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
