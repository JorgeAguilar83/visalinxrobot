#!/bin/bash

LOCAL_PORT="5435"

echo "Buscando procesos del túnel SSH en puerto ${LOCAL_PORT}..."
PID=$(pgrep -f "ssh.*${LOCAL_PORT}:127.0.0.1:5433" || true)

if [ -n "$PID" ]; then
    echo "Deteniendo túnel SSH (PID: $PID)..."
    kill $PID
    echo "✅ Túnel cerrado y puerto ${LOCAL_PORT} liberado."
else
    echo "ℹ️  No hay ningún túnel SSH activo en el puerto ${LOCAL_PORT}."
fi
