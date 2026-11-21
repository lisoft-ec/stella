# Ficha técnica: placa Google Coral (hostname `mocha-rabbit`)

Datos medidos en la placa el 2026-11-21. Lo que no aparece aquí no se ha medido.

## 1. Sistema

| Dato | Valor |
|---|---|
| Placa (`/proc/device-tree/model`) | Freescale i.MX8MQ Phanbell |
| Sistema | Mendel GNU/Linux 5 (Eagle), `ID=mendel`, `ID_LIKE=debian`, `VERSION_CODENAME=eagle` |
| Versión de Mendel (`/etc/mendel_version`) | 5.3 |
| `/etc/debian_version` | 10.0 |
| Kernel (`uname -a`) | `Linux mocha-rabbit 4.14.98-imx #1 SMP PREEMPT Tue Nov 2 02:55:21 UTC 2021 aarch64` |
| Paquetes de Mendel | `base-files` 10.3+mendel5.3 · `mendel-core` 2-1 · `mendel-minimal` 8-5 · `mendel-keyring` 3-3 · `mendel-distro-info-data` 4-1 · `linux-image-4.14.98-imx` 12-4 |
| Arquitectura | aarch64 (paquetes `arm64`) |
| Usuario | `mendel` |
| Reloj (`timedatectl`) | UTC, `System clock synchronized: yes`, servicio NTP activo, RTC presente (en UTC) |

## 2. Hardware

| Componente | Dato |
|---|---|
| CPU | 4 núcleos ARM Cortex-A53 (r0p4), 1 socket, 1 hilo por núcleo, 500 a 1500 MHz |
| Flags de CPU | `fp asimd evtstrm aes pmull sha1 sha2 crc32 cpuid` |
| RAM | 985 MB totales, sin swap |
| Almacenamiento | eMMC `mmcblk0` de 7,3 GB: `/boot` 128 MB · `/` 5,1 GB (5,0 GB útiles, 1,3 GB usados, 3,5 GB libres) · `/home` 2 GB (partición aparte) |
| Edge TPU | PCI, `/dev/apex_0` (`edgetpu.list_edge_tpus()` devuelve `[{'type': 'pci', 'path': '/dev/apex_0'}]`) |
| Módulos del kernel del Edge TPU | `apex` (24576 bytes) y `gasket` (98304 bytes, usado por `apex`) |
| Sensor de cámara | OV5645 (`ov5645_mipi`), MIPI-CSI de 2 carriles, dirección I2C `1-003c` (el kernel registra `camera ov5645_mipi is found`) |
| Dispositivo de video | `/dev/video0` (nombre `mx6s-csi`), único dispositivo de video |
| Formato de captura | solo YUYV (`YUY2` en GStreamer) |

Resoluciones de `/dev/video0` (todas YUYV):

| Resolución | FPS |
|---|---|
| 640x480 | 30 |
| 720x480 | 30 |
| 1280x720 | 30 |
| 1920x1080 | 15 y 30 |
| 2592x1944 | 15 |

## 3. Red

| Interfaz | Estado | Dirección |
|---|---|---|
| `wlan0` | UP | 192.168.100.81/24 |
| `usb0` | UP | 192.168.100.2/24 |
| `usb1` | DOWN | 192.168.101.2/24 |
| `eth0`, `p2p0` | DOWN | sin dirección |

Rutas: `default via 192.168.100.1 dev wlan0` (metric 600). `192.168.100.0/24` está en `usb0` (metric 100) y en `wlan0` (metric 600).

Acceso medido desde la placa (`curl -sI`): `https://github.com` HTTP 200 · `https://raw.githubusercontent.com` HTTP 301 · `https://pypi.org/simple/pip/` HTTP 200.

## 4. Repositorios apt

`/etc/apt/sources.list` no existe. La configuración está en `/etc/apt/sources.list.d/`:

| Archivo | Línea | Estado |
|---|---|---|
| `00-mdt-services.list` | `deb [trusted=yes] file:///var/cache/mdt/packages ./` | activa |
| `multistrap-main.list` | `deb [arch=arm64] https://mendel-linux.org/apt/eagle eagle main` | comentada |
| `multistrap-bsp.list` | `deb [arch=arm64] https://mendel-linux.org/apt/eagle-bsp-enterprise eagle main` | comentada |
| `multistrap-main_backup.list` | `deb [arch=arm64] https://packages.cloud.google.com/apt mendel-eagle main` | comentada |
| `multistrap-bsp_backup.list` | `deb [arch=arm64] https://packages.cloud.google.com/apt mendel-eagle-bsp-enterprise main` | comentada |
| `multistrap-edgetpu.list` | `deb [arch=arm64] https://packages.cloud.google.com/apt coral-edgetpu-stable main` | comentada |

