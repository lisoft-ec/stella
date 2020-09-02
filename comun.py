import os
from periphery import GPIO

class GoogleCoral:	
	def __init__(self):
		#print("Constructor")
		self.ledR = False
		self.ledG = False
		self.ledB = False

	def __del__(self):
		#print("Destructor")
		if self.ledR:
			self.ledR.close()
		if self.ledG:
			self.ledG.close()
		if self.ledB:
			self.ledB.close()

	def iniciar_leds(self):
		self.ledR = GPIO(138, "out")
		self.ledG = GPIO(6, "out")
		self.ledB = GPIO(73, "out")

	def setLED(self,r,g,b):
		if not self.ledR:
			self.iniciar_leds()
			
		self.ledR.write(r == 1)
		self.ledG.write(g == 1)
		self.ledB.write(b == 1)

	def leer_temperatura(self):
		cmd = 'cat /sys/class/thermal/thermal_zone0/temp'
		valor = os.popen(cmd).readline().strip()
		valor = valor[:-3] if len(valor) > 3 else valor
		return valor
