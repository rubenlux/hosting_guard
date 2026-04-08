import subprocess
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class ContainerService:
    @staticmethod
    def get_container_stats(container_id: str) -> Optional[Dict]:
        """Obtiene estadísticas de un contenedor vía docker stats."""
        try:
            result = subprocess.run(
                ["docker", "stats", container_id, "--no-stream", "--format", "{{json .}}"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
        except Exception as e:
            logger.error(f"Error getting stats for {container_id}: {e}")
        return None

    @staticmethod
    def restart_container(container_id: str) -> bool:
        """Reinicia un contenedor."""
        try:
            result = subprocess.run(["docker", "restart", container_id], capture_output=True, timeout=30)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error restarting {container_id}: {e}")
            return False

    @staticmethod
    def get_logs(container_id: str, tail: int = 100) -> str:
        """Obtiene los últimos logs de un contenedor."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_id],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout + result.stderr
        except Exception as e:
            logger.error(f"Error getting logs for {container_id}: {e}")
            return f"Error: {e}"
