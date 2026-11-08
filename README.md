# Estado Base Del Proyector

Restaurador independiente de los ajustes guardados antes de personalizar
el Wanbo Vali 1. Sirve para volver al **menu original y a esos ajustes**,
sin borrar cuentas, sesiones, aplicaciones o datos personales.

**No es un firmware, una ROM, un restablecimiento de fabrica ni una copia
completa del proyector.** No puede recuperar archivos o apps que alguien
haya eliminado despues, ni devolver versiones antiguas de sus actualizaciones.

## Dos Modos, Sin Confundir Firmwares

En la comprobacion de publicacion, el equipo conectado declaraba Android 14
(API 34) y firmware `C1.6.4_20260723`. El punto inicial guardado corresponde
a Android 11 (API 30), firmware `P2.1.6_20240930`.

- `menu`, predeterminado: solo devuelve el menu original de Google. Admite
  exactamente los dos firmwares comprobados y conserva DNS, animaciones,
  recomendaciones y el resto de la optimizacion.
- `base`: devuelve tambien los ajustes detallados abajo. Solo admite el
  firmware original de Android 11. **Se bloquea en Android 14** para no
  aplicar valores de una version anterior a un sistema diferente.

No existe aqui una funcion para bajar de Android 14 a Android 11. Haria
falta un procedimiento oficial y firmware adecuado del fabricante; no
se intenta flashear ni improvisar esa recuperacion.

## Que Restaura

El modo `base` restaura:

- Inicio de Google / Pantalla principal de Android TV como menu predeterminado.
- Estado original de `com.google.android.tvlauncher`,
  `com.google.android.tvrecommendations` y `com.google.android.feedback`.
- DNS privado sin los valores fijados durante la personalizacion.
- Escalas de animacion: ventana `1.0`, transicion `1.0` y animador sin
  valor explicitamente fijado, tal como constaba en el registro inicial.

Se devuelve el estado de paquete `0` (predeterminado), no se inventa un
estado nuevo. `null` en `estado-base.json` significa **quitar el valor
explicitamente fijado** y dejar que Android use su configuracion normal.
Eso no significa bloquear Internet ni borrar los datos de la red Wi-Fi.

Al devolver las recomendaciones y el DNS originales puede reaparecer
publicidad. Las transiciones volveran a su velocidad anterior.

## Que Conserva

- Truper/Xuper, Spotify, Netflix, YouTube oficial, Play Store y el resto de apps.
- HDMI, Cast, Bluetooth, mando, enfoque, correccion geometrica y refrigeracion.
- Inicio Comic y SmartTube, instalados como aplicaciones opcionales.
- Las dos apps que ya estaban desactivadas antes de trabajar en el equipo:
  `com.google.android.tv.axel` y `com.homwee.howtocast` no se tocan.

No se ejecutan desinstalaciones, borrados de datos, root, cambios de
firmware, reinicios forzados ni modificaciones del router o de la TV LG.
Tampoco se instalan o redistribuyen APK del fabricante.

## Antes De Empezar

Necesitas Python 3.10 o posterior y las
[Android Platform Tools oficiales](https://developer.android.com/tools/releases/platform-tools).
El script usa solo la biblioteca estandar de Python; no requiere pip.
El proyector debe estar encendido y la depuracion autorizada para tu PC.

Se comprueba el modelo interno SkyworthDigital / TV Stick / BOS,
el firmware correspondiente al modo y el usuario 0. Si no coinciden,
se detiene. No anules esta comprobacion para otro equipo o firmware.

Consulta el identificador en tu conexion ADB. No se publica en este
repositorio la direccion privada de tu proyector. `SERIAL_DEL_PROYECTOR`
en los ejemplos es un marcador que debes sustituir, no una direccion real.
El servidor ADB local usa el puerto `5038`; el puerto de la conexion
del proyector y el puerto del servidor local no son lo mismo.

```powershell
adb -P 5038 devices
```

Si hace falta, conecta antes el equipo siguiendo la
[guia oficial de ADB](https://developer.android.com/tools/adb).
Autoriza solo tu PC y no abras los puertos de depuracion a Internet.

## Revisar Sin Cambiar Nada

Abre `VER-PLAN.bat`, o ejecuta desde esta carpeta:

```powershell
python restaurar.py --serial SERIAL_DEL_PROYECTOR
```

No uses `--apply` hasta revisar el plan. El modo predeterminado solo lee
el modelo, firmware, usuario, inicio y los ajustes necesarios.

## Restaurar Cuando Lo Decidas

Abre `RESTAURAR.bat` para recuperar **solo el menu**. Veras el plan y
deberas escribir **RESTAURAR** para confirmar. Tambien puedes usar:

```powershell
python restaurar.py --serial SERIAL_DEL_PROYECTOR --apply
```

Para revisar todos los ajustes del punto inicial de Android 11:

```powershell
python restaurar.py --serial SERIAL_DEL_PROYECTOR --mode base
```

Solo en el firmware original, agrega `--apply` para aplicarlos. En
PowerShell el equivalente es `-Mode base -Apply`. Ninguna opcion permite
saltarse la comprobacion de firmware.

En una terminal no interactiva hace falta ademas `--confirm RESTAURAR`.
Para indicar rutas o un puerto de servidor ADB distinto:

```powershell
.\Restaurar-Wanbo.ps1 -Serial SERIAL_DEL_PROYECTOR -Adb 'C:\Ruta\adb.exe' -PythonExe 'C:\Ruta\python.exe' -AdbPort 5038
```

Este ultimo ejemplo **solo revisa**. Agrega `-Apply` para solicitar aplicar.
En Linux/macOS usa directamente el comando de Python y tu ejecutable ADB.

## Comprobaciones Y Fallos

Antes de escribir, el script comprueba que los valores sean los originales
o los que establecimos. Si detecta otro DNS, un tercer inicio o cambios
posteriores, se detiene para no reemplazarlos sin revision.

Antes de aplicar crea un registro en `.local`, con los valores concretos
de esta restauracion. No lo publiques: podria incluir un DNS personalizado.
No se guardan contrasenas, cuentas ni la direccion de conexion en ese registro.
Cada paso se verifica. Si falla, no borra nada para intentar arreglarlo ni
fuerza un reinicio. Conserva la carpeta y vuelve a revisar el plan.

La opcion manual para volver solo al menu sigue siendo Ajustes > Inicio
original > Habilitar, dentro de Inicio Comic. Esa opcion por si sola no
restaura DNS, animaciones o recomendaciones.

## Alcance Del Respaldo

`estado-base.json` es una seleccion anonimizada del registro local
anterior a la personalizacion del 7 de noviembre de 2026. Contiene solo
datos comunes del modelo/firmware, el inicio y los ocho ajustes o estados
a restaurar. `compatibilidad-menu.json` registra solo la version adicional
comprobada para el modo menu, no una nueva linea base de ajustes.
Los registros completos originales, claves, cuentas, red, numero de serie
fisico, capturas y rutas personales no se incluyen.

La herramienta anterior se probo en el equipo y despues se reaplico la
personalizacion. Este restaurador independiente dispone de pruebas
automatizadas; su publicacion **no implica haberlo ejecutado en modo
aplicacion ahora**. No se revierte tu inicio cinematografico al subirlo.

```powershell
python -m unittest discover -s tests -v
```

Los comandos de estado de paquetes e inicio se apoyan en la
[implementacion de Android 11](https://android.googlesource.com/platform/frameworks/base/+/android11-release/services/core/java/com/android/server/pm/PackageManagerShellCommand.java).
