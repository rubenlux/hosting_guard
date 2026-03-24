#!/bin/bash

# --- CONFIGURACIÓN DE SERVIDOR PARA HOSTING GUARD ---
# Este script instala Docker y configura el entorno inicial.

set -e # Detener si algo falla

echo "🛡️  Iniciando configuración del servidor Hosting Guard..."

# 1. Actualizar sistema e instalar Docker
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Agregar llave oficial de Docker si no existe
if [ ! -f /usr/share/keyrings/docker-archive-keyring.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
fi

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 2. Configurar variables de entorno iniciales
if [ ! -f .env.production ]; then
    echo "📄 Creando archivo .env.production desde el ejemplo..."
    cp .env.production.example .env.production
    echo "⚠️  ¡ATENCIÓN! Edita .env.production con tus API Keys reales antes de arrancar."
fi

# 3. Crear backups de bases de datos existentes
if [ -f audit_events.sqlite ]; then
    cp audit_events.sqlite audit_events.sqlite.bak
fi

echo "✅ Configuración base completada."
echo "👉 Ejecuta 'docker compose up -d' para iniciar los servicios."
