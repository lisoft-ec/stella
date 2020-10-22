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
#conecciones = hw.conecciones_guardadas()
#if "StellaWIFI" not in conecciones.keys():
#    print("Crando a StellaWIFI")
#    res = hw.crear_wifi("StellaWIFI", "sTELLAwifi")
#    print(res)

#print("Conectando WIFI:")
#res = hw.coneccion_up("StellaWIFI")
#print(res)

stream = os.popen('git -C /home/mendel/stella/ pull')
output = stream.read().strip()
print(output)
if output== "Already up to date.":
    hw.setLED(0,1,0)
else:
    hw.setLED(1,1,0) #Amarillo
time.sleep(delay)
hw.setLED(0,0,0)
del hw

print("Arranco el Programa")

os.system("sudo service programa start")

time.sleep(delay)

print("Fin!")
