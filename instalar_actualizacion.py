"""Retira únicamente fuentes obsoletas idénticas a la versión sustituida."""
from pathlib import Path
import hashlib

OBSOLETE_DIGESTS = {"1e4e79f9f200c9ae37c12e224ff79984327844322718bb27a73cbff52f7cf00a"}


def retirar_archivos_obsoletos(base=None):
    base = Path(base) if base is not None else Path(__file__).resolve().parent
    removed = []
    for path in base.glob("*.py"):
        try:
            content = path.read_bytes().removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
            if hashlib.sha256(content).hexdigest() in OBSOLETE_DIGESTS:
                path.unlink()
                removed.append(path.name)
                for cache in (base / "__pycache__").glob(path.stem + ".*.pyc"):
                    cache.unlink(missing_ok=True)
                print(f"[ACTUALIZACION] Retirado módulo obsoleto: {path.name}")
        except OSError as exc:
            print(f"[ACTUALIZACION] AVISO: no se pudo revisar/retirar {path.name}: {exc}")
    return removed


if __name__ == "__main__":
    count = len(retirar_archivos_obsoletos())
    print(f"[ACTUALIZACION] Limpieza terminada: {count} módulos retirados.")
