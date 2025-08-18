#!/bin/bash

DOMAIN="mektia.com"

echo "==== 1 ️⃣  Comprobando DNS ===="
DNS_MAIN=$(dig +short $DOMAIN)
DNS_WWW=$(dig +short www.$DOMAIN)

echo "mektia.com → $DNS_MAIN"
echo "www.mektia.com → $DNS_WWW"

if [[ -z "$DNS_MAIN" || -z "$DNS_WWW" ]]; then
    echo "❌ Error: DNS no resuelve correctamente."
else
    echo "✅ DNS resuelve correctamente."
fi

echo -e "\n==== 2 ️⃣ Probando puertos TCP (80 y 443) ===="
check_port() {
    local PORT=$1
    timeout 3 bash -c "echo > /dev/tcp/$DOMAIN/$PORT" &>/dev/null
    if [[ $? -eq 0 ]]; then
        echo "✅ Puerto $PORT abierto"
    else
        echo "❌ Puerto $PORT cerrado o filtrado (firewall / proveedor ISP)"
    fi
}

check_port 80
check_port 443

echo -e "\n==== 3 ️⃣ Probando HTTP/HTTPS ===="
check_http() {
    local PROTO=$1
    RESPONSE=$(curl -Is --max-time 5 $PROTO://$DOMAIN | head -n 1)
    if [[ $RESPONSE == *"200"* || $RESPONSE == *"301"* || $RESPONSE == *"302"* ]]; then
        echo "✅ $PROTO funciona: $RESPONSE"
    else
        echo "❌ $PROTO no responde o hay error: $RESPONSE"
    fi
}

check_http http
check_http https

echo -e "\n==== 4 ️⃣ Comprobando Nginx status ===="
NGINX_STATUS=$(systemctl is-active nginx)
if [[ "$NGINX_STATUS" == "active" ]]; then
    echo "✅ Nginx activo"
else
    echo "❌ Nginx inactivo o con error"
fi

echo -e "\n==== 5️⃣ Comprobación final ===="
echo "DNS: $DNS_MAIN / $DNS_WWW"
echo "Nginx: $NGINX_STATUS"
echo "Puertos 80 y 443: revisa los mensajes anteriores"
