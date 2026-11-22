# Stella · contador de personas para Google Coral

Stella cuenta las personas que **entran y salen** cruzando una línea, con una cámara y la **Coral Dev Board**:

- **Detección:** OpenCV con MOG2 para detectar movimiento, y SSD MobileNet v2 en el Edge TPU para detectar personas.
- **Registro:** guarda cada evento en SQLite.
- **Publicación:** lo envía por **MQTT** (con discovery de Home Assistant) y por **webhook**, y lo expone en una **API REST**.
- **Web:** interfaz para ver el vídeo en vivo, calibrar, configurar la red y actualizar el equipo.

El mismo código corre en el **PC** (detector en CPU, vídeo de archivo o webcam) cambiando solo la configuración.

## Estructura

```
stella/
  config.py          configuración YAML (valores por defecto, validación, secretos)
  pipeline.py        captura → MOG2 → detector → tracker → conteo
  video/source.py    cámara V4L2 / archivo (OpenCV)
  vision/            motion (MOG2), detector (TFLite + Edge TPU), tracker (IoU), counting (zona + línea)
  counters.py        totales del día, aforo, reinicio diario
  storage.py         SQLite: eventos y entregas pendientes
  outbox.py          entrega con reintentos a MQTT y webhook
  sinks/             mqtt.py, webhook.py
  hw/                leds.py (LED RGB por GPIO), system.py (temperatura, IP, reinicio)
  net/wifi.py        wifi, hotspot de respaldo y Ethernet con nmcli
  ota.py             actualizaciones por git con rollback
  web/               Flask: páginas, API /api/v1, vídeo MJPEG, SSE
deploy/              install.sh, unidades systemd, rollback.sh
models/              SSD MobileNet v2 COCO (Edge TPU y CPU)
tests/               pytest (+ run_py37.sh para probar con las versiones de la placa)
docs/coral-device.md ficha técnica de la placa
```

## Instalación en la placa

Requisitos: Mendel 5 (Python 3.7, `python3-pycoral`, `python3-tflite-runtime`), el usuario `mendel` con sudo sin contraseña y acceso a PyPI.

```bash
git clone <url-del-repo> /home/mendel/stella
```

```bash
cd /home/mendel/stella && ./deploy/install.sh
```

`install.sh` hace lo siguiente:
- Crea el venv `/home/mendel/stella-venv` con acceso a los paquetes del sistema, para seguir viendo `pycoral` y `tflite_runtime`. Instala ahí pip 24.0, OpenCV 4.11, numpy 1.21 y las demás dependencias de `requirements-board.txt`.
- Crea `/home/mendel/stella-data/config.yaml` a partir de `config.example.yaml`, con permisos 600. Si ya existe, no lo toca.
- Instala y arranca los servicios `stella.service` y `stella-rollback.service`.

Después abre `http://<ip-de-la-placa>:7777`. El usuario es **admin** y la contraseña inicial **stella**; la web pide cambiarla.

```bash
journalctl -u stella -f
```

## Desarrollo en el PC

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

Crea `data/config.yaml` con el perfil PC (ver `config.example.yaml`), por ejemplo:

```yaml
camera: {source: demo/entrada002.webm, width: 1280, height: 720, loop: true}
detector: {model: models/ssd_mobilenet_v2_coco_quant_postprocess.tflite, delegate: none}
leds: {driver: none}
network: {managed: false}
```

```bash
.venv/bin/python -m stella --config data/config.yaml
```

Para procesar solo el vídeo e imprimir los cruces, sin web:

```bash
.venv/bin/python -m stella --config data/config.yaml --headless
```

### Tests

```bash
.venv/bin/python -m pytest
```

Con Python 3.7 y las versiones exactas de la placa (requiere Docker):

```bash
./tests/run_py37.sh "slow or not slow"
```

MQTT contra un broker real:

```bash
docker run --rm -d -p 1883:1883 eclipse-mosquitto:2 mosquitto -c /mosquitto-no-auth.conf
```

