import time


class RestartServiceExecutor:
    """
    Ejecutor para reiniciar servicios de forma segura.
    """

    def dry_run(self, action: dict) -> bool:
        # Verifica que el nombre del servicio esté presente
        return action.get("service_name") is not None

    def execute(self, action: dict) -> bool:
        # Simulación de reinicio seguro (v1)
        # En el futuro aquí iría la llamada a SSH / API del hosting
        time.sleep(0.2)
        return True

    def rollback(self, action: dict) -> None:
        # En el caso de reinicio, el rollback suele ser otro reinicio
        # o no hacer nada si el servicio ya está arriba.
        time.sleep(0.2)


class ClearCacheExecutor:
    """
    Ejecutor para limpiar caché (v1).
    """

    def dry_run(self, action: dict) -> bool:
        return "cache_type" in action

    def execute(self, action: dict) -> bool:
        time.sleep(0.1)
        return True

    def rollback(self, action: dict) -> None:
        # La limpieza de caché no suele ser reversible fácilmente
        pass


class RollbackDeployExecutor:
    """
    Ejecutor para revertir despliegues (v1).
    """

    def dry_run(self, action: dict) -> bool:
        # Siempre permitimos dry-run de rollback en v1 para simulación
        return True

    def execute(self, action: dict) -> bool:
        time.sleep(0.5)
        return True

    def rollback(self, action: dict) -> None:
        # El rollback de un rollback es complejo, v1 sin acción
        pass
