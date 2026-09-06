FROM python:3.10-bookworm

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1-dev \
    libfftw3-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Try to install Chordino Vamp plugin (nnls-chroma)
# This is best-effort — the app falls back to chromagram if unavailable
RUN apt-get update && apt-get install -y --no-install-recommends \
    vamp-plugin-sdk \
    libvamp-hostsdk3v5 \
    && rm -rf /var/lib/apt/lists/* || true

# Try downloading pre-compiled nnls-chroma (Chordino) plugin for Linux x86_64
RUN mkdir -p /usr/local/lib/vamp && \
    curl -fsSL --connect-timeout 10 --max-time 60 \
    'https://code.soundsoftware.ac.uk/attachments/download/2625/nnls-chroma-1.1-linux64.tar.gz' \
    -o /tmp/nnls-chroma.tar.gz && \
    tar xzf /tmp/nnls-chroma.tar.gz -C /tmp && \
    find /tmp -name '*.so' -exec cp {} /usr/local/lib/vamp/ \; && \
    rm -rf /tmp/nnls-chroma* \
    || echo '>>> Chordino plugin download failed; chromagram fallback will be used.'

ENV VAMP_PATH=/usr/local/lib/vamp

WORKDIR /app

# Install Python dependencies, including the melody analyzer extra.
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e '.[dev,melody]'

# Optional CPU-only vocal isolation. Disabled by default to keep the base image small.
ARG INSTALL_SEPARATION=false
RUN if [ "$INSTALL_SEPARATION" = "true" ]; then \
      pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -e '.[separation]'; \
    fi

# Copy application code
COPY . .

CMD ["python", "-m", "pytest", "tests/", "-v"]
