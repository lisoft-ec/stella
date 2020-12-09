import os
import time
import subprocess
import shutil

comunicacion = False
actualizacion = False

carpeta_stella = '/home/mendel/stella/'
carpeta_backup = '/home/mendel/bk_stella/'


def revisar_actualizaciones():
    command = "git -C %s remote update" % carpeta_stella
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()

    if output == b'Fetching origin\n':        
        print("Con comunicación al GIT")

        command = "git -C %s status" % carpeta_stella
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output, error = process.communicate()
        

        if error == b'' and b'(use "git pull" to update your local branch)' in output:            
            print("Con Actualización")
            # eliminar carpeta        
            shutil.rmtree(carpeta_backup, ignore_errors=True)
            # Sacar respaldo
            res = shutil.copytree(carpeta_stella, carpeta_backup, ignore=shutil.ignore_patterns('inicio.pyc'))
            print("Sacar respaldo: " , res)

            # GIT: Actualizaciones
            command = "git -C %s pull" % carpeta_stella
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            output, error = process.communicate()
            time.sleep(2)

            return True
        else:
            print("Sin Actualización")
            return False
    else:
        print("Sin Comunicación por GIT")
        return False


actualizacion = revisar_actualizaciones()
    
print("Arranco el Programa")

os.system("sudo service programa start")
time.sleep(10)

command = "sudo service programa status"
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
output, error = process.communicate()
lineas = output.split(b'\n')

arraque_normal = True

for l in lineas:
    l = l.strip()

    if l.startswith(b'Active:'):
        arraque_normal = b'inactive' not in l
        break

if not arraque_normal:
    print("Algún problema al arrancar programa.\nRestauro backup")
    os.system("sudo service programa stop")
    time.sleep(3)

    # Copio y Elimino archivos desde el BackUp
    for (dirpath, dirnames, filenames) in os.walk(carpeta_backup):
        if not dirpath.endswith('/'):
            dirpath += '/'

        dirO = dirpath
        dirD = dirO.replace(carpeta_backup, carpeta_stella)
        if not os.path.exists(dirD):
            os.mkdir(dirD)
            print("Creando: ", dirD)

        for name in filenames:
            archivoO = dirpath + name 
            archivoD = archivoO.replace(carpeta_backup, carpeta_stella)

            os.system("sudo cp %s %s" % (archivoO, archivoD)) 
            print("Copiando: ", archivoO, archivoD)

    print("Intentar arrancar desde el backup ya restaurado")
    os.system("sudo chown mendel:mendel -Rf %s" % carpeta_stella)
    time.sleep(2)
    os.system("sudo service programa start")
    time.sleep(2)

print("Fin!")
