import { useState } from 'react';
import { deployFromGithub } from '../services/api';

export function useGithubDeploy() {
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState(null);

  function reset() { setResult(null); }

  async function deploy(name, plan, repoUrl, branch, extra = {}) {
    setLoading(true);
    setResult(null);
    try {
      const data = await deployFromGithub(name, plan, repoUrl, branch, extra);
      setResult({
        kind:       'success',
        hosting_id: data.hosting_id,
        subdomain:  data.subdomain,
        url:        data.url,
        ssl_status: data.ssl_status || 'online',
        message:    data.message,
      });
      return data;
    } catch (err) {
      const status = err.response?.status;
      const resp   = err.response?.data || {};
      const code   = resp.code   || '';
      const stage  = resp.stage  || '';
      const detail = resp.detail || '';

      let normalized;
      if (status === 429 || code === 'deploy_rate_limit_exceeded') {
        normalized = {
          kind:               'rate_limit',
          code,
          detail:             detail || 'Alcanzaste el límite de deploys por hora. Esperá unos minutos.',
          retry_after_seconds: resp.retry_after_seconds || 0,
        };
      } else if (code === 'deploy_runtime_missing_tool') {
        normalized = {
          kind:             'runtime_missing',
          code, stage, detail,
          suggested_fix:    resp.suggested_fix    || '',
          technical_detail: resp.technical_detail || '',
          evidence:         resp.evidence         || null,
          request_id:       resp.request_id       || '',
        };
      } else if (code && stage) {
        normalized = {
          kind:             'diagnostic',
          code, stage, detail,
          suggested_fix:    resp.suggested_fix    || '',
          technical_detail: resp.technical_detail || '',
          evidence:         resp.evidence         || null,
          request_id:       resp.request_id       || '',
        };
      } else if (!err.response) {
        normalized = {
          kind:   'network_error',
          detail: 'No pudimos contactar el servidor. Verificá tu conexión e intentá de nuevo.',
        };
      } else {
        let error = 'Error al crear el proyecto. Inténtalo de nuevo.';
        if (detail.includes('ya existe') || detail.includes('already exists'))
          error = 'Ya existe un proyecto con ese nombre.';
        else if (detail.includes('plan') || detail.includes('suscripción'))
          error = 'Tu plan actual no permite esta acción. Actualizá tu suscripción.';
        else if (detail.includes('IP') || detail.includes('free'))
          error = 'Solo se permite un alojamiento gratuito por dirección IP.';
        else if (detail.includes('nombre') || detail.includes('inválido'))
          error = 'Nombre de proyecto inválido. Usá solo letras, números y guiones.';
        else if (detail && (status === 422 || status === 400))
          error = detail;
        normalized = { kind: 'generic_error', error };
      }
      setResult(normalized);
      return null;
    } finally {
      setLoading(false);
    }
  }

  return { deploy, loading, result, reset };
}
