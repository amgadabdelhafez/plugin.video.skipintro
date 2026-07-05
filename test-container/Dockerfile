FROM ubuntu:22.04

ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        gpg \
        gpg-agent \
    && add-apt-repository -y ppa:team-xbmc/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        kodi \
        ffmpeg \
        python3 \
        sqlite3 \
        xvfb \
        smbclient \
        libsmbclient \
        tzdata \
        libgl1-mesa-dri \
        libglu1-mesa \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV KODI_DATA=/root/.kodi
ENV DISPLAY=:99

# Create directory structure
RUN mkdir -p ${KODI_DATA}/addons/plugin.video.skipintro \
             ${KODI_DATA}/userdata/addon_data/plugin.video.skipintro \
             ${KODI_DATA}/userdata \
             /media

VOLUME /addon

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Kodi web interface + JSON-RPC
EXPOSE 8080 9090

ENTRYPOINT ["/entrypoint.sh"]
