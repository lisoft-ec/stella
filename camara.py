from comun import GoogleCoral
import comun
import os
from deteccion import DetectorPersonas
import configparser
import datetime
import time
import cv2
import numpy as np
import odoorpc


class Camara():

    def __init__(self, args):
        directorio = os.path.dirname(__file__)
        self.backup = directorio + "/backup.data"

        self.con_actualizacion = False
        if len(args) > 1:
            self.con_actualizacion = args[1] == "True"

        self.is_coral = os.environ['USER'] == 'mendel'

        # Iniciar hardware (Leds, temp)
        self.hw = GoogleCoral()

        # Iniciar Archivo de configuraciones
        directorio = os.path.dirname(__file__)        
        self.config = config = configparser.ConfigParser()
        config.read(directorio + '/../configuraciones.ini')

        # Iniciar CAMARA
        self.con_video = config['CAMARA']['GRABAR'] == "SI"
        self.video = config['CAMARA']['ORIGEN']
        self.flipX = config['CAMARA']['flipX'] == "True"
        self.flipY = config['CAMARA']['flipY'] == "True"
        self.cap_w = int(config['CAMARA']['WIDTH'])
        self.cap_h = int(config['CAMARA']['HEIGHT'])

        if self.video.lower().endswith(".mp4"):
            self.vs = cv2.VideoCapture(video) 
        else:
            if self.video.isdigit():
                self.video = int(self.video)
            self.vs = cv2.VideoCapture(self.video, cv2.CAP_V4L)
            self.vs.set(cv2.CAP_PROP_FRAME_WIDTH, self.cap_w)
            self.vs.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cap_h)
            self.vs.set(cv2.CAP_PROP_FPS, int(config['CAMARA']['FPS']))

        if self.is_coral:
            AF_SYSFS_NODE = '/sys/module/ov5645_camera_mipi_v2/parameters/ov5645_af'
            self.sysfs = open(AF_SYSFS_NODE, 'w+')

        # initialize our video writer
        self.ind_video = 0

        #Detector
        self.detector = DetectorPersonas(config = config, threshold = float(config['DETECTOR']['threshold']), max_objetos = int(config['DETECTOR']['max_objetos']), evt_cambio=self.evento_cambio)
        self.grabando = 0
        self.writer = False
        self.primer=True

        self.tiempo_ms = time.time()

        self.lamp_test()
        if self.con_actualizacion:
            self.hw.setLED(1,0,1) # Violeta Actualizacion
            time.sleep(3)            
        else:
            self.hw.setLED(0,1,0) # Inicio normal
            time.sleep(1)
        self.hw.setLED(0,0,0)
      

    def __del__(self): 
        print("Destructor")
    
    def evento_cambio(self, valor):	
        """
        Evento cuando entra o sale una persona
        """

        if valor == "entra":
            print("Evento_Cambio: ", valor)
            self.hw.setLED(0,1,0) #verde            
        elif valor == "sale":
            print("Evento_Cambio: ", valor)
            self.hw.setLED(1,1,0) #amarillo
        elif valor == "in" or valor == "out": # Registrar Evento
            self.guardar_en_odoo(valor)
        else:
            self.hw.setLED(0,0,0)


    def guardar_en_odoo(self, tipo):
        hoy = datetime.datetime.today()
        hora = hoy.time()
        hora = hora.hour + (hora.minute / 60.0) + (hora.second / 3600.0)                   
        
        valores = {
            'fecha': hoy.strftime("%Y-%m-%d"),
            'hora': hora,
            'zona_id': 3,
            'tipo': tipo,
            'version': comun.__VERSION__,
            'ip': self.hw.get_ip_address()
        }                

        try:
            odoo = odoorpc.ODOO('aforo.silttec.com', protocol='jsonrpc+ssl', port=443)
            #odoo = odoorpc.ODOO('192.168.0.100', port=8071)
            odoo.login('aforo', 'admin', 'stt030')
            m_registro =  odoo.env['aforo.registro']   
            r = m_registro.registrar_evento(valores)  
            print("Guardado registro: ", tipo.upper(), r) 

            # Revisar si existen backups
            if os.path.exists(self.backup):
                f = open(self.backup, 'r')
                for l in f.readlines():
                    pars = l.strip().split('|')
                    if len(pars) >= 4:
                        valores = {
                            'fecha': pars[0],
                            'hora': pars[1],
                            'zona_id': int(pars[2]),
                            'tipo': pars[3],
                            'version': comun.__VERSION__,
                            'ip': self.hw.get_ip_address()
                        } 
                        r = m_registro.registrar_evento(valores) 
                f.close()
                os.remove(self.backup)

            odoo.logout()

        except Exception as e:
            print("Error al conectar con ODOO: ", e)

            # Guardar en archivo local de respaldo
            
            f = open(self.backup, 'a')
            f.write("%s|%s|%s|%s\n" % (valores['fecha'], valores['hora'], valores['zona_id'], valores['tipo'])) 
            f.close()
            pass


    def procesar_imagen(self, show=False):
        (grabbed, frame) = self.vs.read()
        if not grabbed:
            return False        
        
        # Solo una vez, para quitar el autofocus
        if self.primer and self.is_coral:
            self.sysfs.write('1')
            self.sysfs.flush()
            self.sysfs.close()
            self.primer=False

        if self.flipY and self.flipY:
            frame = cv2.flip(frame, -1) 
        elif self.flipX:
            frame = cv2.flip(frame, 1)
        elif self.flipY:
            frame = cv2.flip(frame, 0)

        #Resize si es necesario
        h,w = frame.shape[:2]
        if w != self.cap_w or h != self.cap_h:
            frame = cv2.resize(frame, (self.cap_w, self.cap_h))
        ###       
        
        #detectados, frame2 = 0, mask
        estado, _, detectados, frame2 = self.detector.get(frame)		
        
        if self.con_video:
            if detectados > 0: 
                if self.grabando <= 0:					
                    #Crear video
                    self.writer = cv2.VideoWriter("out_%s.avi" % self.ind_video, cv2.VideoWriter_fourcc(*"XVID"), 15, (self.cap_w, self.cap_h), True)
                    self.ind_video += 1

                self.grabando = 45
                self.writer.write(frame)
            else:
                self.grabando -= 1
                if self.grabando <= 0:
                    self.grabando = 0

                if self.writer and self.writer.isOpened():
                    if self.grabando <= 0:						
                        self.writer.release()
                    else:
                        self.writer.write(frame)

        temperatura = self.hw.leer_temperatura()
        lapso_ms = time.time() - self.tiempo_ms
        self.tiempo_ms = time.time()
        
        if show:
            # Crear cuadrado oscuro inferior
            x, y, w, h = 0, frame2.shape[0] - 25, frame2.shape[1], 25
            sub_img = frame2[y:y+h, x:x+w]
            black_rect = np.zeros(sub_img.shape, dtype=np.uint8)
            res = cv2.addWeighted(sub_img, 0.3, black_rect, 0.7, 1.0)
            frame2[y:y+h, x:x+w] = res

            # Poner fecha y hora
            timestamp = datetime.datetime.now()	
            str_time = timestamp.strftime("%d/%m/%Y %I:%M:%S %p")		
            cv2.putText(frame2, str_time, (10, frame2.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (215, 231, 106), 1)

            # Poner temperatura     
            color_temp = (16, 230, 231) if estado == 'det.' else (215, 231, 106)    
            cv2.putText(frame2, temperatura + " C", (frame2.shape[1] - 50, frame2.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color_temp, 1)

            if self.con_video: 
                self.writer.write(frame2)
                #time.sleep(0.03)

        #print("Estado: %s | Lapso [ms]: %0.1f | Temp: %i°" % ( estado, lapso_ms * 1000.0, int(temperatura)))

        return frame2

    def lamp_test(self):
        self.hw.setLED(1,0,0)
        time.sleep(0.3)
        self.hw.setLED(0,1,0)
        time.sleep(0.3)
        self.hw.setLED(0,0,1)
        time.sleep(0.3)
        self.hw.setLED(0,0,0)
        time.sleep(1)

        for i in range(3):
            self.hw.setLED(1,1,1)
            time.sleep(0.3)
            self.hw.setLED(0,0,0)
            time.sleep(0.3)

        time.sleep(1)


    def temporal(self):
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

    def wifi_temp(self):
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
