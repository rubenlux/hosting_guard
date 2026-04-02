import time
import logging
import subprocess
from app.core.execution.interfaces import BaseExecutor

logger = logging.getLogger(__name__)

class RestartServiceExecutor(BaseExecutor):
    """
    Ejecutor para reiniciar servicios de forma segura llamando a docker restart.
    """

    def dry_run(self, action: dict) -> bool:
        service_name = action.get("service_name")
        valid = isinstance(service_name, str) and len(service_name.strip()) > 0
        if not valid:
            logger.warning(f"Dry run fallido [RestartServiceExecutor]. Parámetros inválidos: {action}")
        return valid

    def execute(self, action: dict) -> bool:
        container = action.get("service_name").strip()
        logger.info(f"Iniciando RestartServiceExecutor para: {container}")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ["docker", "restart", container],
                    capture_output=True,
                    timeout=30
                )
                if result.returncode == 0:
                    logger.info(f"[ÉXITO] Contenedor {container} reiniciado.")
                    return True
                
                logger.warning(f"Error reiniciando {container} (Intento {attempt+1}/{max_retries}): {result.stderr.decode('utf-8', errors='replace')}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout al reiniciar {container} (Intento {attempt+1}/{max_retries}).")
            except Exception as e:
                logger.error(f"Excepción reiniciando {container}: {e}", exc_info=True)
                
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Backoff exponencial: 1s, 2s...
                
        logger.error(f"RestartServiceExecutor falló definitivamente tras {max_retries} intentos para {container}.")
        return False

    def rollback(self, action: dict) -> None:
        logger.info(f"Rollback invocado para RestartServiceExecutor en {action.get('service_name')}")


class ClearCacheExecutor(BaseExecutor):
    """
    Ejecutor para limpiar caché usando docker exec nginx -s reload.
    """

    def dry_run(self, action: dict) -> bool:
        container = action.get("container_name")
        valid = bool(container) and bool(action.get("cache_type"))
        if not valid:
            logger.warning(f"Dry run fallido [ClearCacheExecutor]. Faltan datos: {action}")
        return valid

    def execute(self, action: dict) -> bool:
        container = action.get("container_name").strip()
        cache_type = action.get("cache_type")
        logger.info(f"Iniciando ClearCacheExecutor para {container} (Tipo: {cache_type})")
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ["docker", "exec", container, "nginx", "-s", "reload"],
                    capture_output=True,
                    timeout=20
                )
                if result.returncode == 0:
                    logger.info(f"[ÉXITO] Caché limpiada y Nginx recargado en {container}.")
                    return True
                
                logger.warning(f"Error limpiando caché en {container} (Intento {attempt+1}/{max_retries}): {result.stderr.decode('utf-8', errors='replace')}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout al limpiar caché en {container} (Intento {attempt+1}/{max_retries}).")
            except Exception as e:
                logger.error(f"Excepción limpiando caché en {container}: {e}", exc_info=True)
                
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                
        logger.error(f"ClearCacheExecutor falló definitivamente tras {max_retries} intentos para {container}.")
        return False

    def rollback(self, action: dict) -> None:
        # La limpieza de caché no es reversible, pero sí debe quedar registrado
        logger.warning(f"Rollback de ClearCache invocado para {action.get('cache_type')} en {action.get('container_name')} — no reversible.")


class RollbackDeployExecutor(BaseExecutor):
    """
    Ejecutor para revertir despliegues operando checkout a una versión anterior.
    """

    def dry_run(self, action: dict) -> bool:
        valid = bool(action.get("container_name")) and bool(action.get("previous_version"))
        if not valid:
            logger.warning(f"Dry run fallido [RollbackDeployExecutor]. Parámetros incompletos: {action}")
        return valid

    def execute(self, action: dict) -> bool:
        container = action.get("container_name").strip()
        version = action.get("previous_version").strip()
        logger.info(f"Iniciando RollbackDeployExecutor en {container} destino a versión {version}")
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ["docker", "exec", container, "git", "checkout", version],
                    capture_output=True,
                    timeout=45
                )
                if result.returncode == 0:
                    logger.info(f"[ÉXITO] Rollback a versión {version} completado en {container}.")
                    return True
                
                logger.warning(f"Error revirtiendo {container} a versión {version} (Intento {attempt+1}/{max_retries}): {result.stderr.decode('utf-8', errors='replace')}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout al revertir despliegue en {container} (Intento {attempt+1}/{max_retries}).")
            except Exception as e:
                logger.error(f"Excepción en RollbackDeployExecutor para {container}: {e}", exc_info=True)
                
            if attempt < max_retries - 1:
                time.sleep(3)
                
        logger.error(f"RollbackDeployExecutor falló tras {max_retries} intentos para {container}.")
        return False

    def rollback(self, action: dict) -> None:
        logger.warning(f"Rollback de RollbackDeployExecutor invocado para {action.get('container_name')} — requiere revisión manual urgente.")

