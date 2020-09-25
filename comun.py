import os
import cv2
from periphery import GPIO
import time
import configparser

__VERSION__ = "0.1.0"

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

	def wifi_estado(self):
		cmd = 'nmcli -t -f STATE general'
		valor = os.popen(cmd).readline().strip()
		return valor

	def wifi_disponibles(self):
		os.system("nmcli device wifi rescan")		
		cmd = 'nmcli device wifi list'
		valor = os.popen(cmd).readline().strip()
		return valor
	
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