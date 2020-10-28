import os
import cv2
from periphery import GPIO
import time
import configparser

__VERSION__ = "0.1.2"

class GoogleCoral:	
	def __init__(self):
		#print("Constructor")
		self.ledR = False
		self.ledG = False
		self.ledB = False
		self.usuario_sistema = os.environ['USER']
		

	def __del__(self):
		#print("Destructor")
		if self.ledR:
			self.ledR.close()
		if self.ledG:
			self.ledG.close()
		if self.ledB:
			self.ledB.close()

	def iniciar_leds(self):
		config = configparser.ConfigParser()
		config.read('../configuraciones.ini')
		self.leds_on = int(config['GENERAL']['LEDS_ON'])
		
		self.ledR = GPIO(138, "out")
		self.ledG = GPIO(6, "out")
		self.ledB = GPIO(73, "out")

		self.ledR.write(self.leds_on == 0)
		self.ledG.write(self.leds_on == 0)
		self.ledB.write(self.leds_on == 0)

	def setLED(self,r,g,b):
		if self.usuario_sistema != 'mendel':
			return

		if not self.ledR:
			self.iniciar_leds()
			
		self.ledR.write(r == self.leds_on)
		self.ledG.write(g == self.leds_on)
		self.ledB.write(b == self.leds_on)

	def leer_temperatura(self):
		cmd = 'cat /sys/class/thermal/thermal_zone0/temp'
		valor = os.popen(cmd).readline().strip()
		valor = valor[:-3] if len(valor) > 3 else valor
		return valor

	def set_ethernet(self, nombre, tipo='auto', direccion='192.168.0.30/24', enlace='192.168.0.1', dns='8.8.8.8,1.1.1.1'):
		cmd = "nmcli con mod '%s' ipv4.addresses %s" % (nombre, direccion)
		stream = os.popen(cmd)
		output = stream.read().strip() + '\n'

		cmd = "nmcli con mod '%s' ipv4.gateway %s" % (nombre, enlace)
		stream = os.popen(cmd)
		output += stream.read().strip() + '\n'

		cmd = "nmcli con mod '%s' ipv4.dns '%s'" % (nombre, dns.replace(',', ' ').strip())
		stream = os.popen(cmd)
		output += stream.read().strip() + '\n'

		cmd = "nmcli con mod '%s' ipv4.method %s" % (nombre, tipo)  #manual auto
		stream = os.popen(cmd)
		output += stream.read().strip() + '\n'

		return output.strip()

	def wifi_estado(self):
		cmd = "nmcli -t -f STATE general"
		valor = os.popen(cmd).read().strip()
		return valor
	
	def conexiones_estado(self):
		cmd = "nmcli dev status"
		valor = os.popen(cmd).read().strip()
		
		ls = valor.split('\n')
		res = []
		indices = []
		for l in ls:
			if l.startswith('DEVICE'):
				indices.append(0)
				indices.append(l.find('TYPE'))
				indices.append(l.find('STATE'))
				indices.append(l.find('CONNECTION'))
				continue

			device = l[:indices[1]].strip()
			tipo = l[indices[1]:indices[2]].strip()
			estado = l[indices[2]:indices[3]].strip()
			conexion = l[indices[3]:].strip()

			if conexion.startswith('gadget'):
				continue
			if tipo == 'loopback':
				continue
			

			res.append((estado, tipo, conexion))

		return res

	def wifi_disponibles(self):
		os.system("nmcli device wifi rescan")		
		cmd = "nmcli device wifi list"
		valor = os.popen(cmd).read().strip()
		return valor

	def conectar_wifi(self, nombre, password):
		if self.usuario_sistema != 'mendel':
			return
		
		intentos = 20
		#Esperar a que la red este al alcance
		while True:
			lista = self.wifi_disponibles()
			if nombre in lista:
				cmd = "nmcli device wifi connect '%s' password '%s'" % (nombre, password)
				valor = os.popen(cmd).read().strip()
				return valor	
			else:
				intentos -= 1
				print("SSID no esta al alcance en este momento.")
				if intentos == 0:
					print("Termino el tiempo máximo y no se encontró la red: ", nombre)
					break
			time.sleep(3)
	
	def crear_wifi(self, nombre, password):
		if self.usuario_sistema != 'mendel':
			return

		cmd = "nmcli device wifi hotspot ifname wlan0 con-name '%s' ssid '%s' password '%s'" % (nombre, nombre, password)
		valor = os.popen(cmd).read().strip()

		cmd = "nmcli con mod '%s' connection.autoconnect yes" % nombre
		
		valor += "\n" + os.popen(cmd).read().strip()
		return valor	

	def bajar_conexion_auto(self, conexion):
		# Revisar si una esta conectada para quitarla primero
		cons = self.conexiones_estado()
		for c in cons:
			if 'connect' in c[0] and c[1] == 'wifi' and c[2] != conexion:
				if c[2] == '--':
					continue

				print("Bajar la conexion: ", c[2])
				self.conexion_down(c[2])
				time.sleep(3)
				break		

	def conexion_up(self, conexion):
		if self.usuario_sistema != 'mendel':
			return

		self.bajar_conexion_auto(conexion)

		cmd = "nmcli con up '%s'" % conexion
		valor = os.popen(cmd).read().strip()
		return valor	

	def conexion_down(self, conexion):
		if self.usuario_sistema != 'mendel':
			return

		cmd = "nmcli con down '%s'" % conexion
		valor = os.popen(cmd).read().strip()
		return valor
	
	def cambiar_nombre_conexion(self, antiguo, nuevo):
		cmd = "nmcli connection modify '%s' con-name '%s'" % (antiguo, nuevo)
		stream = os.popen(cmd)
		output = stream.read().strip()
		return output

	def conexiones_guardadas(self):
		cmd = "nmcli con"
		lineas = os.popen(cmd).readlines()
		nombres = {}
		indices = []
		for l in lineas:
			if l.startswith('NAME'):
				indices.append(0)
				indices.append(l.find('UUID'))
				indices.append(l.find('TYPE'))
				indices.append(l.find('DEVICE'))
				continue

			name = l[indices[0]:indices[1]].strip()
			uuid = l[indices[1]:indices[2]].strip()
			tipo = l[indices[2]:indices[3]].strip()
			device = l[indices[3]:].strip()

			nombres[name] = tipo

		return nombres

		# direcion ip manual
		# nmcli connection modify "Wired connection 1" con-name "ETH"
		# nmcli con mod "ETH" ipv4.addresses 192.168.2.20/24
		# nmcli con mod "ETH" ipv4.gateway 192.168.2.1
		# nmcli con mod "ETH" ipv4.dns “8.8.8.8 8.4.4.8”
		# nmcli con mod "ETH" ipv4.method manual	
		# nmcli con up "ETH"

		# nmcli -g ip4.address connection show "ETH"

		# nmcli radio wifi off
		# nmcli radio wifi on

		# leer direccion ip
		# sudo nmcli connection show
		# sudo nmcli connection show "Private" | grep address

		# nmcli con
		# nmcli con up SILTTEC
		
		# sudo ufw allow  67/udp
		# sudo ufw reload
		# sudo ufw show


	
	@staticmethod
	def rounded_rectangle(src, top_left, bottom_right, radius=1, color=255, thickness=1, line_type=cv2.LINE_AA):
		#  corners:
		#  p1 - p2
		#  |     |
		#  p4 - p3

		p1 = top_left
		p2 = (bottom_right[0], top_left[1])
		p3 = bottom_right
		p4 = (top_left[0], bottom_right[1])

		height = abs(bottom_right[1] - top_left[1])

		# Radio es porcentaje 
		if radius > 1:
			radius = 1

		corner_radius = int(radius * (height/2))

		# draw straight lines
		cv2.line(src, (p1[0] + corner_radius, p1[1]), (p2[0] - corner_radius, p2[1]), color, abs(thickness), line_type)
		cv2.line(src, (p2[0], p2[1] + corner_radius), (p3[0], p3[1] - corner_radius), color, abs(thickness), line_type)
		cv2.line(src, (p3[0] - corner_radius, p4[1]), (p4[0] + corner_radius, p3[1]), color, abs(thickness), line_type)
		cv2.line(src, (p4[0], p4[1] - corner_radius), (p1[0], p1[1] + corner_radius), color, abs(thickness), line_type)

		# draw arcs
		cv2.ellipse(src, (p1[0] + corner_radius, p1[1] + corner_radius), (corner_radius, corner_radius), 180.0, 0, 90, color ,thickness, line_type)
		cv2.ellipse(src, (p2[0] - corner_radius, p2[1] + corner_radius), (corner_radius, corner_radius), 270.0, 0, 90, color , thickness, line_type)
		cv2.ellipse(src, (p3[0] - corner_radius, p3[1] - corner_radius), (corner_radius, corner_radius), 0.0, 0, 90,   color , thickness, line_type)
		cv2.ellipse(src, (p4[0] + corner_radius, p4[1] - corner_radius), (corner_radius, corner_radius), 90.0, 0, 90,  color , thickness, line_type)

		return src
