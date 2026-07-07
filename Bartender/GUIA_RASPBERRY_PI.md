# Guía de despliegue — MIA en Raspberry Pi 3

Esta guía cubre la instalación completa del proyecto en un Raspberry Pi 3 físico:
sistema operativo, dependencias, cableado de las bombas del Bartender 3.0, el panel
táctil DSI de 7'', configuración, primera ejecución y puesta en marcha automática al
encender el Pi.

Complementa al `README.md` (que explica arquitectura y uso); aquí el foco es
"cómo llevar el proyecto de mi laptop/Windows al Pi real, paso a paso".

---

## 0. Lista de hardware necesario

| Componente | Notas |
|---|---|
| Raspberry Pi 3 (B o B+) | 1 GB RAM — ver nota de SO en la sección 1 |
| microSD 16 GB+ | Clase 10 / A1 recomendado |
| Fuente de poder 5V/2.5A | Una fuente débil causa reinicios aleatorios, sobre todo con USB (cámara+mic) + panel conectados |
| Panel táctil DSI 7'' 800x480 (capacitivo, ft5x06) | Ver sección 6 — cableado y requisitos de SO |
| Webcam USB | Para `eye.py` |
| Micrófono USB (o virtual vía AudioRelay) | Para `ear.py` |
| Bocinas (USB, jack 3.5mm, o HDMI) | Para `voice.py` |
| 8 bombas peristálticas 12V + módulo de relés (8 canales) | Bartender 3.0 — ver sección 5 |
| Fuente 12V separada para las bombas | **No alimentar las bombas desde el Pi** — solo comparten GND |

---

## 1. Flashear el sistema operativo

