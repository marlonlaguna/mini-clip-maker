"""Activa masterizacion al terminar generar_video(), sin editar codigo del proyecto.

Python importa sitecustomize automaticamente al iniciar (si el directorio del
proyecto esta en sys.path). El hook solo actua sobre el modulo generar_video.
"""
import functools
import importlib.abc
import importlib.machinery
import inspect
import sys


class _VideoLoader(importlib.abc.Loader):
    def __init__(self, loader):
        self.loader = loader

    def create_module(self, spec):
        if hasattr(self.loader, "create_module"):
            return self.loader.create_module(spec)
        return None

    def exec_module(self, module):
        self.loader.exec_module(module)
        original = getattr(module, "generar_video", None)
        if not callable(original) or getattr(original, "_masterizacion_integrada", False):
            return

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)
            signature = inspect.signature(original)
            bound = signature.bind_partial(*args, **kwargs)
            ruta_video = bound.arguments.get("ruta_video")
            if ruta_video is None:
                raise RuntimeError("[MASTER] No se encontro el argumento ruta_video")
            from masterizacion_audio import masterizar_video
            masterizar_video(ruta_video)
            return result

        wrapper._masterizacion_integrada = True
        module.generar_video = wrapper
        print("[MASTER] Masterizacion automatica activada")


class _VideoFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "generar_video":
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _VideoLoader(spec.loader)
        return spec


if not any(isinstance(f, _VideoFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _VideoFinder())
