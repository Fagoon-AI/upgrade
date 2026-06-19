#!/bin/bash

# Ensure Nginx is installed (assuming it's a debian/ubuntu system)
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx

# Write Nginx config
cat << 'CONF' | sudo tee /etc/nginx/sites-available/fagoon.tech
server {
    listen 80;
    server_name fagoon.tech www.fagoon.tech;

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
CONF

sudo ln -sf /etc/nginx/sites-available/fagoon.tech /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# Install PM2 and launch the processes
sudo npm install -g pm2
cd /home/shekhar_adhikari747/.openclaw/workspace/upgrade-frontend
pm2 delete upgrade-frontend || true
PORT=3000 pm2 start "npm run start" --name "upgrade-frontend"

cd /home/shekhar_adhikari747/.openclaw/workspace/upgrade-utils
pm2 delete upgrade-backend || true
pm2 start "source venv/bin/activate && uvicorn launch_server:app --port 8000 --host 0.0.0.0" --name "upgrade-backend"

# Ensure PM2 saves and restores on reboot
pm2 save
sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u shekhar_adhikari747 --hp /home/shekhar_adhikari747

# Execute Certbot to get SSL certificates
sudo certbot --nginx -d fagoon.tech -d www.fagoon.tech --non-interactive --agree-tos -m admin@fagoon.ai