```bash
STELLA_TEST_MQTT=localhost:1883 .venv/bin/python -m pytest tests/test_mqtt_broker.py
```

## Cómo cuenta

1. MOG2 vigila la **zona** (polígono). Solo cuando hay movimiento se ejecuta el detector, y se apaga tras `motion.idle_frames` imágenes sin personas.
2. Cada persona se sigue por solapamiento (IoU) entre imágenes.
3. Se toma el **punto de los pies** (centro inferior de la caja). Si una persona aparece a un lado de la **línea** y desaparece al otro, cuenta como **entrada** o **salida** según el sentido marcado con la flecha verde en la web.

## MQTT

`<p>` es el prefijo de tópico e `<id>` el identificador del dispositivo.

| Tópico | Contenido |
|---|---|
| `<p>/<id>/event` | un JSON por cruce (`uid`, `ts`, `direction` `in`/`out`, contadores) · QoS 1 |
| `<p>/<id>/counters` | `{"day", "in", "out", "occupancy", "limit", "full"}` · retenido |
| `<p>/<id>/status` | heartbeat: temperatura, IP, FPS, versión… · retenido |
| `<p>/<id>/availability` | `online` / `offline` (last will) |
| `<p>/<id>/cmd` | `reset_counters` o `{"command": "reset_counters", "occupancy": 0}`, `restart` |

Los eventos se entregan **al menos una vez**: si el broker o el webhook no responden, quedan en SQLite y se reintentan. Cada evento lleva un `uid` único para descartar duplicados.

## API REST

Autenticación con `Authorization: Bearer <token>`; el token se ve y se regenera en *Integraciones*.

| Método y ruta | Uso |
|---|---|
| `GET /api/v1/status` | estado general |
| `GET /api/v1/counters` · `POST /api/v1/counters/reset` | contadores |
| `GET /api/v1/events?since_id=&limit=` | historial de cruces |
| `GET /api/v1/config[/sección]` · `PUT /api/v1/config/<sección>` | configuración (los secretos salen enmascarados) |
| `GET /api/v1/stream` | SSE con detecciones y contadores en vivo |
| `GET /api/v1/network/status` | red: conexiones, IPs y nombre del equipo |
| `GET /api/v1/ota` · `POST /api/v1/ota/check` · `POST /api/v1/ota/apply` | actualizaciones |
| `POST /api/v1/system/restart` · `POST /api/v1/system/reboot` | reinicios |

## Actualizaciones (OTA)

En *Sistema* se configuran el repositorio git y la rama. «Buscar actualizaciones» hace `git fetch` y lista los cambios. «Instalar» mueve el clon a la versión nueva, reinstala dependencias si cambiaron y reinicia Stella.

Si la versión nueva falla 3 veces en 5 minutos, `stella-rollback.service` vuelve a la anterior. Si sigue funcionando pasados `ota.healthy_after` segundos (60), la actualización queda confirmada.

> El clon de la placa es solo para desplegar: la OTA descarta cualquier cambio local (`git reset --hard`). La configuración y los datos viven fuera del repo, en `stella-data/`.

## Red

Con `network.managed: true`, Stella gestiona NetworkManager:
- Crea una conexión `stella-wifi-<ssid>` por cada red del YAML, con su prioridad.
- Configura la Ethernet (DHCP o IP fija).
- Prepara el **hotspot de respaldo** (`StellaWIFI` por defecto, web en `http://10.42.0.1:7777`). Lo activa si pasan `hotspot.timeout` segundos sin conexión, y cada `retry_interval` segundos vuelve a probar las redes wifi guardadas (las de Stella y cualquier otra), salvo que alguien esté usando la web.
- Las conexiones USB gadget de la placa nunca se tocan.

### Configurar la wifi desde el hotspot

