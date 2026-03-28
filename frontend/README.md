# HostingGuard Frontend

Este es el frontend de la plataforma HostingGuard, construido con **React**, **Tailwind CSS** y **Framer Motion**.

## Requisitos
- Node.js (v18 o superior)
- Backend de HostingGuard en ejecución (puerto 8000 por defecto)

## Instalación

1. Entra en la carpeta del frontend:
   ```bash
   cd frontend
   ```

2. Instala las dependencias:
   ```bash
   npm install
   ```

## Desarrollo

Para iniciar el servidor de desarrollo:
```bash
npm run dev
```

El sitio estará disponible en `http://localhost:5173`.

## Características
- **Landing Page Premium**: Diseño inspirado en Vercel/Stripe.
- **Formulario de Creación**: Conectado directamente al endpoint `/create-hosting` del backend.
- **Responsive**: Optimizado para móviles y escritorio.
- **Glassmorphism**: UI moderna con efectos de desenfoque y neón.

## Configuración del API
El formulario apunta a `https://api.hostingguard.lat/create-hosting`. Si estás probando localmente, puedes cambiar esta URL en `src/App.jsx`.
