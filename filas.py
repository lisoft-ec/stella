# sudo -H pip3 install numpy Pillow odoorpc
import cv2

from edgetpu.detection.engine import DetectionEngine, BasicEngine
from edgetpu.utils import dataset_utils, image_processing
from PIL import Image
import numpy as np
import datetime
from persona import Persona
import configparser
from comun import GoogleCoral

import odoorpc


class FilasPersonas:

  modelo = "models/mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite"

  TRANSPARENCIA = 0.3
  ninguno = 0

  def __init__(self, config = False, threshold = 0.5, max_objetos = 10):
    self.config = config
    self.threshold = threshold
    self.max_objetos = max_objetos
    self.engine = DetectionEngine(self.modelo)
    _, self.H, self.W, _ = self.engine.get_input_tensor_shape()
    self.zonas = []

    self.get_zonas()

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

  def get_zonas(self):
    secciones = self.config.sections()    
    for z in secciones:
      if "ZONA" not in z:
        continue

      color = self.config[z]['color']
      colores = color.split(",")
      color = (int(colores[2].strip()), int(colores[1].strip()), int(colores[0].strip()))

      s_puntos = self.config[z]['puntos']
      s_puntos = s_puntos.split(",")
      puntos = []
      x = False
      y = False
      for pto in s_puntos:
        if x == False:
          x = int(pto)
        elif y == False:
          y = int(pto)
          puntos.append([x,y])
          x = False
          y = False
      
      s_salida = self.config[z]['salida']
      s_salida = s_salida.split(",")
      salida = []
      x = False
      y = False
      for pto in s_salida:
        if x == False:
          x = int(pto)
        elif y == False:
          y = int(pto)
          salida.append([x,y])
          x = False
          y = False      

      zona = {
        'nombre': z,
        'color': color,
        'puntos': np.array(puntos),
        'cantidad': 0,
        'salida': np.array(salida),
      }

      self.zonas.append(zona)    

  @staticmethod
  def box_dentro(box, poly):
    return FilasPersonas.pto_dentro(box[0], box[3], poly) or FilasPersonas.pto_dentro(box[2], box[3], poly)
  
  @staticmethod
  def box_in_box(box1, box2):    
    return FilasPersonas.pto_in_box((box1[0], box1[1]), box2) and FilasPersonas.pto_in_box((box1[2], box1[1]), box2) and FilasPersonas.pto_in_box((box1[0], box1[3]), box2) and FilasPersonas.pto_in_box((box1[2], box1[3]), box2)

  @staticmethod
  def pto_in_box(pto, box):
    return box[0] <= pto[0] <= box[2] and box[1] <= pto[1] <= box[3]

  @staticmethod
  def pto_dentro(x,y,poly):
    n = len(poly)
    inside = False
    p2x = 0.0
    p2y = 0.0
    xints = 0.0
    p1x,p1y = poly[0]
    for i in range(n+1):
        p2x,p2y = poly[i % n]
        if y > min(p1y,p2y):
            if y <= max(p1y,p2y):
                if x <= max(p1x,p2x):
                    if p1y != p2y:
                        xints = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x,p1y = p2x,p2y

    return inside
    
 
  def get(self, frame):
    global ninguno

    corte = self.get_corte()
    piso = self.get_piso()

    #frame = frame[corte[1]:corte[3], corte[0]:corte[2]]    
    h,w = frame.shape[:2]
    area_total = w*h

    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))    
  
    objs = self.engine.detect_with_image(img, threshold= self.threshold,
                                   keep_aspect_ratio=False,
                                   relative_coord=False,
                                   top_k=self.max_objetos)

    
    objetos = []
    for o in objs: 
      if o.label_id != 0: # 0 es persona (ver : coco_labels.txt)
        continue

      box = o.bounding_box.flatten().tolist()
      box = [int(i) for i in box] # to int        
      
      area = (box[2] - box[0]) * (box[3] - box[1])
      # No puede ser tan grande
      if area > area_total * 0.5:
        continue
    
      objetos.append(box)

    personas = []
    for o in objetos: 
      pasa = True
      #cajas dentro de cajas
      for oo in objetos:
        if o == oo:
          continue

        if FilasPersonas.box_in_box(o, oo):
          pasa = False
          break
      
      if pasa:
        personas.append(o)   

      
    numero = 0

    for box in personas:  
      GoogleCoral.rounded_rectangle(frame, (box[0], box[1]), (box[2], box[3]), 0.2, (0,255,0), 2)
      
      #cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (255,0,0), 1)

      # Dibujo Zonas
    #   for zona in self.zonas:
    #     cv2.polylines(frame, [zona['puntos']], True, zona['color'], 2)
    #     cv2.polylines(frame, [zona['salida']], True, (100,100,100), 2)

    #     if FilasPersonas.box_dentro(box, zona['puntos']):
    #       numero += 1
    #       cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), zona['color'], 2)  

    #     elif FilasPersonas.box_dentro(box, zona['salida']):
    #       cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0,255,0), 2)      

    # cv2.putText(frame, str(numero), (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 255, 100), 2)      

    return len(objs), 0, frame