import asyncio
import subprocess

async def get_container_logs(container_name: str, tail: int = 100) -> str:
    """
    Obtiene los logs sin procesar de un contenedor.
    Operación Read-Only.
    """
    loop = asyncio.get_running_loop()
    try:
        res = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_name],
                capture_output=True,
                text=True,
                timeout=5
            )
        )
        return res.stdout + "\n" + res.stderr
    except subprocess.TimeoutExpired:
        return "[LOG RETRIEVAL ERROR] Timeout al obtener logs"
    except Exception as e:
        return f"[LOG RETRIEVAL ERROR] {str(e)}"