**Por qué están comentadas.** `apt-get update` fallaba con estos errores:

- `packages.cloud.google.com`: `404 Not Found` en el archivo `Release` de `mendel-eagle`, `mendel-eagle-bsp-enterprise` y `coral-edgetpu-stable`, y `E: The repository '...' does not have a Release file` para las tres. El servidor respondió por HTTPS, así que la conexión y los certificados funcionaban.
- `mendel-linux.org`: `Temporary failure resolving 'mendel-linux.org'` para `eagle` y `eagle-bsp-enterprise`. En la misma sesión `ping archive.debian.org` resolvió el nombre y recibió respuesta.

El 2026-11-21 se antepuso `# ` a las líneas que contienen `packages.cloud.google.com` o `mendel-linux.org`, para que `apt-get update` termine sin errores. Después del cambio, las últimas 5 líneas de `apt-get update` solo muestran el repositorio local (mensajes `Ign`) y ningún error.

**Estado actual:** no hay ninguna fuente remota configurada (ni de Mendel, ni de Coral, ni de Debian).

Claves presentes: `/etc/apt/trusted.gpg.d/debian-archive-buster-automatic.gpg`, `debian-archive-buster-security-automatic.gpg` y `debian-archive-buster-stable.gpg`; paquete `mendel-keyring` 3-3.

## 5. Python y herramientas

| Componente | Versión |
|---|---|
| Python | 3.7.3 (`/usr/bin/python3` → `python3.7`; también `python3.7m`) |
| pip | 18.1 |
| git | 2.20.1 |
| `v4l-utils` (`v4l2-ctl`) | 1.16.3-3 |
| GStreamer (`Gst.version_string()`) | 1.14.4 |

- OpenCV (`cv2`): **no instalado** (`ModuleNotFoundError`).
- `gst-inspect-1.0`: **no instalado** (comando no encontrado).
- `curl` disponible.

Paquetes de Python (`pip3 list`):

| Paquete | Versión | Paquete | Versión |
|---|---|---|---|
| certifi | 2018.8.24 | PyOpenGL | 3.1.0 |
| chardet | 3.0.4 | pyserial | 3.4 |
| distro-info | 0.21 | PySimpleSOAP | 1.16.2 |
| edgetpuvision | 7.0 | python-apt | 1.8.4.3 |
| httplib2 | 0.11.3 | python-debian | 0.1.35 |
| idna | 2.6 | python-debianbts | 2.8.2 |
| netifaces | 0.10.4 | reportbug | 7.5.3-deb10u1 |
| numpy | 1.16.2 | requests | 2.21.0 |
| Pillow | 5.4.1 | setuptools | 40.8.0 |
| pip | 18.1 | six | 1.12.0 |
| protobuf | 3.6.1 | tflite-runtime | 2.5.0.post1 |
| pycairo | 1.16.2 | unattended-upgrades | 0.1 |
| pycoral | 2.0.0 | urllib3 | 1.24.1 |
| pycurl | 7.43.0.2 | vitalsd | 1.0 |
| PyGObject | 3.30.4 | wheel | 0.32.3 |
| PyJWT | 1.7.0 | | |

`edgetpuvision` figura como 7.0 en `pip3 list` y como `python3-edgetpuvision` 8-1 en `dpkg`.

## 6. Paquetes instalados (`dpkg-query`)

| Paquete | Versión |
|---|---|
| `libedgetpu1-std` | 16.0 |
| `python3-pycoral` | 2.0.0 |
| `python3-tflite-runtime` | 2.5.0.post1 |
| `python3-edgetpuvision` | 8-1 |
| `edgetpudemo` | 4-1 |
| `python3-gi` | 3.30.4-1 |
| `python3-gi-cairo` | 3.30.4-1 |
| `gir1.2-gstreamer-1.0` | 1.14.4-1 |
| `gir1.2-gst-plugins-base-1.0` | 1.14.4-2 |
| `gstreamer1.0-python3-plugin-loader` | 1.14.4-1+b1 |
| `gstreamer1.0-gl` | 1.14.4+imx-6 |
| `gstreamer1.0-plugins-base` | 1.14.4+imx-6 |
| `gstreamer1.0-plugins-good` | 1.14.4+imx-5 |
| `gstreamer1.0-plugins-bad` | 1.14.4+imx-7 |
| `gstreamer1.0-plugins-ugly` | 1.14.4-1 |
| `libgstreamer1.0-0` | 1.14.4+imx-3 |
| `libgstreamer-gl1.0-0` | 1.14.4+imx-6 |
| `libgstreamer-plugins-base1.0-0` | 1.14.4+imx-6 |
| `libgstreamer-plugins-bad1.0-0` | 1.14.4+imx-7 |
| `v4l-utils` | 1.16.3-3 |
| `imx-vpuwrap` | 4.4.5-mendel5 |
| `libdrm-vivante` | 2.4.84+imx-mendel3 |
| `bluez`, `bluetooth`, `libbluetooth3` | 5.50+imx-mendel3 |

