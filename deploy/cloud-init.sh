#!/bin/bash
# Paste this whole file into the "cloud-init script" box (Oracle Cloud) or "User data" box (DigitalOcean)
# when you create an Ubuntu server. It downloads OmniEducation and runs deploy/server-setup.sh.
# Progress is written to /var/log/omniedu-setup.log; the site is ready 10-20 minutes after the server starts.
exec > /var/log/omniedu-setup.log 2>&1
set -x
for i in 1 2 3 4 5; do apt-get update -q && apt-get install -y -q git && break; sleep 20; done
git clone https://github.com/Qacbuub/OmniEducation.git /opt/omniedu
bash /opt/omniedu/deploy/server-setup.sh
