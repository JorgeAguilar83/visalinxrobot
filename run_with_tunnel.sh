#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

VPS_HOST="191.101.0.80"
VPS_USER="root"
REMOTE_PORT="5433"
LOCAL_PORT="5435"

echo "============================================================"
echo "🛡️  VISALINX ROBOT - INICIALIZADOR DE CONEXIÓN CON VPS"
echo "============================================================"

# Función para verificar si el túnel ya está respondiendo
check_tunnel() {
    "$DIR/.venv/bin/python" -c "import socket; s = socket.socket(); s.settimeout(1); exit(0 if s.connect_ex(('127.0.0.1', $LOCAL_PORT)) == 0 else 1)" 2>/dev/null
}

if check_tunnel; then
    echo "✅ El túnel seguro en el puerto ${LOCAL_PORT} ya está activo."
else
    echo "📡 Abriendo túnel SSH cifrado hacia ${VPS_USER}@${VPS_HOST}:${REMOTE_PORT}..."
    ssh -f -N -L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT} \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        ${VPS_USER}@${VPS_HOST}
    
    # Esperar confirmación de apertura
    sleep 1
    if check_tunnel; then
        echo "✅ Túnel SSH establecido exitosamente en 127.0.0.1:${LOCAL_PORT}."
    else
        echo "❌ Error al iniciar el túnel SSH. Verifica tu conexión o acceso al servidor."
        exit 1
    fi
fi

echo "🚀 Lanzando Robot VisaLinx..."
echo "============================================================"
exec "$DIR/.venv/bin/python" "$DIR/main.py" "$@"
