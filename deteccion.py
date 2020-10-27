# sudo -H pip3 install numpy Pillow odoorpc
import cv2

from edgetpu.detection.engine import DetectionEngine, BasicEngine
from edgetpu.utils import dataset_utils, image_processing
from PIL import Image
import numpy as np
import datetime
from persona import Persona
import configparser


class DetectorPersonas:

  modelo = "models/mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite"
  #modelo_seg = "models/deeplabv3_mnv2_dm05_pascal_quant_edgetpu.tflite"

  TRANSPARENCIA = 0.3

  def __init__(self, config = False, threshold = 0.5, max_objetos = 10, evt_cambio=None):
    self.config = config
    self.threshold = threshold
    self.max_objetos = max_objetos
    self.evt_cambio = evt_cambio
    self.engine = DetectionEngine(self.modelo)   
    self.flag_mov = False
    self.cont_nadie = 0
    #_, self.H, self.W, _ = self.engine.get_input_tensor_shape()

    #self.engine_seg = BasicEngine(self.modelo_seg)
    #self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9))

    # Background
    #self.movimiento = cv2.createBackgroundSubtractorKNN()
    self.backSub = cv2.createBackgroundSubtractorMOG2()

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

  # def histograma(self, img):
  #     image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
  #     hist = cv2.calcHist([image], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
  #     hist = cv2.normalize(hist, hist).flatten()      
  #     return hist
  
  # def segmentacion(self, img):
  #   img = Image.fromarray(img)

  #   _, height, width, _ = self.engine_seg.get_input_tensor_shape()   
  #   #print(img.width, img.height)

  #   resized_img, ratio = image_processing.resampling_with_original_ratio(img, (width, height), Image.NEAREST)

  #   input_tensor = np.asarray(resized_img).flatten()

  #   _, raw_result = self.engine_seg.run_inference(input_tensor)
  #   result = np.reshape(raw_result, (height, width))
  #   new_width, new_height = int(width * ratio[0]), int(height * ratio[1])

  #   # If keep_aspect_ratio, we need to remove the padding area.
  #   result = result[:new_height, :new_width]
  #   result = Image.fromarray(result)

  #   result = result.resize((img.width, img.height))

  #   #print(result.width, result.height)
    
  #   return np.array(result)

  # def cuerpo_movimiento(self, img):
  #   h, w = img.shape[:2]
  #   _, img = cv2.threshold(img,127,255,cv2.THRESH_BINARY)
  #   img = cv2.dilate(img, self.kernel)
  #   img = cv2.erode(img, self.kernel)
  #   # img = cv2.dilate(img, self.kernel)
  #   # img = cv2.erode(img, self.kernel)

  #   im_flood_fill = img.copy()
  #   mask = np.zeros((h + 2, w + 2), np.uint8)
  #   im_flood_fill = im_flood_fill.astype("uint8")
  #   cv2.floodFill(im_flood_fill, mask, (0, 0), 255)
  #   im_flood_fill_inv = cv2.bitwise_not(im_flood_fill)
  #   img_out = img | im_flood_fill_inv
  #   #cv2.imshow("img_fill", img_out)  
  #   return img_out

 
  def get(self, frame):
    corte = self.get_corte()
    piso = self.get_piso()

    frame = frame[corte[1]:corte[3], corte[0]:corte[2]]    
    
    # detectar movimeinto en el piso
    frame_piso = frame[piso[1]:piso[3], piso[0]:piso[2]]   
    piso_h, piso_w = frame_piso.shape[:2]     
    mask_movimiento = self.backSub.apply(frame_piso)    
    total_pxs = piso_h * piso_w
    white_pxs = np.sum(mask_movimiento == 255)
    porc_movimiento = int((white_pxs / total_pxs) * 100)
    #print("Movimiento: %s" % porc_movimiento)
    
    if porc_movimiento > 1:
      self.flag_mov = True

    if self.flag_mov:
      #print("Deteccion")
      estado = "det."
      img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))   
      objs = self.engine.detect_with_image(img, threshold= self.threshold,
                                      keep_aspect_ratio=True,
                                      relative_coord=False,
                                      top_k=self.max_objetos)
    
      # Print and draw detected objects.    
      detectados = []
      l_objs = len(objs)
      if l_objs == 0:
        self.cont_nadie += 1
      else:
        self.cont_nadie = 0
      
      if self.cont_nadie > 10:
        self.flag_mov = False

      for o in objs:    
        if o.label_id != 0: # 0 es persona (ver : coco_labels.txt)
          continue

        box = o.bounding_box.flatten().tolist()
        box = [int(i) for i in box] # to int       
          
        if piso[1] <= box[3] <= piso[3] and piso[0] <= box[2] <= piso[2] and piso[0] <= box[0] <= piso[2]:
          detectados.append({
            'rect': box,
            'usado': 0,
          })
      
      l_detectados = len(detectados)
      if l_detectados == 0:      
        if self.evt_cambio is not None:
          self.evt_cambio("nada")     
      
      Persona.asociar_objetos_rect(detectados, piso, evt_cambio=self.evt_cambio)

    else:
      #print("Pasa")
      estado = "pasa"
      l_detectados = 0
      l_objs = 0      
         
    frame = Persona.dibujar(frame, piso, self.TRANSPARENCIA)


    return estado, l_objs, l_detectados, frame