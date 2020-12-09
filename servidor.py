# USAGE
# python webstreaming.py --ip 0.0.0.0 --port 8000

# import the necessary packages
from comun import GoogleCoral
import comun
from camara import Camara
import os
from flask import Flask, Response, request, render_template
import configparser
import threading
import time
import cv2 
import sys

camara = None
outputFrame = None
lock = threading.Lock()

# initialize a flask object
app = Flask(__name__)

@app.route("/")
def url_index():
	config = camara.config
	return render_template("index.html", defcorte = config['DETECTOR']['corte'], defpiso = config['DETECTOR']['piso'], defpass="", defmsg="", defversion= comun.__VERSION__)

@app.route('/', methods=['POST'])
def url_index_post():
	config = camara.config
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

		
def generate():
	# grab global references to the output frame and lock variables
	global outputFrame, lock

	# loop over frames from the output stream
	while True:
		time.sleep(0.5)

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
	config = camara.config
	return render_template("conexion.html", defssid = config['CONEXION']['wifi'], defpass = '', defmsg="")

@app.route("/conexion", methods=['POST'])
def conexion_post():
	config = camara.config
	password = request.form['fpass']	
	msg = ""
	if password == "steLLa":
		ssid = request.form['fssid']	
		# config['DETECTOR']['corte'] = text

		# text = request.form['fpiso']	
		# config['DETECTOR']['piso'] = text

		# with open('../configuraciones.ini', 'w') as configfile:
		# 	config.write(configfile)
	else:
		msg = "Contraseña NO válida!"

	return render_template("conexion.html", defssid = config['CONEXION']['wifi'], defpass = '', defmsg=msg)

def get_image(frame_count):
	global outputFrame, lock

	while True:
		frame = camara.procesar_imagen(True)


		with lock:
			outputFrame = frame


# check to see if this is the main thread of execution
if __name__ == '__main__':	
	#Argumentos
	args = sys.argv
	camara = Camara(args)

	# start a thread that will perform motion detection	
	t = threading.Thread(target=get_image, args=(10,))
	t.daemon = True
	t.start()
	
	# start the flask app
	app.run(host="0.0.0.0", port=7777, debug=False, threaded=True, use_reloader=False)
