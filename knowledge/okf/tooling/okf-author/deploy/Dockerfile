FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir uv && uv pip install --system -e .
# Write-only MCP server: HOST/PORT/GITHUB_* come from the env_file at runtime.
ENV HOST=0.0.0.0 \
    PORT=8016 \
    IDENTITY_HEADER=Cf-Access-Authenticated-User-Email
EXPOSE 8016
CMD ["okfauthor"]
