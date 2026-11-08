"""Restore only the recorded Wanbo settings. Default operation is read-only."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parent
STOCK_HOME = "com.google.android.tvlauncher/.MainActivity"
CUSTOM_HOME = "com.gathin.tvhome/.MainActivity"
PACKAGES = (
    "com.google.android.tvlauncher",
    "com.google.android.tvrecommendations",
    "com.google.android.feedback",
)
ORIGINAL = {
    "private_dns_mode": None,
    "private_dns_specifier": None,
    "window_animation_scale": "1.0",
    "transition_animation_scale": "1.0",
    "animator_duration_scale": None,
}
APPLIED = {
    "private_dns_mode": "hostname",
    "private_dns_specifier": "dns.adguard-dns.com",
    "window_animation_scale": "0.5",
    "transition_animation_scale": "0.5",
    "animator_duration_scale": "0.5",
}
COMPONENT = re.compile(r"^\s*([A-Za-z][\w.]*/[\w.$]+)\s*$", re.M)


class RestoreError(RuntimeError):
    pass


def canonical(component):
    package, activity = component.split("/", 1)
    return package + "/" + (package + activity if activity.startswith(".") else activity)


def load_profile(mode="base"):
    profile = json.loads((ROOT / "estado-base.json").read_text(encoding="utf-8-sig"))
    if (profile.get("schema_version") != 1 or profile.get("home") != STOCK_HOME
            or profile.get("packages") != dict.fromkeys(PACKAGES, 0)
            or profile.get("settings") != ORIGINAL):
        raise RestoreError("El perfil base no coincide con los cambios conocidos. No se aplicara.")
    if mode not in ("base", "menu"):
        raise RestoreError("Modo de restauracion desconocido.")
    profile["mode"] = mode
    profile["allowed_devices"] = [dict(profile["device"])]
    if mode == "menu":
        compatible = json.loads((ROOT / "compatibilidad-menu.json").read_text(encoding="utf-8-sig"))
        if compatible.get("schema_version") != 1:
            raise RestoreError("Perfil de compatibilidad de menu desconocido.")
        for firmware in compatible["additional_firmwares"]:
            if set(firmware) != {"sdk", "fingerprint"}:
                raise RestoreError("El perfil de menu solo puede ampliar la version de firmware.")
            device = dict(profile["device"])
            device.update(firmware)
            profile["allowed_devices"].append(device)
        profile["packages"] = {PACKAGES[0]: 0}
        profile["settings"] = {}
    return profile


class Adb:
    def __init__(self, executable, serial, port=5038, runner=subprocess.run):
        if not re.fullmatch(r"[A-Za-z0-9_.:\[\]-]+", serial or ""):
            raise RestoreError("Indica un identificador ADB valido, sin espacios ni comandos.")
        if not 1 <= port <= 65535:
            raise RestoreError("Puerto del servidor ADB invalido.")
        self.prefix = [str(executable), "-P", str(port), "-s", serial]
        self.runner = runner

    def run(self, *args):
        try:
            result = self.runner(self.prefix + list(args), capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=45)
        except FileNotFoundError as error:
            raise RestoreError("No se encuentra ADB. Instala Android Platform Tools o indica --adb.") from error
        except subprocess.TimeoutExpired as error:
            raise RestoreError("ADB no respondio a tiempo. No fuerces un reinicio.") from error
        output = result.stdout.strip()
        combined = output + "\n" + result.stderr
        if result.returncode or re.search(
                r"(?im)^\s*(?:error:|failure\b|exception\b|java\.[\w.]*Exception\b)", combined):
            raise RestoreError("Fallo ADB en " + " ".join(args[:4]) + ": " + combined.strip()[:300])
        return output

    def shell(self, *args):
        return self.run("shell", *args)


def package_state(adb, package):
    output = adb.shell("dumpsys", "package", package)
    user = re.search(r"(?m)^\s*User 0:([^\r\n]*)", output)
    if not user or "installed=true" not in user[1]:
        raise RestoreError("Falta una aplicacion original: " + package)
    if "hidden=true" in user[1] or "suspended=true" in user[1]:
        raise RestoreError("La aplicacion esta oculta o suspendida: " + package)
    if not re.search(r"(?m)^\s*(?:pkgFlags|flags)=\[[^\]]*\bSYSTEM\b", output):
        raise RestoreError("No se reconoce como aplicacion del sistema: " + package)
    match = re.search(r"\benabled=(\d+)\b", user[1])
    if not match:
        raise RestoreError("No se pudo leer el estado de " + package)
    return int(match[1])


def read_home(adb):
    output = adb.shell("cmd", "package", "resolve-activity", "--brief", "--user", "0",
                       "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")
    matches = COMPONENT.findall(output)
    if len(matches) != 1:
        raise RestoreError("No se pudo identificar un unico inicio activo.")
    return canonical(matches[0])


def read_setting(adb, key):
    value = adb.shell("settings", "get", "global", key)
    return None if value == "null" else value


def snapshot(adb, profile):
    if adb.run("get-state") != "device":
        raise RestoreError("El proyector no esta conectado o falta autorizar la depuracion.")
    properties = {"manufacturer": "ro.product.manufacturer", "model": "ro.product.model",
                  "device": "ro.product.device", "sdk": "ro.build.version.sdk",
                  "fingerprint": "ro.build.fingerprint"}
    actual = {key: adb.shell("getprop", prop) for key, prop in properties.items()}
    if not any(all(actual[key] == device[key] for key in properties)
               for device in profile["allowed_devices"]):
        raise RestoreError("Modelo o firmware distinto del perfil " + profile["mode"]
                           + " (API declarada " + actual["sdk"] + "). Nada modificado.")
    if adb.shell("am", "get-current-user") != "0":
        raise RestoreError("Solo se admite el usuario original 0. Nada modificado.")
    return {
        "home": read_home(adb),
        "packages": {package: package_state(adb, package) for package in profile["packages"]},
        "settings": {key: read_setting(adb, key) for key in profile["settings"]},
    }


def make_plan(before, profile=None):
    profile = profile if profile is not None else load_profile()
    targets = profile["settings"]
    if set(before["packages"]) != set(profile["packages"]) or set(before["settings"]) != set(targets):
        raise RestoreError("El estado leido no coincide con el alcance del perfil.")
    if before["home"] not in {canonical(STOCK_HOME), canonical(CUSTOM_HOME)}:
        raise RestoreError("Hay otro inicio elegido. Se detiene para no reemplazar un cambio posterior.")
    if any(state not in (0, 1, 3) for state in before["packages"].values()):
        raise RestoreError("Un paquete tiene un estado distinto del inicial o de nuestra desactivacion.")
    for key, value in before["settings"].items():
        if value != targets[key] and value != APPLIED[key]:
            raise RestoreError("El ajuste " + key + " cambio despues. No se sobrescribira automaticamente.")
    return {
        "packages": [package for package in profile["packages"] if before["packages"][package] != 0],
        "home": before["home"] != canonical(STOCK_HOME),
        "settings": [key for key in targets if before["settings"][key] != targets[key]],
    }


class Journal:
    def __init__(self, path, before, plan):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {"schema_version": 1, "status": "prepared", "before": before,
                     "plan": plan, "events": []}
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(self.data, stream, indent=2)

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def pending(self, action):
        self.data["status"] = "applying"
        self.data["events"].append({"action": action, "verified": False})
        self.save()

    def verified(self):
        self.data["events"][-1]["verified"] = True
        self.save()


def apply_restore(adb, profile, before, path):
    plan = make_plan(before, profile)
    targets = profile["settings"]
    if snapshot(adb, profile) != before:
        raise RestoreError("El estado cambio durante la confirmacion. Vuelve a revisar el plan.")
    journal = Journal(path, before, plan)
    try:
        # Bring back the stock HOME before touching the remaining preferences.
        for package in plan["packages"]:
            if package_state(adb, package) != before["packages"][package]:
                raise RestoreError("Cambio concurrente en " + package)
            journal.pending("default-state " + package)
            adb.shell("pm", "default-state", "--user", "0", package)
            if package_state(adb, package) != 0:
                raise RestoreError("No se restauro el estado de " + package)
            journal.verified()
        current_home = read_home(adb)
        if current_home not in {canonical(STOCK_HOME), canonical(CUSTOM_HOME)}:
            raise RestoreError("Cambio concurrente del inicio.")
        if current_home != canonical(STOCK_HOME):
            journal.pending("set-home-activity " + STOCK_HOME)
            adb.shell("cmd", "package", "set-home-activity", "--user", "0", STOCK_HOME)
            if read_home(adb) != canonical(STOCK_HOME):
                raise RestoreError("No se pudo elegir el inicio original.")
            journal.verified()
        journal.pending("open-stock-home")
        started = adb.shell("am", "start", "-W", "--user", "0", "-a", "android.intent.action.MAIN",
                            "-c", "android.intent.category.HOME", "-n", STOCK_HOME)
        if not re.search(r"(?im)^Status:\s*ok\s*$", started):
            raise RestoreError("El inicio original no confirmo su apertura. No se tocaran los demas ajustes.")
        if read_home(adb) != canonical(STOCK_HOME):
            raise RestoreError("El inicio original no quedo seleccionado.")
        journal.verified()
        for key in plan["settings"]:
            if read_setting(adb, key) != before["settings"][key]:
                raise RestoreError("Cambio concurrente en " + key)
            journal.pending("restore-setting " + key)
            if targets[key] is None:
                adb.shell("settings", "delete", "global", key)
            else:
                adb.shell("settings", "put", "global", key, targets[key])
            if read_setting(adb, key) != targets[key]:
                raise RestoreError("No se pudo verificar el ajuste " + key)
            journal.verified()
        after = snapshot(adb, profile)
        expected = {"home": canonical(STOCK_HOME), "packages": profile["packages"],
                    "settings": targets}
        if after != expected:
            raise RestoreError("La comprobacion final no coincide. Revisa el registro local.")
        journal.data.update(status="complete", after=after)
        journal.save()
        return after
    except (Exception, KeyboardInterrupt):
        journal.data["status"] = "interrupted"
        journal.save()
        raise


def print_plan(before, plan, profile):
    print("PLAN:", "solo menu original" if profile["mode"] == "menu" else "menu y ajustes iniciales",
          "del Wanbo (usuario 0).")
    print("Paquetes a devolver al estado predeterminado:", ", ".join(plan["packages"]) or "ninguno")
    print("Inicio:", before["home"], "->", canonical(STOCK_HOME))
    for key, value in profile["settings"].items():
        print(key + ":", repr(before["settings"][key]), "->", "sin valor fijado" if value is None else value)
    print("NO se borran apps, cuentas o datos. Truper no se modifica.")
    print("Inicio Comic y SmartTube se conservan como apps opcionales.")
    if profile["mode"] == "menu":
        print("No se leen ni cambian DNS, animaciones, recomendaciones o informes.")
    else:
        print("Al volver al DNS y recomendaciones originales puede reaparecer publicidad.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Revisar o restaurar los ajustes iniciales guardados del Wanbo.")
    parser.add_argument("--serial", required=True, help="Identificador ADB del proyector autorizado")
    parser.add_argument("--adb", default="adb", help="Ruta al ejecutable oficial de Android Platform Tools")
    parser.add_argument("--port", type=int, default=5038, help="Puerto local del servidor ADB (predeterminado 5038)")
    parser.add_argument("--mode", choices=["menu", "base"], default="menu",
                        help="menu: solo inicio original; base: todos los ajustes guardados de Android 11")
    parser.add_argument("--apply", action="store_true", help="Aplicar solo despues de confirmar el plan")
    parser.add_argument("--confirm", choices=["RESTAURAR"], help="Confirmacion explicita para uso no interactivo")
    args = parser.parse_args(argv)
    try:
        profile = load_profile(args.mode)
        adb = Adb(args.adb, args.serial, args.port)
        before = snapshot(adb, profile)
        plan = make_plan(before, profile)
        print_plan(before, plan, profile)
        if not args.apply:
            print("Solo lectura. No se modifico el proyector. Usa --apply para restaurar.")
            return 0
        if args.confirm != "RESTAURAR":
            if not sys.stdin.isatty():
                raise RestoreError("Falta confirmacion interactiva o --confirm RESTAURAR.")
            if input("Escribe RESTAURAR para aplicar; cualquier otra cosa cancela: ").strip() != "RESTAURAR":
                print("Cancelado. Ningun cambio aplicado.")
                return 0
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = ROOT / ".local" / ("restauracion-" + timestamp + "-" + uuid4().hex[:8] + ".json")
        apply_restore(adb, profile, before, path)
        print("Restauracion verificada. Registro local:", path)
        print("No es un restablecimiento de fabrica ni una restauracion del firmware.")
        return 0
    except (RestoreError, OSError, ValueError, KeyError, TypeError) as error:
        print("DETENIDO:", error, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrumpido. No reinicies a la fuerza; vuelve a revisar el plan.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
