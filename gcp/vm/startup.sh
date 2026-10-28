#!/bin/bash
# Runs as root on first boot: 2 GB swap (the free e2-micro has 1 GB RAM) and Docker. Marker file when done.
set -e
if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile; chmod 600 /swapfile; mkswap /swapfile; swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
touch /var/lib/smsgate-ready
