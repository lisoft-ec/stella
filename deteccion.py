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

#corte = (200, 0, 1700, 950)
#piso = (500,600,1000,900)
            
corte = (400, 200, 1600, 1080)
piso = (400,600,800,800)

TRANSPARENCIA = 0.3
ninguno = 0

##########################################################

class DetectorPersonas:

  def __init__(self, threshold = 0.5, max_objetos = 10):
    self.threshold = threshold
    self.max_objetos = max_objetos
    self.engine = DetectionEngine(modelo)   
    _, self.H, self.W, _ = self.engine.get_input_tensor_shape()

    self.engine_seg = BasicEngine(modelo_seg)
    self.movimiento = cv2.createBackgroundSubtractorKNN()
    self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9))

  def histograma(self, img):
      image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
      hist = cv2.calcHist([image], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
      hist = cv2.normalize(hist, hist).flatten()      
      return hist
  
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

  def cuerpo_movimiento(self, img):
    h, w = img.shape[:2]
    _, img = cv2.threshold(img,127,255,cv2.THRESH_BINARY)
    img = cv2.dilate(img, self.kernel)
    img = cv2.erode(img, self.kernel)
    # img = cv2.dilate(img, self.kernel)
    # img = cv2.erode(img, self.kernel)

    im_flood_fill = img.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    im_flood_fill = im_flood_fill.astype("uint8")
    cv2.floodFill(im_flood_fill, mask, (0, 0), 255)
    im_flood_fill_inv = cv2.bitwise_not(im_flood_fill)
    img_out = img | im_flood_fill_inv
    #cv2.imshow("img_fill", img_out)  
    return img_out

 
  def get(self, frame):
    global ninguno

    frame = frame[corte[1]:corte[3], corte[0]:corte[2]]    

    mov = self.movimiento.apply(frame)    


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
        detectados.append({
          'rect': box,
          'usado': 0,     
          #'color1': avg1,
          #'color2': avg2,   
        })
    
    if len(detectados) > 0:      
      mov = self.cuerpo_movimiento(mov)

      for d in detectados:
        box = d['rect']        
        cuerpo = cv2.bitwise_and(frame, frame, mask=mov)
        cuerpo = frame[box[1]:box[3], box[0]:box[2]]
        d['hist'] = self.histograma(cuerpo)

            
      #frame = cv2.bitwise_and(frame, frame, mask=img_seg)
    
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
  
  fourcc =  cv2.VideoWriter_fourcc(*"XVID")
  writer = cv2.VideoWriter("/home/almustafa/Vídeos/salida1.avi", fourcc, 15, (960,540), True)

  while True:
    (grabbed, frame) = vs.read()     
    
    if not grabbed:
      break

    #if cont >= offset:
    #frame = cv2.resize(frame, (640,480))
    _, frame2 = obj.get(frame)

    frame[corte[1]:corte[3], corte[0]:corte[2]] = frame2

    frame2 = cv2.resize(frame2, (960,540))
    writer.write(frame2)
    #cv2.imshow("Frame", frame2)
    #cv2.imshow("Frame2", frame2)

    print("FRAME: ", cont)      

    key = cv2.waitKey(100) & 0xFF   
    if key == ord("q"):
      break   

    cont+=1

  writer.release()
  vs.release()
  cv2.destroyAllWindows()    

  print("*************FIN****************")
