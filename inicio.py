from comun import GoogleCoral


import os
import time

delay = 1.0

hw = GoogleCoral()

#Lamp TEST
hw.setLED(1,0,0)
time.sleep(delay)
hw.setLED(0,1,0)
time.sleep(delay)
hw.setLED(0,0,1)
time.sleep(delay)
hw.setLED(0,0,0)
time.sleep(delay)

for i in range(2):
    hw.setLED(1,1,1)
    time.sleep(delay / 5.0)
    hw.setLED(0,0,0)
    time.sleep(delay / 5.0)


#Crear wifi
conecciones = hw.conecciones_guardadas()
print(conecciones)

red_default = "SILTTEC"

if "StellaWIFI" not in conecciones.keys():
    print("Creando a StellaWIFI")
    res = hw.crear_wifi("StellaWIFI", "sTELLAwifi")
    print(res)

print("Conectando WIFI:")
res = hw.coneccion_up(red_default)
print(res)

stream = os.popen('git -C /home/mendel/stella/ pull')
output = stream.read().strip()
print(output)
if output== "Already up to date.":  # Nada q hacer
    hw.setLED(0,1,0) # verde
elif output.startswith("fatal:"):   # Error
    hw.setLED(1,0,0) # rojo
else:  # Se Actualiza
    hw.setLED(1,1,0) # amarillo  

time.sleep(delay)
hw.setLED(0,0,0)

print("Arranco el Programa")

os.system("sudo service programa start")

time.sleep(delay)

fallos = 1
# keep network test
while True:
    # Test ping
    hostname = "google.com"
    response = os.system("ping -c 1 -w2 " + hostname + " > /dev/null 2>&1")
    if response == 0:
        print("Network Active")
        time.sleep(30)
    else:
        print("Network Error: ", fallos) 
        fallos += 1
        # Baja la conexion
        res = hw.coneccion_down(red_default)
        print(res)
        time.sleep(3.0) # espera 3 segundos y vuelve a conectar
        res = hw.coneccion_up(red_default)
        print(res)
        time.sleep(3.0)

print("Fin!")
