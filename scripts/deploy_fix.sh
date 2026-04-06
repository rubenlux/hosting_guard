#!/bin/bash
# deploy_fix.sh — Emergency fix para login 500 + route conflict
# Ejecutar en el servidor: bash /tmp/deploy_fix.sh

set -e
cd /opt/hosting_guard 2>/dev/null || cd ~/hosting_guard 2>/dev/null || { echo "ERROR: No se encuentra el directorio del proyecto"; exit 1; }

echo "=== [1/4] Git pull ==="
git pull origin main --rebase

echo "=== [2/4] Build imagen Docker ==="
docker compose build app

echo "=== [3/4] Reiniciar servicio ==="
docker compose up -d app

echo "=== [4/4] Verificar login ==="
sleep 5
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST https://api.hostingguard.lat/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@notexists.com","password":"wrong"}')

if [ "$STATUS" = "401" ]; then
  echo "✅ Login OK — devuelve 401 (credenciales incorrectas, no 500)"
elif [ "$STATUS" = "500" ]; then
  echo "❌ SIGUE dando 500 — revisar logs: docker compose logs app --tail=50"
else
  echo "⚠️  Status: $STATUS"
fi

echo ""
echo "=== Logs recientes ==="
docker compose logs app --tail=30
