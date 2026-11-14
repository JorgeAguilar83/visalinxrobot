#!/bin/bash

# ==========================================
# CONFIGURACIÓN DEL SERVIDOR (Edita estos datos)
# ==========================================
USER="adalinx_server_1"
HOST="192.168.1.50"
DEST_DIR="/home/adalinx_server_1/VisaLinx"
# ==========================================

echo "🚀 Iniciando despliegue hacia $HOST..."

# 1. Crear el directorio destino en el servidor si no existe
echo "📁 Verificando/Creando carpeta destino en el servidor ($DEST_DIR)..."
ssh $USER@$HOST "mkdir -p $DEST_DIR"

# 2. Transferir los archivos excluyendo archivos locales pesados o temporales
echo "⬆️ Transfiriendo código fuente..."
rsync -avz --exclude '.venv' \
           --exclude '__pycache__' \
           --exclude 'logs' \
           --exclude 'deploy.sh' \
           ./ $USER@$HOST:$DEST_DIR

echo "✅ ¡Despliegue completado con éxito!"
