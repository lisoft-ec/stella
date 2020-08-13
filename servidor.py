# USAGE
# python webstreaming.py --ip 0.0.0.0 --port 8000

# import the necessary packages
from deteccion import DetectorPersonas
from flask import Response
from flask import Flask
from flask import render_template
import threading
import datetime
import time
import cv2

con_video = 0
# initialize the output frame and a lock used to ensure thread-safe
# exchanges of the output frames (useful for multiple browsers/tabs
# are viewing tthe stream)
outputFrame = None
lock = threading.Lock()

# initialize a flask object
app = Flask(__name__)

# initialize the video stream and allow the camera sensor to
# warmup

video = "/home/mendel/out_1.avi"
vs = cv2.VideoCapture(video, cv2.CAP_V4L)
#vs.set(cv2.CAP_PROP_FRAME_WIDTH,1920)
#vs.set(cv2.CAP_PROP_FRAME_HEIGHT,1080)
#vs.set(cv2.CAP_PROP_FPS, 30)

# initialize our video writer
ind_video = 1
time.sleep(1.0)

@app.route("/")
def index():
	# return the rendered template
	return render_template("index.html")

def detect_motion(frameCount):
	global vs, outputFrame, lock, ind_video

	md = DetectorPersonas()
	total = 0
	grabando = 0
	writer = False

	# loop over frames from the video stream
	while True:
		(grabbed, frame) = vs.read()
		if not grabbed:
			break
		frame = cv2.flip(frame, 0)

		#frame2 = cv2.resize(frame, (640,480))

		detectados, frame2 = md.get(frame)

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
				


		# grab the current timestamp and draw it on the frame
		timestamp = datetime.datetime.now()
		cv2.putText(frame2, timestamp.strftime( 
			"%d/%m/%Y %I:%M:%S%p"), (150, frame2.shape[0] - 10),
			cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
		#if con_video: writer.write(frame2)
		#time.sleep(0.03)

		# if the total number of frames has reached a sufficient
		# number to construct a reasonable background model, then
		# continue to process the frame
		total += 1

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
	# return the response generated along with the specific media
	# type (mime type)
	return Response(generate(),
		mimetype = "multipart/x-mixed-replace; boundary=frame")

# check to see if this is the main thread of execution
if __name__ == '__main__':
	# start a thread that will perform motion detection
	t = threading.Thread(target=detect_motion, args=(10,))
	t.daemon = True
	t.start()

	# start the flask app
	app.run(host="0.0.0.0", port=7777, debug=False,
		threaded=True, use_reloader=False)

# release the video stream pointer
vs.release()
cv2.destroyAllWindows() 
