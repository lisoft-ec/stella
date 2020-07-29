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

video = 0 # "/home/mendel/contador/demo/entrada002.webm"
vs = cv2.VideoCapture(video)
vs.set(cv2.CAP_PROP_FRAME_WIDTH,640)
vs.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
vs.set(cv2.CAP_PROP_FPS, 30)

# initialize our video writer
if con_video:
   fourcc =  cv2.VideoWriter_fourcc(*"XVID")
   writer = cv2.VideoWriter("/home/mendel/out.avi", fourcc, 30,
			(640, 480), True)

time.sleep(1.0)

@app.route("/")
def index():
	# return the rendered template
	return render_template("index.html")

def detect_motion(frameCount):
	global vs, outputFrame, lock

	md = DetectorPersonas()
	total = 0
	primer = True

	# loop over frames from the video stream
	while True:
		(grabbed, frame) = vs.read()
		if not grabbed:
			break
		frame = cv2.flip(frame, 0)
		if con_video: writer.write(frame)

		if primer:
			cv2.imwrite("frame0.jpg", frame)		

		frame = md.get(frame)

		if primer:
			primer = False
			cv2.imwrite("frame_final.jpg", frame)

		# grab the current timestamp and draw it on the frame
		timestamp = datetime.datetime.now()
		cv2.putText(frame, timestamp.strftime( 
			"%d/%m/%Y %I:%M:%S%p"), (150, frame.shape[0] - 10),
			cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
		#if con_video: writer.write(frame)
		#time.sleep(0.03)

		# if the total number of frames has reached a sufficient
		# number to construct a reasonable background model, then
		# continue to process the frame
		total += 1

		# acquire the lock, set the output frame, and release the
		# lock
		with lock:
			outputFrame = frame.copy()
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
