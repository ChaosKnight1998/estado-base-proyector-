# Verificacion De Publicacion

- 39 pruebas automatizadas con `unittest`, sin fallos.
- Sintaxis PowerShell comprobada con el analizador de PowerShell.
- Estado base publico cotejado con el registro original local: inicio,
  tres estados de paquetes y cinco valores de ajustes.
- Se comprobo por lectura la identificacion del equipo conectado:
  Android 14 / API 34, firmware `C1.6.4_20260723`.
- El modo base de Android 11 se detuvo sin aplicar cambios, como estaba previsto.
- El modo menu completo su comprobacion real en solo lectura.

Las pruebas simuladas cubren restauracion exacta, modos separados,
seleccion explicita del equipo, usuario, firmware, confirmacion,
cancelacion, registro previo, interrupciones, fallos de escritura,
concurrencia, DNS posterior no sobrescrito y paquetes no modificados.

No se ejecuto `--apply` en el proyector durante esta publicacion. El
inicio cinematografico, Truper y el resto de ajustes permanecen como
estaban. La apertura real del menu tras aplicar esta version queda
pendiente de una futura restauracion solicitada por el propietario.

No se publica la direccion de conexion, la huella de un equipo fisico,
cuentas, registros privados o la copia original completa. Las huellas
de compilacion incluidas son comunes del modelo y version de firmware.
