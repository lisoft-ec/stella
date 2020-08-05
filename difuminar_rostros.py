import cv2
import numpy as np

print("**********INICIANDO*************")

vs = cv2.VideoCapture("/home/almustafa/Vídeos/out_1.avi")

print("OPENCV version: ", cv2.__version__)

haar_cascade_face = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

while True:
    (grabbed, frame) = vs.read()     

    if not grabbed:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)    
    mascara = np.zeros_like(gray)

    faces_rects = haar_cascade_face.detectMultiScale(gray, scaleFactor=1.3, 
                                 minNeighbors=5, 
                                 minSize=(3, 3),
                                 flags=cv2.CASCADE_SCALE_IMAGE)

    img2 = cv2.GaussianBlur(frame,(51,51),0)

    for (x,y,w,h) in faces_rects:
        #rostro = frame[y:y+h, x:x+w]
        #rostro = cv2.GaussianBlur(rostro,(21,21),0)
        #cv2.imshow("R", rostro)
        cv2.circle(frame, (int(x+(w/2)), int(y+(h/2))), int(w/2), (0, 0, 0), -1)
        cv2.circle(mascara, (int(x+(w/2)), int(y+(h/2))), int(w/2), (255, 255, 255), -1)
        cv2.circle(frame, (int(x+(w/2)), int(y+(h/2))), int(w/2), (0, 255, 0), 2)
          
    
    img2 = cv2.bitwise_and(img2, img2, mask=mascara)

    #cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
    #cv2.imshow("Mask", mascara)
    cv2.imshow("Frame", frame + img2)

    key = cv2.waitKey() & 0xFF   
    if key == ord("q"):
      break   

vs.release()
cv2.destroyAllWindows()    

print("*************FIN****************")