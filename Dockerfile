ARG BASE_IMAGE=python
ARG BASE_IMAGE_TAG=3-slim-bookworm
ARG UID=0
ARG GID=0

FROM $BASE_IMAGE:$BASE_IMAGE_TAG

# copy cert-files
ADD root.pem #[.....]
ADD sub.pem #[.....]


ENV http_proxy=#[.....]
ENV HTTP_PROXY=$http_proxy
ENV https_proxy=$http_proxy
ENV HTTPS_PROXY=$http_proxy
ENV no_proxy=#[.....]
ENV NO_PROXY=$no_proxy
ENV REQUESTS_CA_BUNDLE=#[.....]

# Default to UTF-8 file.encoding and de_CH locale
ENV LANG=de_CH.UTF-8
ENV LANGUAGE=de_CH:en
ENV LC_ALL=de_CH.UTF-8

# timezone setting
ENV TZ=Europe/Zurich

# install certificates into local cert store
USER root:root
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates locales && \
    cp #[.....] /usr/local/#[.....] && \
    cp #[.....] /usr/local/#[.....] && \
    sed -i -e 's/# de_CH.UTF-8 UTF-8/de_CH.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=de_CH.UTF-8 && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app/

# Install system dependencies if needed
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and install dependencies
COPY pyproject.toml .
COPY uv.lock .

# Install uv for faster dependency installation
RUN pip install --no-cache-dir uv

# Install project dependencies using uv
#RUN uv pip install --system --no-cache -r pyproject.toml
RUN uv sync

# Copy application code
COPY *.py ./

# Create outputs directory and set permissions
RUN mkdir -p /app/outputs && \
    useradd -m -u #[.....] #[.....] && \
    chown -R #[.....]:#[.....] /app

# Switch to non-root user
USER #[.....]:#[.....]

# Run the application
CMD ["uv", "run", "main.py"]