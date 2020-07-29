import math
import numpy as np
import cv2
import datetime

class Persona:
    personas = []
    p_id = "A"

    def __init__(self, rect, img=None):
        super().__init__()
        self.p_id = Persona.p_id
        Persona.p_id = chr(ord(Persona.p_id)+1)
        if Persona.p_id == "Z":
            Persona.p_id = "A"

        self.rect = rect
        self.por_eliminar = 0
        self.activa = 1
        self.usada = 1
        self.sale = 0
        self.entra = 0
        
        #self.puntos = []
        #self.color = np.uint8(np.random.uniform(0, 255, 3))
        self.color = (100,100,100)  #  tuple(map(int, self.color))    
        # if img not is None:
        #     self.img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        #     edge_mask = np.zeros_like(self.img)
        #     cv2.rectangle(edge_mask, (rect[0], rect[1]), (rect[2], rect[3]), 255, cv2.FILLED)    
        #     self.keys = cv2.goodFeaturesToTrack(self.img, 200, 0.05, 5, mask=edge_mask)
                                
        Persona.personas.append(self)
    
    def update(self, rect):  
        if rect[1] > self.rect[1] and rect[3] > self.rect[3]:
            self.entra += (rect[1] - self.rect[1]) + (rect[3] - self.rect[3])
            
        elif rect[1] < self.rect[1] and rect[3] < self.rect[3]:            
            self.sale += (self.rect[1] - rect[1]) + (self.rect[3] - rect[3])            

        if (self.entra - self.sale) > 0:
            self.color = (0,255,0)
        else:
            self.color = (0,255,255)
        

        # if self.direccion == 0:
        #     self.direccion = 1 if direccion < 0 else -1

        # if self.direccion != direccion:
        #     self.cambio += 1
        #     print("Cambio?: ", self.direccion, direccion, self.cambio)
        #     if self.cambio >= 3:
        #         # Cambio de dirección                
        #         respuesta = direccion
        #         self.direccion = direccion
        #         self.color = (0,255,0) if self.direccion > 0 else (0,255,255)
        # else:
        #     self.cambio = 0     
        #     # Aun no definido si entra o no
        #     if self.color == (100,100,100):
        #         self.direccion = 0

        self.rect = rect
        self.activa = 1                
        #self.puntos.append(pto)
        return 0

    @staticmethod
    def distancia_puntos(pto1, pto2):
        x = abs(pto1[0] - pto2[0])
        y = abs(pto1[1] - pto2[1])
        return math.sqrt(x**2 + y**2)

    @staticmethod
    def intersection_over_union(boxA, boxB):
        # determine the (x, y)-coordinates of the intersection rectangle
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        # compute the area of intersection rectangle
        interArea = abs(max((xB - xA, 0)) * max((yB - yA), 0))
        if interArea == 0:
            return 0
        # compute the area of both the prediction and ground-truth
        # rectangles
        boxAArea = abs((boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
        boxBArea = abs((boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))

        # compute the intersection over union by taking the intersection
        # area and dividing it by the sum of prediction + ground-truth
        # areas - the interesection area
        iou = interArea / float(boxAArea + boxBArea - interArea)

        # return the intersection over union value
        return iou

    @staticmethod
    def get_histograma(img, rect):
        roi = img[rect[1]:rect[3], rect[0]:rect[2]]
        hist = cv2.calcHist([roi], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        return cv2.normalize(hist, hist).flatten()
   
    @staticmethod
    def clear():
        for p in Persona.personas:            
            Persona.personas.remove(p)
            del p

    @staticmethod
    def asociar_objetos_hist(detectados, img, conteo_personas):   
        # Para eliminar
        for p in Persona.personas:
            p.por_eliminar += 1	
        
        for d in detectados:
            d_hist = Persona.get_histograma(img, d['rect'])
            
            #print()
            #print("Detectado:")
            candidatos = []
            for p in Persona.personas:
                if p.por_eliminar == 0:
                    continue
                
                p_hist = Persona.get_histograma(img, p.rect)
                
                correlacion = cv2.compareHist(p_hist, d_hist, cv2.HISTCMP_CORREL)
                #print("Corr: ", correlacion)
                
                #if minimo < 0 or (correlacion < minimo and dist < 100):
                if correlacion > 0.9:                    
                    candidatos.append({
                        'p': p,
                        'corr': correlacion,
                        'dist': Persona.distancia_puntos(d['pto'], p.punto),
                    })

                #over = Persona.intersection_over_union(d['rect'], p.rect)
                #print(over)
                #if (len_resultados == 1 and over >= 0.1) or (len_resultados > 1 and over >= 0.7):   
                                
            if len(candidatos) == 0:
                ps = Persona(d['rect'], d['pto'], img)
            elif len(candidatos) == 1:
                ps = candidatos[0]['p']
                ps.update(d['rect'], d['pto'])  
                ps.por_eliminar = 0                   
            else:
                minimo = -1
                print()
                print("Varios:")
                for c in candidatos:
                    print("Corr: ", c['corr'], "Dist:", c['dist'])
                    if minimo < 0 or c['dist'] < minimo:
                        minimo = c['dist']
                        ps = c['p']
                
                ps.update(d['rect'], d['pto'])  
                ps.por_eliminar = 0                
            

                
        
        # Revisar para eliminar
        for p in Persona.personas:
            #print("Reviso eliminar: ", p.por_eliminar)
            if p.por_eliminar > 5:
                Persona.personas.remove(p)
                del p
        
        return conteo_personas

    @staticmethod
    def asociar_objetos_rect(detectados, piso, m_registro):
        resultado = ""
        for p in Persona.personas:
            p.usada = 0

        if len(detectados) > 0 or len(Persona.personas) > 0:
            print()
            print("Detectadas:", len(detectados), "Existen: ", len(Persona.personas))

        for d in detectados:            
            candidatos = []
            for p in Persona.personas:
                if p.usada:
                    continue

                factor = Persona.intersection_over_union(d['rect'], p.rect)
                if factor > 0.4:
                    candidatos.append({
                        'p': p,
                        'f': factor,
                    })
            
            if len(candidatos)==0:
                print("Creando persona")
                ps = Persona(d['rect'])

            elif len(candidatos) > 0:
                maximo = 0
                for c in candidatos:
                    if c['f'] >= maximo:
                        maximo = c['f']
                        ps = c['p']

                print("Actualizar a persona ", ps.p_id, "/ factor:", maximo, "/ dir: ", ps.entra, ps.sale)

                res = ps.update(d['rect']) 
                ps.usada = 1
                ps.por_eliminar = 0	
                ps.activa = 1
                if res > 0:
                    resultado = "ENTRA"
                elif res < 0:
                    resultado = "SALE"
        
        # Revisar si hay q eliminar a las personas
        for p in Persona.personas:
            if not p.usada:
                p.por_eliminar += 1	
                print("Desactiva a persona:", p.p_id)
                p.activa = 0
                if p.por_eliminar > 5:
                    print("Registrar: ", p.p_id, p.entra, p.sale)
                    ####                    
                    if ((p.entra * 0.5) > p.sale) or ((p.sale * 0.5) > p.entra):
                        if p.entra > 10 or p.sale > 10:
                            hoy = datetime.datetime.today()
                            hora = hoy.time()
                            hora = hora.hour + (hora.minute / 60.0) + (hora.second / 3600.0)

                            if (p.entra * 0.5) > p.sale:
                                tipo = "in"
                            else:
                                tipo = "out"                          
                            
                            valores = {
                                'fecha': hoy.strftime("%Y-%m-%d"),
                                'hora': hora,
                                'zona_id': 1,
                                'tipo': tipo
                            }        
                            r = m_registro.create(valores)

                            print("Guardado registro: ", tipo.upper(), r)
                    ####
                    print("Eliminando persona: ", p.p_id)
                    Persona.personas.remove(p)
                    del p

        return resultado
        
    @staticmethod
    def asociar_objetos(detectados, img, conteo_personas):   
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        lk_params = dict( winSize  = (15,15),
                  maxLevel = 2,
                  criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))

        print()
        print("Detectadas:", len(detectados), "Existen: ", len(Persona.personas))
        for p in Persona.personas:
            old_keys = np.asarray(p.keys, dtype=np.float32)
            if not old_keys.any():
                continue
              
            p1, st, err = cv2.calcOpticalFlowPyrLK(p.img, g, old_keys, None, **lk_params) 
            good_new = p1[st == 1]
            maximo = 0
            ds = None
            candidatos = []
            for d in detectados:
                if d['usado'] == 1:
                    continue

                coinciden = 0
                for i in good_new:
                    x,y = i.ravel()
                    rect = d['rect']
                    if rect[0] < x < rect[2] and rect[1] < y < rect[3]:
                        coinciden+=1

                factor = coinciden / len(good_new)
                
                if factor > 0.5:
                    candidatos.append({
                        'd': d,
                        'f': factor,
                    })
            
            print("Persona: ", p.p_id, "Candidatos: ", [c['f'] for c in candidatos])
            if len(candidatos) > 0:
                maximo = 0
                for d in candidatos:
                    if d['f'] > maximo:
                        maximo = d['f']
                        ds = d['d']

                print("Actualizar a persona ", p.p_id)
                ds['usado'] = 1
                p.update(ds['rect'], ds['pto']) 
                p.img = g
                roi = g[p.rect[1]:p.rect[3], p.rect[0]:p.rect[2]]                
                p.keys = np.int0(cv2.goodFeaturesToTrack(roi, 200, 0.05, 5)) + (p.rect[0], p.rect[1])
            else:
                print("desactivar a persona ", p.p_id)
                p.activa = 0

        for d in detectados:
            if d['usado'] == 0:
                print("Creando persona")
                Persona(d['rect'], d['pto'], img)
                                            
        
        return conteo_personas   


    @staticmethod
    def rounded_rectangle(src, top_left, bottom_right, radius=1, color=255, thickness=1, line_type=cv2.LINE_AA):
        #  corners:
        #  p1 - p2
        #  |     |
        #  p4 - p3

        p1 = top_left
        p2 = (bottom_right[0], top_left[1])
        p3 = bottom_right
        p4 = (top_left[0], bottom_right[1])

        height = abs(bottom_right[1] - top_left[1])

        # Radio es porcentaje 
        if radius > 1:
            radius = 1

        corner_radius = int(radius * (height/2))
        
        # draw straight lines
        cv2.line(src, (p1[0] + corner_radius, p1[1]), (p2[0] - corner_radius, p2[1]), color, abs(thickness), line_type)
        cv2.line(src, (p2[0], p2[1] + corner_radius), (p3[0], p3[1] - corner_radius), color, abs(thickness), line_type)
        cv2.line(src, (p3[0] - corner_radius, p4[1]), (p4[0] + corner_radius, p3[1]), color, abs(thickness), line_type)
        cv2.line(src, (p4[0], p4[1] - corner_radius), (p1[0], p1[1] + corner_radius), color, abs(thickness), line_type)

        # draw arcs
        cv2.ellipse(src, (p1[0] + corner_radius, p1[1] + corner_radius), (corner_radius, corner_radius), 180.0, 0, 90, color ,thickness, line_type)
        cv2.ellipse(src, (p2[0] - corner_radius, p2[1] + corner_radius), (corner_radius, corner_radius), 270.0, 0, 90, color , thickness, line_type)
        cv2.ellipse(src, (p3[0] - corner_radius, p3[1] - corner_radius), (corner_radius, corner_radius), 0.0, 0, 90,   color , thickness, line_type)
        cv2.ellipse(src, (p4[0] + corner_radius, p4[1] - corner_radius), (corner_radius, corner_radius), 90.0, 0, 90,  color , thickness, line_type)

        return src

    @staticmethod
    def dibujar(img, piso, alpha=0.1):   
        frameOver = img.copy()       

        (H, W) = img.shape[:2]
        
        for p in Persona.personas:	
            #if p.activa == 0 or p.direccion == 0:
            #    continue

            Persona.rounded_rectangle(img, (p.rect[0], p.rect[1]), (p.rect[2], p.rect[3]), 0.2, p.color, 2)           
            cv2.rectangle(frameOver, (p.rect[0], p.rect[1]), (p.rect[2], p.rect[3]), p.color, -1)	

            #cv2.putText(img, p.p_id, ((p.rect[0] + p.rect[2]) // 2, p.rect[1] + 17), cv2.FONT_HERSHEY_SIMPLEX , 0.8, p.color, 2)
            
            # keys = np.int0(p.keys)
            # for i in keys:
            #     x,y = i.ravel()
            #     cv2.circle(img,(x,y),3,p.color,-1)

            # pto_ant = False
            # for pto in p.puntos:		
            #     if not pto_ant:
            #         pto_ant = pto
            #     else:
            #         cv2.line(img, pto_ant, pto, p.color, 2)	
            #         pto_ant = pto
            #     #cv2.circle(img, pto , 5, p.color , 1)

        cv2.rectangle(frameOver, (piso[0], piso[1]), (piso[2], piso[3]), (255, 0, 0), cv2.FILLED)
        #cv2.line(frameOver, (0, linea), (W, linea), (0, 255, 255), 5)      

        cv2.addWeighted(frameOver, alpha, img, 1-alpha, 0, img)
	

if __name__ == '__main__':
    print("Test")

    rect1 = (10,10,50,50)
    rect2 = (40,10,60,50)

    print(Persona.intersection_over_union(rect1, rect2))

    print("bye")