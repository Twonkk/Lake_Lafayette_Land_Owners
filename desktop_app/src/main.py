from src.app import launch
from src.runtime import ensure_runtime_dirs, resolve_app_paths
from src.services.logging_service import configure_logging, install_global_exception_logging


if __name__ == "__main__":
    paths = resolve_app_paths()
    ensure_runtime_dirs(paths)
    configure_logging(paths)
    install_global_exception_logging()
    launch()
