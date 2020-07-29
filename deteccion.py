# sudo -H pip3 install numpy Pillow odoorpc


import cv2

from edgetpu.detection.engine import DetectionEngine, BasicEngine
from PIL import Image
import numpy as np
import datetime
from persona import Persona

import odoorpc

path = "/home/mendel/coral_contador/models/"


modelo = path + "mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite"
video = "/dev/video0"

# udevadm info --query=all --name=/dev/mmcblk0   
corte = (250, 200, 400, 450)          
piso = (20,120,120,200)
TRANSPARENCIA = 0.3
ninguno = 0
cuenta_ant = cuenta

##########################################################

odoo = odoorpc.ODOO('aforo.silttec.com', protocol='jsonrpc+ssl', port=443)
#odoo = odoorpc.ODOO('localhost', port=8071)
odoo.login('aforo', 'admin', 'stt030')
m_registro =  odoo.env['aforo.registro']

##########################################################

class DetectorPersonas:

  def __init__(self, threshold = 0.5, max_objetos = 100):
    self.threshold = threshold
    self.max_objetos = max_objetos
    self.engine = DetectionEngine(modelo)  
    _, self.H, self.W, _ = self.engine.get_input_tensor_shape()
 
  def get(self, frame):
    global ninguno
    global cuenta

    frame = frame[corte[1]:corte[3], corte[0]:corte[2]]

    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    mask = np.zeros_like(img)
  
    objs = self.engine.detect_with_image(img, threshold= self.threshold,
                                    keep_aspect_ratio=True,
                                    relative_coord=False,
                                    top_k=self.max_objetos)

    # Print and draw detected objects.    
    detectados = []
    for o in objs:    
      if o.label_id != 0: # 0 es persona (ver : coco_labels.txt)
        continue

      box = o.bounding_box.flatten().tolist()
      box = [int(i) for i in box] # to int       
        
      if piso[1] <= box[3] <= piso[3] and piso[0] <= box[2] <= piso[2] and piso[0] <= box[0] <= piso[2]:
        cv2.rectangle(mask, (box[0], box[1]), (box[2], box[3]), (255, 255, 255), cv2.FILLED)   
        detectados.append({
          'rect': box,
          'usado': 0,         
        })
    
    Persona.asociar_objetos_rect(detectados, piso, m_registro)
 
      
    
    Persona.dibujar(frame, piso, TRANSPARENCIA)

#    cv2.rectangle(frame, (0,frame.shape[0] - 40), (70, frame.shape[0]), (0, 0, 0), -1)
#    cv2.putText(frame, str(cuenta), (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX , 1, (0,255,0), 2)    

    return frame


if __name__ == '__main__':

  print("**********INICIANDO*************")

  vs = cv2.VideoCapture(video)
  

  print("OPENCV version: ", cv2.__version__)

  obj = DetectorPersonas()

  primer = True

  while True:
    (grabbed, frame) = vs.read()     
    
    if not grabbed:
      break

    if primer:
      cv2.imwrite("frame0.jpg", frame)

    frame = frame[corte[1]:corte[3], corte[0]:corte[2]]

    if primer:
      cv2.imwrite("frame_corte.jpg", frame)
    #frame = cv2.resize(frame, (640,480))
    frame = obj.get(frame)

    #qcv2.imshow("Frame", frame)

    if primer:
      primer = False
      cv2.imwrite("frame_final.jpg", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
      break   

  vs.release()
  cv2.destroyAllWindows()    

  print("*************FIN****************")
