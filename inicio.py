from comun import GoogleCoral
import configparser
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
conexiones = hw.conexiones_guardadas()
cte_stellawifi = "StellaWIFI"
red_default = cte_stellawifi
red_eth = "Wired connection 1"

for c in conexiones.keys():
    if conexiones[c] == 'ethernet' and not conexiones[c].startswith("gadget"):
        red_eth = c
    if conexiones[c] == 'wifi' and c != cte_stellawifi:
        red_default = c


print(red_eth, red_default)
#Leer conexion
config = configparser.ConfigParser()
#directorio = os.path.dirname(__file__)
directorio = os.path.dirname(os.path.abspath(__file__))
config.read(directorio + '/../configuraciones.ini')

tipo = config['CONEXION']['tipo']
tipo = tipo.strip()
if tipo == "wifi":
    red_wifi = config['CONEXION']['wifi']
    if red_wifi != "none":
        red_default = red_wifi

    contrasena = config['CONEXION']['contrasena']
else:
    eth = config['CONEXION']['eth']    
    eth_ip = config['CONEXION']['eth_ip']
    eth_enlace = config['CONEXION']['eth_enlace']
    eth_dns = config['CONEXION']['eth_dns']

    hw.cambiar_nombre_conexion(red_eth, 'ETH')
    red_eth = "ETH"

    res = hw.set_ethernet(red_eth, eth, eth_ip, eth_enlace, eth_dns)
    print(res)

    red_default = red_eth
       

print("Conexion a usar: ", red_default)

if cte_stellawifi not in conexiones.keys():
    print("Creando a StellaWIFI")
    hw.bajar_conexion_auto("-")
    res = hw.crear_wifi(cte_stellawifi, cte_stellawifi)
    print(res)
    time.sleep(5)

if red_default != cte_stellawifi and tipo == "wifi" and red_default not in conexiones.keys():
    print("Conectar a red WIFI")
    hw.bajar_conexion_auto("-")
    res = hw.conectar_wifi(red_default, contrasena)
    print(res)
    time.sleep(5)


print("Levantar Conexion:")
if red_default == cte_stellawifi:
    hw.setLED(1,0,1) # Violeta
else:
    hw.setLED(0,0,0)

res = hw.conexion_up(red_default)
print(res)


# GIT: Actualizaciones

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

def activar_stellawifi():
    global red_default
    hw.setLED(1,1,1) # Blanco
    red_default = cte_stellawifi
    res = hw.conexion_up(cte_stellawifi)
    print(res)

def tiempo(segundos):
    global red_default, hw
    segundos *= 10
    for i in range(segundos):        
        if hw.BTN.read():
            if red_default == cte_stellawifi:
                hw.setLED(1,1,1) # Blanco                
                hw.reiniciar()
            else:
                hw.setLED(1,0,1) # Violeta
                flag_btn += 1
                if flag_btn >= 50: #5 segundos
                    flag_btn = 0                
                    print("ACTIVAR StellaWIFI!")                 
                    activar_stellawifi()                   
        else:
            flag_btn = 0
            hw.setLED(0,0,0)

        time.sleep(0.1)

fallos = 1
flag_btn = 0
# keep network test
while True:
    # Test ping
    if red_default != cte_stellawifi:
        hostname = "google.com"
        response = os.system("ping -c 1 -w2 " + hostname + " > /dev/null 2>&1")
        if response == 0:
            print("Network Active")
            tiempo(30)
        else:
            print("Network Error: ", fallos) 
            fallos += 1
            # Baja la conexion
            res = hw.conexion_down(red_default)
            print(res)
            tiempo(3) # espera 3 segundos y vuelve a conectar
            res = hw.conexion_up(red_default)
            print(res)
            tiempo(3)
    else:
        tiempo(3)
           

print("Fin!")
