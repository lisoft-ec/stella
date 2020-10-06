import math
import numpy as np
import cv2
import datetime

class Persona:
    personas = []
    p_id = "P001"
    m_registro = False

    def __init__(self, rect, img=None, evt_cambio=None):
        super().__init__()
        p_id = Persona.p_id
        self.p_id = p_id

        p_id = int(p_id[1:]) + 1
        p_id = "P{0:03d}".format(p_id)
        Persona.p_id = p_id

        self.rect = rect
        self.por_eliminar = 0
        self.activa = 1
        self.usada = 1
        self.sale = 0
        self.entra = 0
        self.evt_cambio = evt_cambio
        
        self.color = (100,100,100)  
                                
        Persona.personas.append(self)
    
    def update(self, rect, piso):  
        umbral = int((piso[1] + piso[3]) / 2)
        umbral2 = umbral #int((piso[1] + piso[3]) / 2.7)

        print("UMBRAL: ", self.p_id, rect[3], umbral, umbral2, self.rect[3])

        if rect[3] >= umbral and self.rect[3] < umbral:
            self.entra += 1
            self.color = (0,255,0)
            if self.evt_cambio is not None:
                self.evt_cambio("entra")                

        if rect[3] < umbral2 and self.rect[3] >= umbral2:
            self.sale += 1
            self.color = (0,255,255)
            if self.evt_cambio is not None:
                self.evt_cambio("sale")

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
    def clear():
        for p in Persona.personas:            
            Persona.personas.remove(p)
            del p


    @staticmethod
    def asociar_objetos_rect(detectados, piso, evt_cambio=None):
        resultado = ""
        for p in Persona.personas:
            p.usada = 0

        if len(detectados) > 0 or len(Persona.personas) > 0:
            print()
            print("Detectadas:", len(detectados), "Existen: ", len(Persona.personas))

        for d in detectados:     
            cuerpo = d['hist']     

            candidatos = []
            for p in Persona.personas:
                if p.usada:
                    continue

                #cv2.compareHist(cuerpo, p.histo, cv2.HISTCMP_CORREL)
                factor = Persona.intersection_over_union(d['rect'], p.rect)
                if factor > 0.4:
                    candidatos.append({
                        'p': p,
                        'f': factor,
                    })
            
            if len(candidatos)==0:
                print("Creando persona")
                ps = Persona(d['rect'], evt_cambio=evt_cambio)

            elif len(candidatos) > 0:
                maximo = 0
                for c in candidatos:
                    if c['f'] >= maximo:
                        maximo = c['f']
                        ps = c['p']

                print("Actualizar a persona ", ps.p_id, "/ factor:", maximo, "/ dir: ", ps.entra, ps.sale)

                ps.update(d['rect'], piso) 
                ps.usada = 1
                ps.por_eliminar = 0
                ps.activa = 1
        
        # Revisar si hay q eliminar a las personas
        for p in Persona.personas:
            if not p.usada:
                p.por_eliminar += 1	
                print("Desactiva a persona:", p.p_id)
                p.activa = 0
                if p.por_eliminar > 5:
                    print("Registrar: ", p.p_id, p.entra, p.sale)
                    ####                    
                    estado = p.sale - p.entra
                    if estado != 0:                        
                        hoy = datetime.datetime.today()
                        hora = hoy.time()
                        hora = hora.hour + (hora.minute / 60.0) + (hora.second / 3600.0)

                        if p.entra > p.sale:
                            tipo = "in"
                        else:
                            tipo = "out"                          
                        
                        valores = {
                            'fecha': hoy.strftime("%Y-%m-%d"),
                            'hora': hora,
                            'zona_id': 2,
                            'tipo': tipo
                        }        
                        Persona.m_registro = Persona.conectar_odoo()
                        if Persona.m_registro:
                            r = Persona.m_registro.create(valores)
                            print("Guardado registro: ", tipo.upper(), r)                            
                    ####
                    print("Eliminando persona: ", p.p_id)
                    Persona.personas.remove(p)
                    del p

        return resultado

    @staticmethod
    def conectar_odoo():
        if Persona.m_registro:
            return Persona.m_registro
        else:
            Persona.m_registro = False
            try:
                #odoo = odoorpc.ODOO('aforo.silttec.com', protocol='jsonrpc+ssl', port=443)
                odoo = odoorpc.ODOO('localhost', port=8071)
                odoo.login('aforo', 'admin', 'stt030')
                Persona.m_registro =  odoo.env['aforo.registro']                
            except:
                print("Error al conectar con ODOO")
                pass
            
            return Persona.m_registro
        

##########################################################
        
   


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
            if p.activa == 0:
                continue

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

        umbral = int((piso[1] + piso[3]) / 2)
        cv2.rectangle(frameOver, (piso[0], piso[1]), (piso[2], piso[3]), (255, 0, 0), cv2.FILLED)
        cv2.line(frameOver, (0, umbral), (W, umbral), (255, 0, 255), 2)      

        return cv2.addWeighted(frameOver, alpha, img, 1-alpha, 0, img)
	

if __name__ == '__main__':
    print("Test")

    rect1 = (10,10,50,50)
    rect2 = (40,10,60,50)

    print(Persona.intersection_over_union(rect1, rect2))

    print("bye")