# Guía de Despliegue - Hosting Guard 🛡️🚀

Esta guía detalla cómo desplegar la aplicación en un entorno de producción (o simulación de producción) usando Docker.

---

## 🛠️ Requisitos Previos
1. Servidor Linux (Ubuntu 20.04/22.04 recomendado).
2. Git.
3. API Keys de OpenAI o Anthropic (Claude).

---

## 🏗️ Fase 1: Preparación del Servidor
1. Clona el repositorio:
   ```bash
   git clone https://github.com/rubenlux/hosting_guard.git
   cd hosting_guard
   ```
2. Ejecuta el script de configuración inicial (Instala Docker si no está):
   ```bash
   chmod +x setup-server.sh
   ./setup-server.sh
   ```

---

## 🔑 Fase 2: Configuración de Secretos
1. Edita el archivo `.env.production` que se generó en el paso anterior:
   ```bash
   nano .env.production
   ```
2. Asegúrate de configurar:
   - `OPENAI_API_KEY` y/o `CLAUDE_API_KEY`.
   - `SECRET_KEY` (Genera una cadena aleatoria).
   - `ENABLE_AI_ADVISORY=true`.

---

## 🚀 Fase 3: Despliegue
1. Construye e inicia los contenedores:
   ```bash
   docker compose up -d --build
   ```
2. Verifica que los servicios estén corriendo:
   ```bash
   docker compose ps
   ```

---

## 📊 Fase 4: Monitoreo
- **Métricas**: Accede a Prometheus en `http://tu-ip-servidor:9090`.
- **API**: La aplicación estará disponible en `http://tu-ip-servidor:8000`.
- **Salud**: Puedes consultar el endpoint `/metrics` de la app directamente.

---

## 🔄 Actualización
Para subir cambios nuevos del repositorio:
```bash
git pull origin main
docker compose up -d --build
```
