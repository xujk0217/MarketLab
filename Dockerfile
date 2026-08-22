# MarketLab container image: installs the package and runs the CLI smoke check.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

CMD ["python", "-m", "marketlab"]
