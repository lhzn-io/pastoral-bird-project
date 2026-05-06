# Use a lightweight python image
FROM python:3.12-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (frozen to ensure lockfile is respected)
RUN uv sync --frozen --no-dev

# Copy the rest of the application
COPY . .

# Expose the Streamlit port
EXPOSE 8501

# Run the application using uv
CMD ["uv", "run", "streamlit", "run", "src/admin_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
