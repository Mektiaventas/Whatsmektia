#!/bin/bash
DOMAIN="mektia.com"

echo "==== 1️⃣ Comprobando DNS ===="
dig +short $DOMAIN
dig +short www.$DOMAIN

echo -e "\n==== 2️⃣ Probando puertos TCP (80 y 443) ===="
nc -zv $DOMAIN 80
nc -zv $DOMAIN 443

echo -e "\n==== 3️⃣ Probando HTTP/HTTPS ===="
echo "HTTP:"
curl -I http://$DOMAIN
echo -e "\nHTTPS:"
curl -I https://$DOMAIN

echo -e "\n==== 4️⃣ Comprobando Nginx status ===="
sudo systemctl status nginx | grep Active