1. Conéctate a `StellaWIFI` (clave `stella1234`) y abre `http://10.42.0.1:7777`. Si el móvil avisa «sin internet», elige mantener la conexión y desactiva los datos móviles.
2. En *Red → Conectar a una red wifi*, escribe el nombre exacto de la red y su clave. Marca **Red oculta** si la red no anuncia su nombre. Pulsa **Guardar y conectar**.
3. La placa deja el hotspot y se une a esa red. Si no lo consigue en unos 45 segundos, vuelve a crear `StellaWIFI`.

No se buscan redes: con la wifi funcionando como punto de acceso, el chip no puede escanear.

### ¿Qué IP tiene la placa?

Con wifi o con cable Ethernet (DHCP del router), estas son las formas de encontrarla:

- **Por nombre:** `http://<hostname>.local:7777`, por ejemplo `http://mocha-rabbit.local:7777`. La placa se anuncia por mDNS (avahi). Funciona en Windows 10+, macOS y Linux; en Android depende del navegador.
- **Por cable USB:** `http://192.168.200.2:7777`. La página *Red* muestra la IP de cada interfaz.
- **En el router:** en la lista de clientes DHCP aparece con el nombre de la placa.
- **Por MQTT:** el tópico `<prefijo>/<id>/status` incluye las IPs.
- Si necesitas una IP fija por cable, configúrala en *Red → Ethernet → IP fija*.
- Stella usa `nmcli` sin `sudo`: el usuario `mendel` pertenece al grupo `netdev`, y polkit le da los permisos necesarios.

### Red USB

Mendel trae por defecto la interfaz USB en `192.168.100.2/24`. Si la red local también es `192.168.100.0/24`, la placa responde a la LAN por el cable USB y, sin el cable, parece que no tiene red. Por eso `install.sh` ejecuta `deploy/usb-subnet.sh`, que mueve la interfaz USB a **`192.168.200.2`** (y `usb1` a `192.168.201.2`) en NetworkManager y en el DHCP de dnsmasq. Por cable USB la placa queda en:

```bash
ssh mendel@192.168.200.2
```

## Restaurar fábrica

En *Sistema → Acciones → Restaurar fábrica* (hay que escribir `RESTAURAR` para confirmar), o por SSH:

```bash
sudo systemctl stop stella
```

```bash
cd /home/mendel/stella && /home/mendel/stella-venv/bin/python -m stella --config /home/mendel/stella-data/config.yaml --factory-reset
```

Hay que lanzarlo **desde la carpeta del repo**: desde `/home/mendel`, Python toma la carpeta `stella/` del clon como paquete y falla.

```bash
sudo systemctl start stella
```

Qué hace:
- Borra **todas** las conexiones wifi de NetworkManager, también las creadas fuera de Stella. No toca USB ni Ethernet.
- Borra `events.db` (historial, contadores y envíos pendientes).
- Sustituye `config.yaml` por `stella-data/factory.yaml` si existe; si no, por `config.example.yaml`. El usuario y la contraseña vuelven a `admin` / `stella`, y se genera un token nuevo.

Sin ninguna red conocida, a los 90 segundos aparece el hotspot **StellaWIFI** (clave `stella1234`). La web queda en `http://10.42.0.1:7777`, y desde *Red* se añade la wifi definitiva.

## LED RGB

| Color | Significado |
|---|---|
| destello verde | entrada |
| destello amarillo | salida |
| rojo | error de cámara o detector, o aforo completo |
| violeta | hotspot activo |
| azul | sin red |
| apagado | funcionamiento normal |

Conexión en el conector de 40 pines: **rojo = GPIO_P18** (`gpio138`), **verde = GPIO_P13** (`gpio6`), **azul = GPIO_P16** (`gpio73`).
El LED de la caja es de **ánodo común** (`leds.active_level: 0`): un color se enciende cuando su pin está a 0 V.
Si en reposo el LED queda blanco, el tipo está invertido: cámbialo en *Sistema → LED RGB → Tipo de LED*.

Los colores se pueden cambiar en *Sistema*.
