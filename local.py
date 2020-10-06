# sudo -H pip3 install numpy Pillow odoorpc
import cv2

from edgetpu.detection.engine import DetectionEngine, BasicEngine
from edgetpu.utils import dataset_utils, image_processing
from PIL import Image
import numpy as np
import datetime
from persona import Persona
import configparser
from deteccion import DetectorPersonas
from filas import FilasPersonas


import odoorpc
     
TRANSPARENCIA = 0.3
ninguno = 0


refPt = []
cropping = False
def imagen_click(event, x, y, flags, param):
    global refPt

    if event == cv2.EVENT_LBUTTONUP:
        refPt.append([x, y])        
        for pto in refPt:
            print("%s,%s" % (pto[0], pto[1]), end=" ")
        print()
	#	cropping = False
		


print("**********INICIANDO*************")

config = configparser.ConfigParser()
config.read('/home/almustafa/Programas/coral/codigo/configuraciones.ini')

# Iniciar CAMARA
con_video = config['CAMARA']['GRABAR'] == "SI"
video = config['CAMARA']['ORIGEN']
cap_w = int(config['CAMARA']['WIDTH'])
cap_h = int(config['CAMARA']['HEIGHT'])

if video.isdigit():
	video = int(video)

if video.lower().endswith(".mp4"):
	vs = cv2.VideoCapture(video) 
else:
	vs = cv2.VideoCapture(video, cv2.CAP_V4L)
	vs.set(cv2.CAP_PROP_FRAME_WIDTH, cap_w)
	vs.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_h)
	vs.set(cv2.CAP_PROP_FPS, int(config['CAMARA']['FPS']))


print("OPENCV version: ", cv2.__version__)

md = FilasPersonas(config = config, threshold = float(config['DETECTOR']['threshold']), max_objetos = int(config['DETECTOR']['max_objetos']))
	

primer = True

cont = 1

offset = 300

cv2.namedWindow("image")
cv2.setMouseCallback("image", imagen_click)

while True:
    (grabbed, frame) = vs.read()     

    if not grabbed:
        break

    h,w = frame.shape[:2]
    if w != cap_w or h != cap_h:
        frame = cv2.resize(frame, (cap_w, cap_h))

    _, _, frame2 = md.get(frame)

    #frame[corte[1]:corte[3], corte[0]:corte[2]] = frame2

    #frame2 = cv2.resize(frame2, (960,540))
    #writer.write(frame2)

    if len(refPt) > 3:    
        puntos = np.array(refPt)
        cv2.polylines(frame2, [puntos], True, (0, 255, 0), 2)
	    #cv2.rectangle(frame2, refPt[0], refPt[1], (0, 255, 0), 2)

    cv2.imshow("image", frame2)
    #cv2.imshow("Frame2", frame2)

    print("FRAME: ", cont)      

    key = cv2.waitKey(1) & 0xFF   
    if key == ord("q"):
        break   

    cont+=1

#writer.release()
vs.release()
cv2.destroyAllWindows()    

print("*************FIN****************")
