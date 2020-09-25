# sudo -H pip3 install numpy Pillow odoorpc
import cv2

from edgetpu.detection.engine import DetectionEngine, BasicEngine
from edgetpu.utils import dataset_utils, image_processing
from PIL import Image
import numpy as np
import datetime
from persona import Persona
import configparser

import odoorpc


class DetectorPersonas:

  modelo = "models/mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite"
  modelo_seg = "models/deeplabv3_mnv2_dm05_pascal_quant_edgetpu.tflite"

  TRANSPARENCIA = 0.3
  ninguno = 0

  def __init__(self, config = False, threshold = 0.5, max_objetos = 10):
    self.config = config
    self.threshold = threshold
    self.max_objetos = max_objetos
    self.engine = DetectionEngine(self.modelo)   
    _, self.H, self.W, _ = self.engine.get_input_tensor_shape()

    self.engine_seg = BasicEngine(self.modelo_seg)
    self.movimiento = cv2.createBackgroundSubtractorKNN()
    self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9))

    # self.corte = []
    # self.corte.append()

  def get_corte(self):
    txt = self.config['DETECTOR']['corte']
    txt = txt.split(',')
    return (int(txt[0]), int(txt[1]), int(txt[2]), int(txt[3]))

  def get_piso(self):
    txt = self.config['DETECTOR']['piso']
    txt = txt.split(',')
    return (int(txt[0]), int(txt[1]), int(txt[2]), int(txt[3]))

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

    corte = self.get_corte()
    piso = self.get_piso()

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
         
    frame = Persona.dibujar(frame, piso, self.TRANSPARENCIA)

    return len(objs), len(detectados), frame