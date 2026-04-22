# Cloudflare Tunnel — IntecsaRAG Beta

Expone el frontend (Next.js, puerto 3000) a internet sin cuenta, sin dominio y sin abrir puertos.
El backend (FastAPI, puerto 8000) **nunca** es accesible directamente; las peticiones `/api/*` llegan al frontend y Next.js las reescribe internamente a `localhost:8000`.

---

## Opción A — Quick tunnel (sin cuenta, sin dominio, gratis)

La forma más rápida. No necesitas nada más que `cloudflared` instalado.

```bash
cloudflared tunnel --url http://localhost:3000
```

En la salida aparece una URL pública del tipo:

```
https://random-words-here.trycloudflare.com
```

Compártela con el tribunal. Mientras el proceso esté corriendo, la URL funciona.

**Limitación:** la URL cambia cada vez que arrancas el tunnel. Para la defensa no importa — la anotas una vez y listo.

### Instalar cloudflared (si no lo tienes)

```bash
# Debian/Ubuntu
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Verificar
cloudflared --version
```

---

## Opción B — Tunnel con cuenta Cloudflare + dominio propio

Solo necesaria si quieres una URL fija entre sesiones. Requiere dominio (puede ser gratuito en [Freenom](https://www.freenom.com) o cualquier registrar) y una cuenta Cloudflare gratuita.

<details>
<summary>Ver instrucciones</summary>

### 1. Autenticarse

```bash
cloudflared tunnel login
```

### 2. Crear el tunnel

```bash
cloudflared tunnel create intecsarag-beta
```

Anota el TUNNEL_ID (UUID) que aparece.

### 3. Editar `cloudflare/config.yml`

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/maria/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: rag.tudominio.com
    service: http://localhost:3000
  - service: http_status:404
```

### 4. Crear el registro DNS

```bash
cloudflared tunnel route dns intecsarag-beta rag.tudominio.com
```

### 5. Arrancar

```bash
cloudflared tunnel --config cloudflare/config.yml run
```

</details>

---

## Servicio systemd (para que el tunnel no se caiga en la defensa)

Ejecutar `cloudflared` en un terminal tiene tres riesgos durante una defensa:
- El portátil se suspende → el tunnel cae.
- Se cierra accidentalmente el terminal.
- Pierdes la WiFi → el tunnel cae y no se reconecta.

Con systemd el proceso se reinicia solo y no depende de ningún terminal.

### Para el quick tunnel (Opción A)

Crea el fichero del servicio:

```bash
sudo tee /etc/systemd/system/cloudflared-quick.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Quick Tunnel — IntecsaRAG
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=maria
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:3000
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
```

Actívalo:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cloudflared-quick
sudo systemctl start cloudflared-quick
```

Ver la URL que generó:

```bash
sudo journalctl -u cloudflared-quick --no-pager | grep "trycloudflare.com"
```

### Para el tunnel con cuenta (Opción B)

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

---

## Checklist para el día de la defensa

- [ ] `sudo systemctl status cloudflared-quick` → `active (running)`.
- [ ] URL anotada: `sudo journalctl -u cloudflared-quick --no-pager | grep "trycloudflare.com"`
- [ ] El frontend corre en puerto 3000.
- [ ] El backend corre en puerto 8000.
- [ ] Abre la URL desde el móvil para confirmar que carga el login.
- [ ] Ten la URL anotada en papel.

---

## Arquitectura de red

```
Internet → Cloudflare CDN → cloudflared (tunnel) → localhost:3000 (Next.js)
                                                          ↓ rewrite /api/*
                                                    localhost:8000 (FastAPI)
```

El backend **nunca** recibe tráfico directo de internet.
