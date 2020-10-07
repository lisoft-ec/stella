# USAGE
# python webstreaming.py --ip 0.0.0.0 --port 8000

# Veamos

# import the necessary packages
from comun import GoogleCoral
import comun
import os
from deteccion import DetectorPersonas
from flask import Flask, Response, request, render_template
import configparser
import threading
import datetime
import time
import cv2
import numpy as np
 
usuario_sistema = os.environ['USER']

# initialize the output frame and a lock used to ensure thread-safe
# exchanges of the output frames (useful for multiple browsers/tabs
# are viewing tthe stream)
outputFrame = None
lock = threading.Lock()

# initialize a flask object
app = Flask(__name__)

# Iniciar hardware (Leds, temp)
hw = GoogleCoral()

# Iniciar Archivo de configuraciones
config = configparser.ConfigParser()
config.read('../configuraciones.ini')

# Segundos actuales
tiempo = time.time()
conexion_flag = False

# Iniciar CAMARA
con_video = config['CAMARA']['GRABAR'] == "SI"
video = config['CAMARA']['ORIGEN']
flipX = config['CAMARA']['flipX'] == "True"
flipY = config['CAMARA']['flipY'] == "True"
cap_w = int(config['CAMARA']['WIDTH'])
cap_h = int(config['CAMARA']['HEIGHT'])

if video.lower().endswith(".mp4"):
	vs = cv2.VideoCapture(video) 
else:
	if video.isdigit():
		video = int(video)
	vs = cv2.VideoCapture(video, cv2.CAP_V4L)
	vs.set(cv2.CAP_PROP_FRAME_WIDTH, cap_w)
	vs.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_h)
	vs.set(cv2.CAP_PROP_FPS, int(config['CAMARA']['FPS']))

if usuario_sistema == 'mendel':
	AF_SYSFS_NODE = '/sys/module/ov5645_camera_mipi_v2/parameters/ov5645_af'
	sysfs = open(AF_SYSFS_NODE, 'w+')

	# Led de inicio
	for i in range(3):
		hw.setLED(1,1,1)
		time.sleep(0.1)
		hw.setLED(0,0,0)
		time.sleep(0.1)

# initialize our video writer
ind_video = 1


def evento_cambio(valor):	
	global usuario_sistema	
	if valor == "entra":
		print("\n\nEvento_Cambio: ", valor, "\n\n")
		hw.setLED(0,1,0) #verde
	elif valor == "sale":
		print("\n\nEvento_Cambio: ", valor, "\n\n")
		hw.setLED(1,1,0) #amarillo
	else:
		hw.setLED(0,0,0)


@app.route("/")
def url_index():
	# return the rendered template
	return render_template("index.html", defcorte = config['DETECTOR']['corte'], defpiso = config['DETECTOR']['piso'], defpass="", defmsg="", defversion= comun.__VERSION__)

@app.route('/', methods=['POST'])
def url_index_post():
	print("ver index!")
	password = request.form['fpass']	
	msg = ""
	if password == "steLLa":
		text = request.form['fcorte']	
		config['DETECTOR']['corte'] = text

		text = request.form['fpiso']	
		config['DETECTOR']['piso'] = text

		with open('../configuraciones.ini', 'w') as configfile:
			config.write(configfile)
	else:
		msg = "Contraseña NO válida!"

	return render_template("index.html", defcorte = config['DETECTOR']['corte'], defpiso = config['DETECTOR']['piso'], defpass=password, defmsg=msg, defversion= comun.__VERSION__)

def get_image(frameCount):
	global vs, outputFrame, lock, ind_video

	md = DetectorPersonas(config = config, threshold = float(config['DETECTOR']['threshold']), max_objetos = int(config['DETECTOR']['max_objetos']), evt_cambio=evento_cambio)
	total = 0
	grabando = 0 
	writer = False
		
	primer=True

	# loop over frames from the video stream
	while True:
		(grabbed, frame) = vs.read()
		if not grabbed:
			break

		if not conexion_flag:
			lapso_tiempo = time.time() - tiempo
			if lapso_tiempo > 60:
				conexion_flag = True
				hw.conectar_wifi(config['CONEXION']['wifi'], config['CONEXION']['contrasena'])
		
		if primer and usuario_sistema == 'mendel':
			sysfs.write('1')
			sysfs.flush()
			primer=False

		if flipY and flipY:
			frame = cv2.flip(frame, -1) 
		elif flipX:
			frame = cv2.flip(frame, 1)
		elif flipY:
			frame = cv2.flip(frame, 0)

		#Resize si es necesario
		h,w = frame.shape[:2]
		if w != cap_w or h != cap_h:
			frame = cv2.resize(frame, (cap_w, cap_h))
		###

		_, detectados, frame2 = md.get(frame)		

		if con_video:
			if detectados > 0: 
				if grabando <= 0:					
					#Crear video
					fourcc =  cv2.VideoWriter_fourcc(*"XVID")
					writer = cv2.VideoWriter("out_%s.avi" % ind_video, fourcc, 15, (1920, 1080), True)
					ind_video += 1

				grabando = 45
				writer.write(frame)
			else:
				grabando -= 1
				if grabando <= 0:
					grabando = 0

				if writer and writer.isOpened():
					if grabando <= 0:						
						writer.release()
					else:
						writer.write(frame)

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
		temperatura = hw.leer_temperatura()
		cv2.putText(frame2, temperatura + " C", (frame2.shape[1] - 50, frame2.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (16, 230, 231), 1)
 
		#if con_video: writer.write(frame2)
		#time.sleep(0.03)

		# acquire the lock, set the output frame, and release the
		# lock
		with lock:
			outputFrame = frame2.copy()
#	writer.close()
		
def generate():
	# grab global references to the output frame and lock variables
	global outputFrame, lock

	# loop over frames from the output stream
	while True:
		# wait until the lock is acquired
		with lock:
			# check if the output frame is available, otherwise skip
			# the iteration of the loop
			if outputFrame is None:
				continue

			# encode the frame in JPEG format
			(flag, encodedImage) = cv2.imencode(".jpg", outputFrame)

			# ensure the frame was successfully encoded
			if not flag:
				continue

		# yield the output frame in the byte format
		yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
			bytearray(encodedImage) + b'\r\n')

@app.route("/video_feed")
def video_feed():
	return Response(generate(),
		mimetype = "multipart/x-mixed-replace; boundary=frame")

@app.route("/conexion")
def conexion():
	return render_template("conexion.html", defcorte = config['DETECTOR']['corte'], defpiso = config['DETECTOR']['piso'], defpass="", defmsg="", defversion= comun.__VERSION__)


# check to see if this is the main thread of execution
if __name__ == '__main__':
	# start a thread that will perform motion detection
	t = threading.Thread(target=get_image, args=(10,))
	t.daemon = True
	t.start()

	# start the flask app
	app.run(host="0.0.0.0", port=7777, debug=False,
		threaded=True, use_reloader=False)

# release the video stream pointer
vs.release()
cv2.destroyAllWindows() 
if usuario_sistema == 'mendel': 
	sysfs.close()
