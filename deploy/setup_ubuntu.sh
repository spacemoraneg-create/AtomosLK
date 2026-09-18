#!/bin/bash
# ==============================================================================
# ATOMOS AUTOMATED UBUNTU / DEBIAN PRODUCTION SETUP SCRIPT
# Run as root or with sudo
# ==============================================================================

set -e

echo "[*] Updating apt package repository..."
apt-get update && apt-get upgrade -y

echo "[*] Installing Python 3, venv, Nginx, and Certbot..."
apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx curl git sqlite3

APP_DIR="/var/www/atomos"
echo "[*] Setting up application directory at $APP_DIR..."
mkdir -p $APP_DIR
chown -R www-data:www-data $APP_DIR

echo "[*] Copying application files..."
# Run this script from the root of your cloned repository
cp -r . $APP_DIR/
cd $APP_DIR

echo "[*] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[*] Setting permissions..."
chown -R www-data:www-data $APP_DIR
chmod -R 755 $APP_DIR
chmod -R 775 $APP_DIR/data

echo "[*] Installing systemd service..."
cp $APP_DIR/deploy/atomos.service /etc/systemd/system/atomos.service
systemctl daemon-reload
systemctl enable atomos
systemctl restart atomos

echo "[*] Configuring Nginx..."
cp $APP_DIR/deploy/nginx.conf /etc/nginx/sites-available/atomos
ln -sf /etc/nginx/sites-available/atomos /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

echo "=================================================================="
echo "  ATOMOS DEPLOYMENT COMPLETE!"
echo "  Check server status:  systemctl status atomos"
echo "  Check nginx status:   systemctl status nginx"
echo "  To configure SSL:     certbot --nginx -d yourdomain.com"
echo "=================================================================="