Runtime del Edge TPU en disco: `/usr/lib/aarch64-linux-gnu/libedgetpu.so.1` → `libedgetpu.so.1.0` (1 135 952 bytes, fecha 9 jul 2021).

## 7. Contenido de `edgetpudemo` y `edgetpuvision`

`/usr/share/edgetpudemo/`:

- `mobilenet_ssd_v1_coco_quant_postprocess_edgetpu.tflite`
- `mobilenet_ssd_v1_coco_quant_postprocess.tflite`
- `coco_labels.txt` (solo nombres, uno por línea; empieza con `person`, `bicycle`, `car`)
- `index.html`, `video_device.mp4`, `video_stream.mp4`

Ejecutables en `/usr/bin`: `edgetpu_demo`, `edgetpu_detect`, `edgetpu_detect_server`, `edgetpu_classify`, `edgetpu_classify_server`.

Módulos en `/usr/lib/python3/dist-packages/edgetpuvision/`: `apps.py`, `camera.py`, `classify.py`, `classify_server.py`, `detect.py`, `detect_server.py`, `gst.py`, `gstreamer.py`, `pipelines.py`, `svg.py`, `utils.py`, `streaming/server.py`, `streaming/proto/messages_pb2.py`.

Plugins GStreamer en Python (`/usr/lib/aarch64-linux-gnu/gstreamer-1.0/python/`): `glbox.py`, `glsvgoverlaysink.py`, `glsvgoverlaysrc.py`.

Detalles del código (leídos de los archivos; `gstreamer.py`, `gst.py`, `utils.py` y `svg.py` no se han leído):

- `detect.py`: importa `pycoral.adapters.detect` y `pycoral.utils.edgetpu`. `render_gen(args)` es un generador: entrega `(width, height)` de la entrada del modelo y luego, en bucle, `tensor, layout, command = (yield output)`. Por cuadro ejecuta `edgetpu.run_inference(interpreter, tensor)` y `detect.get_objects(interpreter, args.threshold)`, y filtra con `labels[obj.id]` y por área.
- `pipelines.py`:
  - `v4l2_src(fmt)`: `v4l2src` con caps `video/x-raw` (formato, ancho, alto y framerate).
  - `inference_pipeline`: `glfilterbin filter=glbox` → caps RGB al tamaño del modelo → `appsink` (`emit_signals=True`, `max_buffers=1`, `drop=True`, `sync=False`).
  - `camera_headless_pipeline`: `v4l2_src` → `glupload` → `inference_pipeline`.
  - `camera_streaming_pipeline`: `v4l2src` → `tee`, con rama H.264 (`videoconvert`, `x264enc speed_preset=ultrafast tune=zerolatency threads=4`, `h264parse`, `appsink h264sink`) y rama de inferencia.
- `apps.py`: `run_server` crea `make_camera(args.source, next(gen), args.loop)` y `StreamingServer(camera, args.bitrate)`; el callback `camera.render_overlay` llama a `gen.send(...)`. `run_app` usa `run_gen(...)` con `Display` (por defecto `FULLSCREEN`).
- `--source` tiene el formato `/dev/videoN:FMT:WxH:N/D`, un `.mp4` o una imagen. Por defecto: `/dev/video0:YUY2:640x480:30/1` (servidor) y `/dev/video0:YUY2:1280x720:30/1` (`run_app`).
- `StreamingServer` escucha en los puertos web 4664, tcp 4665 y annexb 4666, y publica con `avahi-publish-service`.
- Opciones de `edgetpu_detect_server`: `--source`, `--bitrate`, `--loop`, `--model`, `--labels`, `--top_k` (50), `--threshold` (0.1), `--min_area` (0.0), `--max_area` (1.0), `--filter`, `--color`, `--print`.