⚠️ **Importante — cambia respecto a un Pi "solo voz" sin pantalla**: el panel táctil DSI
solo funciona plug-and-play sobre **Raspberry Pi OS oficial con entorno de escritorio**
(el manual del panel lo dice explícito: *"other systems are not supported by plug and
play"*). Un Pi 3 sin pantalla podría usar Raspberry Pi OS **Lite** para ahorrar RAM, pero
como este proyecto sí lleva panel, **Lite no sirve** — el touch no se auto-configuraría.
La sección 8 explica cómo compensar esa RAM extra que consume el escritorio.

1. Descarga [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Elige **Raspberry Pi OS (32-bit)** — la versión "Desktop" normal, **no** "Raspberry Pi OS
   Full" (esa trae LibreOffice, Mathematica, etc. — peso extra en disco que no necesitas).
3. Antes de escribir, abre las opciones avanzadas (⚙️ / Ctrl+Shift+X) y configura:
   - Hostname (ej. `mia`)
   - Habilitar SSH (con contraseña o tu llave pública)
   - WiFi (SSID/contraseña) si no vas a usar cable ethernet
   - Usuario/contraseña
4. Escribe la imagen, inserta la microSD en el Pi y enciéndelo.
5. Conéctate por SSH desde tu PC:
   ```bash
   ssh pi@mia.local
   # o ssh pi@<IP-DEL-PI> si mDNS no resuelve
   ```

---

## 2. Preparar el sistema

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Instala las dependencias de sistema **antes** de `pip install` — así los paquetes pesados
(OpenCV, PyAudio, numpy) se instalan como binarios precompilados de piwheels en vez de
compilar desde código fuente (en un Pi 3 eso puede tardar 30-60+ min o colgarse por RAM):

```bash
sudo apt install -y python3-pip python3-venv git \
    python3-opencv python3-pyaudio python3-numpy python3-tk \
    portaudio19-dev mpg123
```

- `python3-opencv`, `python3-pyaudio`, `python3-numpy` → versiones del sistema, evitan compilar.
- `python3-tk` → necesario para `touch_ui.py` (la interfaz del panel táctil, sección 7). No viene preinstalado en Raspberry Pi OS Desktop.
- `portaudio19-dev` → fallback por si `pip` necesita compilar PyAudio de todos modos.
- `mpg123` → reproductor que usa `voice.py` para sacar audio por las bocinas del Pi (ver `voice.py::_play_unix`).

Verifica que pip apunte a piwheels (viene por defecto en Raspberry Pi OS, pero confírmalo):
```bash
cat /etc/pip.conf 2>/dev/null || cat ~/.pip/pip.conf 2>/dev/null
# Debe mostrar algo como: [global] extra-index-url=https://www.piwheels.org/simple
```

Interfaces I2C/SPI: **no hace falta habilitarlas**. El panel DSI y el touch se
auto-detectan por el kernel/Xorg sin tocar `raspi-config`, y `pump_controller.py` solo usa
GPIO estándar. Solo entrarías a `Interface Options` si más adelante agregas otro periférico
I2C/SPI (ej. un sensor).

---

## 3. Copiar el proyecto al Pi

Desde tu PC (elige una opción):

```bash
# Opción A: scp directo
scp -r "C:\Users\Lcant\Desktop\Bartender\Bartender" pi@mia.local:~/mia

# Opción B: si el proyecto está en un repo git
ssh pi@mia.local
git clone <tu-repo> ~/mia
```

---

## 4. Instalar dependencias de Python

En el Pi:

```bash
cd ~/mia
pip install -r requirements.txt --break-system-packages
```

`--break-system-packages` es necesario en Raspberry Pi OS moderno (Debian Bookworm+),
que por defecto bloquea `pip install` fuera de un entorno virtual.

Si `opencv-python-headless` o `pyaudio` intentan compilar de todos modos (verás mucho output
de compilación en vez de "Using cached..."), cancela con Ctrl+C y confirma que instalaste
los paquetes `apt` de la sección 2 — luego usa `pip install --no-deps` para esos dos paquetes
específicos, dejando que el resto se resuelva vía `apt`.

Esta vez `RPi.GPIO` **sí debe instalar sin problemas** (a diferencia de Windows), porque
en el Pi real hay acceso nativo a GPIO.

`tkinter` no está en `requirements.txt` porque no es un paquete de `pip` — viene del
sistema operativo vía `python3-tk` (ya instalado en la sección 2).

---

## 5. Cableado de las bombas (Bartender 3.0)

`pump_config.json` ya viene configurado con este mapeo BCM → ingrediente:

| Pump | GPIO (BCM) | Pin físico (header 40 pines) | Ingrediente |
|---|---|---|---|
| pump_1 | GPIO17 | Pin 11 | gin |
| pump_2 | GPIO27 | Pin 13 | ron |
| pump_3 | GPIO22 | Pin 15 | vodka |
| pump_4 | GPIO23 | Pin 16 | tequila |
| pump_5 | GPIO24 | Pin 18 | whisky |
| pump_6 | GPIO25 | Pin 22 | tónica |
| pump_7 | GPIO5  | Pin 29 | cola |
| pump_8 | GPIO6  | Pin 31 | naranja |

**Lógica del relé — importante:** `pump_controller.py` inicializa los pines en `GPIO.HIGH`
y activa la bomba poniendo el pin en `GPIO.LOW` (línea `_pour()`). Esto asume un **módulo de
relés activo en bajo** (el tipo más común en kits de 8 canales tipo Songle/SRD-05VDC).
Si tu módulo es activo en alto, invierte `HIGH`/`LOW` en `pump_controller.py` (`__init__` y `_pour`).

### Conexión

1. **GND común**: conecta el GND del Pi al GND del módulo de relés y al GND de la fuente de 12V de las bombas. Todo debe compartir tierra.
2. **Señal**: cada pin BCM de la tabla → su entrada IN correspondiente en el módulo de relés.
3. **Alimentación del módulo de relés**: VCC del módulo → 5V del Pi *solo si tu módulo consume poco*; si tiene 8 relés y consume mucho, mejor alimentar el módulo con una fuente 5V externa y compartir solo GND — para no sobrecargar el regulador del Pi (recuerda que el panel táctil también tira de esos mismos 5V, ver sección 6).
4. **Bombas**: cada bomba 12V se alimenta desde la fuente 12V separada, pasando por el contacto NO (Normally Open) de su relé correspondiente.
5. **NUNCA** alimentes las bombas directo desde el Pi — solo la señal de control pasa por GPIO.

⚠️ **Seguridad**: mantén la fuente 12V y las conexiones de las bombas físicamente separadas
de los pines lógicos del Pi y de cualquier líquido. Usa manguera apta para alimentos.

### Probar cada bomba antes de correr MIA completa

```bash
cd ~/mia
python3 -c "
from pump_controller import PumpController
pc = PumpController()
for name, p in pc.pump_configuration.items():
    input(f'Presiona Enter para probar {name} ({p[\"value\"]}, pin {p[\"pin\"]})...')
    pc._pour(p['pin'], 1.0)
    print('  -> pulso de 1s enviado')
pc.cleanup()
"
```

Si alguna bomba no activa: revisa el cableado de esa señal específica y que el relé
correspondiente haga "click" (los módulos de relé normalmente traen un LED indicador por canal).

---

## 6. Conectar el panel táctil DSI 7''

Según el manual del panel (`7inch-DSI-Display_User_Manual-V1.1.pdf`, incluido en el proyecto):

- **Interfaz**: cable FFC de 15 pines (1.0mm de paso) directo al puerto MIPI DSI del Pi —
  no es HDMI ni USB, y el touch (controlador capacitivo `ft5x06`) viaja por el mismo cable.
  No requiere instalar drivers: el kernel de Raspberry Pi OS Desktop lo detecta solo.
- **Alimentación — dos métodos, no mezclarlos**:
  1. **Pogo pins** (recomendado si vas a atornillar el Pi al panel con los parales de cobre
     incluidos): el panel toma los 5V directo por los pines pogo al hacer contacto con el
     header del Pi. No necesitas cablear nada aparte.
  2. **Conector DuPont** (si el Pi queda suelto, sin atornillar al panel): el manual advierte
     explícitamente que debes usar el cable DuPont de 2 pines para conectar **los pines
     físicos 4 (5V) y 6 (GND)** del Pi al conector de alimentación del panel — **conectarlo
     mal puede dañar el módulo**. No autoalimentes el panel desde ningún otro pin.
- **Botón de brillo físico**: está en la placa del panel (no en software) — toque corto
  sube el brillo 10% (cíclico), 3 segundos mantenido apaga el backlight.
- **Teclado en pantalla** (opcional — MIA es por voz, pero útil si necesitas escribir algo
  directo en el Pi): `sudo apt-get install matchbox-keyboard`.
- **Rotar la pantalla** (si la montaste al revés): con el escritorio abierto, ícono de
  Raspberry → Preferences → Screen Configuration → clic derecho en "DSI-2" → Orientation.
  Solo funciona en imágenes oficiales posteriores a 2023-12-05.

Después de conectar y encender, confirma resolución y touch:
```bash
DISPLAY=:0 xrandr | head -5          # debería listar DSI-2 (o similar) a 800x480
python3 -c "import tkinter as tk; r=tk.Tk(); r.geometry('300x100'); tk.Label(r, text='toca aquí').pack(); r.mainloop()"
# toca la ventana; si el clic responde, el touch está funcionando
```

---

## 7. Interfaz local en el panel (`main_kiosk.py`) vs. modo web (`server.py`)

El proyecto ahora tiene **dos formas de interactuar** con MIA, y para un Pi 3 de 1GB
la diferencia de RAM entre ellas es grande:

| Modo | Entry point | Costo de RAM aprox. | Cuándo usarlo |
|---|---|---|---|
| **Kiosko táctil (recomendado con este panel)** | `main_kiosk.py` | Tkinter: unos pocos MB extra | Panel DSI conectado directo al Pi — botones grandes de "Hablar"/"Mirar" + estado en vivo, sin navegador |
| Servidor web | `server.py` | Flask+SocketIO: modesto, pero si además abres un navegador en kiosko en el propio panel para verlo, un Chromium suma **150-250MB+** | Control remoto desde el celular; `server.py` sirve `templates/index.html`, que aún no está armado (ver README) |
| Consola | `main.py` | Mínimo | Pruebas/debug por SSH, sin pantalla |

`touch_ui.py` (nuevo) es una interfaz nativa en Tkinter — **no** un navegador — hecha
específicamente para no repetir el patrón típico de estos paneles (Chromium en kiosko
apuntando a `localhost:5000`), que en un Pi 3 con 1GB de RAM compite directo por memoria
con Gemini/OpenCV/numpy ya cargados en el proceso de MIA. Dibuja: estado actual grande
("Escuchando...", "Pensando...", "Preparando Gin & Tonic..."), la última respuesta de
texto, y tres botones táctiles (Hablar / Mirar / Salir) que inyectan comandos directo a
`Ear.audio_queue` — el mismo mecanismo que ya usa el push-to-talk web.

```bash
cd ~/mia
python3 main_kiosk.py
```

Debería abrir en pantalla completa sobre el panel (800x480), mostrando "Di 'Hey MIA'".
Prueba el botón "🎤 Hablar" — debe comportarse como si hubieras dicho la wake word.

> Si más adelante armas `templates/index.html` para `server.py` y quieres las dos vías
> (celular + panel) simultáneas, ten en cuenta que hoy `on_state_change` solo admite un
> listener a la vez — `main_kiosk.py` y `server.py` no están pensados para correr juntos
> tal como están escritos.

---

## 8. Reducir el consumo de RAM con el entorno de escritorio

Como el touch obliga a tener Raspberry Pi OS Desktop (sección 1), la RAM que "recuperarías"
con Lite hay que recuperarla de otra forma: evitando que el escritorio cargue cosas que no
vas a usar (panel, taskbar, salvapantallas, gestor de archivos, y sobre todo un navegador).

### Arrancar directo a `main_kiosk.py` sin el escritorio completo (recomendado)

1. `sudo raspi-config` → `System Options` → `Boot / Auto Login` → **Console Autologin**
   (arranca en terminal, no en el escritorio de LXDE — ahorra el panel/taskbar completo).
2. Crea `~/.bash_profile` para lanzar X automáticamente solo al iniciar sesión en la
   consola principal (tty1):
   ```bash
   cat >> ~/.bash_profile << 'EOF'
   if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
       startx
   fi
   EOF
   ```
3. Crea `~/.xinitrc` con el mínimo indispensable (sin gestor de ventanas de escritorio
   completo — `matchbox-window-manager` es una alternativa aún más liviana si Tkinter
   necesita ayuda con el foco de la ventana en fullscreen):
   ```bash
   cat > ~/.xinitrc << 'EOF'
   #!/bin/sh
   xset -dpms      # sin apagado de pantalla por inactividad
   xset s off      # sin salvapantallas
   cd ~/mia
   exec python3 main_kiosk.py
   EOF
   chmod +x ~/.xinitrc
   ```
4. Reinicia: `sudo reboot`. Debería arrancar directo en `main_kiosk.py` a pantalla completa,
   sin escritorio de por medio.

### Servicios que puedes desactivar (si no los usas)

```bash
sudo systemctl disable bluetooth.service    # si no usas Bluetooth
sudo systemctl disable triggerhappy.service # atajos de teclado, no aplica sin teclado físico
sudo systemctl disable cups.service         # impresión, casi nunca se usa en un Pi headless/kiosko
```
No desactives `avahi-daemon` si dependes de `mia.local` para conectarte por SSH.

### Otras ganancias menores

- No instales/uses Chromium para nada relacionado a MIA — es, con diferencia, lo más
  pesado que podrías sumar a este proceso en RAM.
- `dphys-swapfile`: déjalo activo (no lo desactives) — en 1GB de RAM el swap es red de
  seguridad ante picos, no el enemigo aquí; el enemigo es correr un navegador.
- Verifica consumo real en cualquier momento con `free -h` y `htop` (`sudo apt install htop`).

---

## 9. Configurar variables y `config.py`

### API key de Gemini
```bash
echo 'export GEMINI_API_KEY="tu-key-aqui"' >> ~/.bashrc
source ~/.bashrc
```
Verifica: `echo $GEMINI_API_KEY`

Si vas a correr MIA con `sudo` (por ejemplo por permisos de GPIO), el entorno de root no
hereda tu `~/.bashrc`. Alternativas:
```bash
# Opción A: agregar la key a nivel sistema
echo 'GEMINI_API_KEY="tu-key-aqui"' | sudo tee -a /etc/environment

# Opción B: exportarla justo antes del comando
sudo GEMINI_API_KEY="tu-key-aqui" python3 main_kiosk.py
```

### Ajustes específicos de hardware en `config.py`

Edita estos valores para que coincidan con tu Pi real (ahora mismo tienen los valores
de la máquina de desarrollo en Windows):

| Variable | Qué cambiar |
|---|---|
| `MICROPHONE_NAME` | Corre el snippet de abajo y usa el nombre (parcial) que veas en el Pi |
| `CAMERA_INDEX` | `0` si es la única webcam USB; usa `ls /dev/video*` para confirmar |
| `STT_LANGUAGE` | Déjalo en `"es-ES"` salvo que prefieras otro dialecto de Google STT |
| `TOUCH_SCREEN_WIDTH` / `TOUCH_SCREEN_HEIGHT` | Ya vienen en 800x480 (resolución nativa del panel); solo cámbialos si usas otro panel |

Listar micrófonos disponibles en el Pi:
```bash
python3 -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"
```

---

## 10. Primera ejecución (modo consola, para descartar errores antes del panel)

```bash
cd ~/mia
python3 main.py
```

Deberías ver la secuencia de inicialización (Gemini conectado, memoria lista, cámara
on-demand, bombas detectadas). Prueba:
1. Di **"Hey MIA"** y espera el "¿Sí?"
2. Di un comando simple: "¿cómo estás?"
3. Prueba visión: "mira esto y dime qué ves"
4. Prueba una bebida: "hazme un Gin & Tonic" (si ya cableaste las bombas)
5. Escribe `salir` para apagar limpio (libera cámara y GPIO)

Si algo falla, revisa la sección **Solución de problemas** del `README.md` — cubre errores
comunes de `GEMINI_API_KEY`, micrófono, cámara y GPIO. Una vez que esto funciona sin
errores, pasa a `main_kiosk.py` (sección 7) para probar sobre el panel.

---

## 11. Arranque automático al encender el Pi (systemd)

Si seguiste la sección 8 (autologin a consola + `.xinitrc`), `main_kiosk.py` **ya arranca
solo** al encender el Pi — no necesitas systemd para eso.

Si en cambio prefieres el modo servidor web (`server.py`) corriendo como servicio de
fondo (más robusto ante crashes que `.xinitrc`, útil si accedes solo desde el celular):

```bash
sudo nano /etc/systemd/system/mia.service
```

```ini
[Unit]
Description=MIA Voice Assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/mia
Environment="GEMINI_API_KEY=tu-key-aqui"
ExecStart=/usr/bin/python3 /home/pi/mia/server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable mia.service
sudo systemctl start mia.service

# Ver logs en vivo
journalctl -u mia.service -f
```

---

## 12. Mantenimiento

- **Limpiar mangueras**: coloca todas las mangueras en agua y corre:
  ```bash
  python3 -c "from pump_controller import PumpController; PumpController().clean()"
  ```
- **Actualizar código**: `git pull` (si clonaste por git) y reinicia (`.xinitrc`) o
  `sudo systemctl restart mia.service` (si usas el servicio de `server.py`).
- **Cuota de Gemini agotada (error 429)**: espera al reinicio de cuota (medianoche hora
  Pacífico) o revisa límites vigentes en [ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits).
- **Pines GPIO "atascados"** tras un crash: `sudo pkill -f mia` o reinicia el Pi.

---

## Checklist rápido

- [ ] Raspberry Pi OS **Desktop** (no Lite) flasheado — obligatorio por el panel táctil
- [ ] `apt install` de dependencias de sistema (opencv, pyaudio, numpy, `python3-tk`, mpg123)
- [ ] Proyecto copiado a `~/mia`
- [ ] `pip install -r requirements.txt --break-system-packages` sin errores
- [ ] `GEMINI_API_KEY` exportada y verificada (`echo $GEMINI_API_KEY`)
- [ ] `MICROPHONE_NAME` y `CAMERA_INDEX` ajustados en `config.py`
- [ ] Relés cableados según la tabla de la sección 5, cada bomba probada individualmente
- [ ] Panel táctil conectado (pogo pins o DuPont a pines 4/6), `xrandr` lo detecta a 800x480
- [ ] `python3 main.py` corre y responde a "Hey MIA" (prueba en consola primero)
- [ ] `python3 main_kiosk.py` corre en pantalla completa sobre el panel y los botones responden
- [ ] Autologin a consola + `.xinitrc` configurado para que `main_kiosk.py` arranque solo
- [ ] Servicios innecesarios desactivados (bluetooth/triggerhappy/cups) si no los usas
