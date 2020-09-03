import compileall
import os
import glob
import shutil
import comun


rootdir = "/home/mendel/coral_contador/"
destdir = "/home/mendel/stella/"

res = compileall.compile_dir(rootdir, force=True, legacy=True)

print("\n\n\nCompilacion: ", res)

if res:
    # Mover Archivos
    for filename in glob.iglob(rootdir + '**/*.*', recursive=True):
        if "__pycache__" not in filename and \
            not filename.endswith(".py") and \
            ".code-workspace" not in filename and \
            "git" not in filename:

            destino = filename.replace(rootdir, destdir)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            print("Creando: " , destino)
            if filename.endswith(".pyc"):
                shutil.move(filename, destino)
            else:
                shutil.copy(filename, destino)
    
    #Subir cambios
    os.system("git -C %s add ." % destdir)
    os.system("git -C %s commit -m \"%s\"" % (destdir, "Produccion: " + comun.__VERSION__))
    os.system("git -C %s push" % destdir)
            

print("Fin!")