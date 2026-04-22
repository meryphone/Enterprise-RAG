# Cloudflare Tunnel — IntecsaRAG Beta

Expone el frontend (Next.js, puerto 3000) a internet sin abrir puertos en el router.
El backend (FastAPI, puerto 8000) **nunca** es accesible directamente; las peticiones `/api/*` llegan al frontend y Next.js las reescribe internamente a `localhost:8000`.

---

## Requisitos

- `cloudflared` instalado: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
- Cuenta Cloudflare con un dominio bajo tu control (o subdominio de `trycloudflare.com` para pruebas rápidas sin cuenta).

```bash
# Verificar instalación
cloudflared --version
```

---

## Configuración inicial (una sola vez)

### 1. Autenticarse en Cloudflare

```bash
cloudflared tunnel login
```

Se abrirá el navegador. Elige el dominio que quieres usar. Esto crea `~/.cloudflared/cert.pem`.

### 2. Crear el tunnel

```bash
cloudflared tunnel create intecsarag-beta
```

Anota el **TUNNEL_ID** (UUID) que aparece en la salida. Crea el fichero de credenciales en `~/.cloudflared/<TUNNEL_ID>.json`.

### 3. Editar `cloudflare/config.yml`

Sustituye los dos placeholders:

```yaml
tunnel: <TUNNEL_ID>                              # UUID del paso anterior
credentials-file: /home/maria/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: rag.tudominio.com                  # subdominio que vas a usar
    service: http://localhost:3000
  - service: http_status:404
```

### 4. Crear el registro DNS

```bash
cloudflared tunnel route dns intecsarag-beta rag.tudominio.com
```

Esto añade un registro CNAME en Cloudflare apuntando al tunnel.

### 5. Probar manualmente

Asegúrate de que el frontend esté corriendo (`npm run dev` en `frontend/`) y ejecuta:

```bash
cloudflared tunnel --config cloudflare/config.yml run
```

Abre `https://rag.tudominio.com` en el navegador. Si carga el login, todo está bien. Interrumpe con Ctrl+C.

---

## Servicio systemd (recomendado para la defensa del TFG)

Ejecutar `cloudflared` en un terminal manual tiene tres riesgos durante una defensa:
- El portátil se suspende → el tunnel cae.
- Se cierra accidentalmente el terminal.
- Se pierde la WiFi → el tunnel cae y no se reconecta automáticamente.

El servicio systemd resuelve los tres: se inicia con el sistema, se reinicia solo si cae, y no depende de ningún terminal abierto.

### Instalar el servicio

```bash
# Copiar el config al directorio estándar de cloudflared
sudo mkdir -p /etc/cloudflared
sudo cp cloudflare/config.yml /etc/cloudflared/config.yml

# Editar /etc/cloudflared/config.yml para usar rutas absolutas si es necesario
# credentials-file: /home/maria/.cloudflared/<TUNNEL_ID>.json  ← ya es absoluta

# Instalar como servicio del sistema
sudo cloudflared service install
```

Esto crea `/etc/systemd/system/cloudflared.service` automáticamente.

### Gestión del servicio

```bash
# Arrancar
sudo systemctl start cloudflared

# Parar
sudo systemctl stop cloudflared

# Activar inicio automático al arrancar el sistema
sudo systemctl enable cloudflared

# Ver estado
sudo systemctl status cloudflared

# Ver logs en tiempo real
sudo journalctl -u cloudflared -f
```

### Verificar que el tunnel está activo

```bash
cloudflared tunnel info intecsarag-beta
```

La salida muestra las conexiones activas y los data centers Cloudflare conectados.

---

## Checklist para el día de la defensa

- [ ] El portátil está enchufado (suspensión desactivada).
- [ ] `sudo systemctl status cloudflared` → `active (running)`.
- [ ] El frontend corre: `cd frontend && npm run dev` (o está levantado como servicio).
- [ ] El backend corre: `cd backend && uvicorn app.main:app --port 8000`.
- [ ] Abre `https://rag.tudominio.com/login` desde otro dispositivo (móvil) para confirmar.
- [ ] Ten la URL anotada en papel por si el navegador pierde el historial.

---

## Arquitectura de red

```
Internet → Cloudflare CDN → cloudflared (tunnel) → localhost:3000 (Next.js)
                                                          ↓ rewrite /api/*
                                                    localhost:8000 (FastAPI)
```

El backend **nunca** recibe tráfico directo de internet. Solo recibe peticiones desde el proceso Next.js en la misma máquina.

---

## Variables de entorno necesarias

El backend necesita `CLOUDFLARE_ORIGIN` para permitir CORS desde el dominio público:

```bash
# En backend/.env
CLOUDFLARE_ORIGIN=https://rag.tudominio.com
```

Reinicia el backend tras añadirla.
