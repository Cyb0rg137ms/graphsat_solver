FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY graphsat ./graphsat
RUN pip install --no-cache-dir .
ENTRYPOINT ["graphsat"]
CMD ["--help"]
