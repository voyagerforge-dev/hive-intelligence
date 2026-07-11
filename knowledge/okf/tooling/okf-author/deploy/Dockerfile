FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir uv && uv pip install --system -e .
EXPOSE 8000
CMD ["okfauthor"]
