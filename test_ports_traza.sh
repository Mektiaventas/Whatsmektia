#!/bin/bash
# test_ports_traza.sh
# Prueba puertos TCP y muestra si el firewall local acepta o bloquea

HOST="mektia.com"
PUERTOS=(22 80 443 5000 8080 3306)

echo "==== Prueba de puertos con trazabilidad ===="
for PUERTO in "${PUERTOS[@]}"; do
    echo -n "Probando puerto $PUERTO ... "
    
    # Usamos timeout para no quedarnos pegados si no responde
    nc -z -v -w3 $HOST $PUERTO &> /tmp/nc_result.txt
    RESULT=$(cat /tmp/nc_result.txt)
    
    if grep -q "succeeded" /tmp/nc_result.txt; then
        echo "✅ Abierto / aceptado"
    elif grep -q "refused" /tmp/nc_result.txt; then
        echo "❌ Cerrado / rechazado"
    elif grep -q "timed out" /tmp/nc_result.txt; then
        echo "⚠️ No llega / filtrado (posible firewall ISP o UFW)"
    else
        echo "❓ Resultado desconocido"
    fi
done

# Limpieza
rm /tmp/nc_result.txt
echo "==== Fin de la prueba ===="
