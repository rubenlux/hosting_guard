import React from 'react';
import { AlertTriangle, Wrench, Zap } from 'lucide-react';
import DeployErrorDetails from './DeployErrorDetails';

const CODE_LABELS = {
  github_repo_not_found:            'Repositorio no encontrado',
  github_private_repo_unauthorized: 'Repositorio privado sin permisos',
  github_branch_not_found:          'Branch no encontrada',
  github_clone_timeout:             'Clone demoró demasiado',
  invalid_repo_url:                 'URL de repositorio inválida',
  package_json_not_found:           'No se encontró package.json',
  multiple_project_roots_detected:  'Múltiples proyectos detectados',
  build_script_missing:             'Script build no encontrado',
  node_sass_incompatible:           'Dependencia incompatible: node-sass',
  package_manager_pnpm_detected:    'pnpm no disponible en el build',
  package_manager_yarn_detected:    'Yarn no disponible en el build',
  node_version_mismatch:            'Versión de Node incompatible',
  next_ssr_not_supported:           'Next.js SSR no soportado',
  dependency_version_not_found:     'Versión de dependencia no encontrada',
  module_not_found_build:           'Módulo no encontrado en el build',
  openssl_build_failed:             'Error de compatibilidad OpenSSL',
  index_html_not_found:             'Build sin index.html',
  multiple_output_directories:      'Múltiples salidas de build',
  unsafe_publish_root:              'Directorio de publicación inseguro',
  ssl_provisioning_timeout:         'SSL en proceso de activación',
};

export default function DeployDiagnosticCard({ errorData }) {
  const { detail, suggested_fix, code, stage, technical_detail, evidence, request_id } = errorData;
  const codeLabel = CODE_LABELS[code];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-0.5">
        <div className="flex items-start gap-3 text-red-400 font-bold text-sm">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          Deploy no completado
        </div>
        {codeLabel && (
          <p className="text-xs text-gray-500 pl-8">{codeLabel}</p>
        )}
      </div>

      <p className="text-gray-200 text-sm leading-relaxed">{detail}</p>

      {evidence?.install_skipped && (
        <div className="flex items-start gap-2 bg-amber-500/8 border border-amber-500/20 rounded-xl px-4 py-3">
          <Zap className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-amber-300 text-xs leading-relaxed">
            Lo detectamos antes de instalar dependencias — no se creó ningún contenedor ni se ejecutó el build.
          </p>
        </div>
      )}

      {suggested_fix && (
        <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3">
          <Wrench className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
          <p className="text-blue-300 text-xs leading-relaxed">{suggested_fix}</p>
        </div>
      )}

      <DeployErrorDetails
        code={code}
        stage={stage}
        request_id={request_id}
        technical_detail={technical_detail}
        evidence={evidence}
      />
    </div>
  );
}
