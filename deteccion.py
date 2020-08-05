# sudo -H pip3 install numpy Pillow odoorpc


import cv2

from edgetpu.detection.engine import DetectionEngine, BasicEngine
from edgetpu.utils import dataset_utils, image_processing
from PIL import Image
import numpy as np
import datetime
from persona import Persona

import odoorpc

modelo = "models/mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite"
#modelo_seg = "models/deeplabv3_mnv2_pascal_quant_edgetpu.tflite"
modelo_seg = "models/deeplabv3_mnv2_dm05_pascal_quant_edgetpu.tflite"

video =  "/home/almustafa/Vídeos/local01.mp4" # "/dev/video0"

# udevadm info --query=all --name=/dev/mmcblk0
corte = (250, 200, 400, 470)          
#piso = (20,120,120,200)

piso = (20,150,130,280)
            
TRANSPARENCIA = 0.3
ninguno = 0

##########################################################

class DetectorPersonas:

  def __init__(self, threshold = 0.5, max_objetos = 100):
    self.threshold = threshold
    self.max_objetos = max_objetos
    self.engine = DetectionEngine(modelo)  
    _, self.H, self.W, _ = self.engine.get_input_tensor_shape()

    self.engine_seg = BasicEngine(modelo_seg)

  
  def segmentacion(self, img):
    img = Image.fromarray(img)

    _, height, width, _ = self.engine_seg.get_input_tensor_shape()   
    #print(img.width, img.height)

    resized_img, ratio = image_processing.resampling_with_original_ratio(img, (width, height), Image.NEAREST)

    input_tensor = np.asarray(resized_img).flatten()

    _, raw_result = self.engine_seg.run_inference(input_tensor)
    result = np.reshape(raw_result, (height, width))
    new_width, new_height = int(width * ratio[0]), int(height * ratio[1])

    # If keep_aspect_ratio, we need to remove the padding area.
    result = result[:new_height, :new_width]
    result = Image.fromarray(result)

    result = result.resize((img.width, img.height))

    #print(result.width, result.height)
    
    return np.array(result)

 
  def get(self, frame):
    global ninguno

    frame = frame[corte[1]:corte[3], corte[0]:corte[2]]

    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))    
  
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
        #cv2.rectangle(mask, (box[0], box[1]), (box[2], box[3]), (255, 255, 255), cv2.FILLED)
        #print("Cuerpo: ", box[2]- box[0], box[3] - box[1])  
        #cuerpo = frame[box[1]:box[3], box[0]:box[2]]

        #cuerpo_seg = self.segmentacion(cuerpo)

        #y1 = int(box[1] + (box[3] - box[1])/2)
        #cv2.imshow("cuerpo", cuerpo_seg)
        
        #avg1 = cv2.mean(frame[box[1]:y1, box[0]:box[2]]) 
        
        detectados.append({
          'rect': box,
          'usado': 0,     
          #'color1': avg1,
          #'color2': avg2,   
        })
    
    # if len(detectados) > 0:
    #   img_seg = self.segmentacion(frame)
    #   img_seg = np.array(img_seg, dtype=np.int8)
    #   #cv2.imshow("img_seg", img_seg)      
    #   frame = cv2.bitwise_and(frame, frame, mask=img_seg)
    
    Persona.asociar_objetos_rect(detectados, piso)
         
    frame = Persona.dibujar(frame, piso, TRANSPARENCIA)

    return len(objs), frame


if __name__ == '__main__':

  print("**********INICIANDO*************")

  vs = cv2.VideoCapture(video)
  

  print("OPENCV version: ", cv2.__version__)

  obj = DetectorPersonas()

  primer = True

  cont = 1

  offset = 300

  while True:
    (grabbed, frame) = vs.read()     
    
    if not grabbed:
      break

    #if cont >= offset:
    frame = cv2.resize(frame, (640,480))
    _, frame2 = obj.get(frame)

    frame[corte[1]:corte[3], corte[0]:corte[2]] = frame2

    cv2.imshow("Frame", frame)

    print("FRAME: ", cont)      

    key = cv2.waitKey() & 0xFF   
    if key == ord("q"):
      break   

    cont+=1

  vs.release()
  cv2.destroyAllWindows()    

  print("*************FIN****************")
