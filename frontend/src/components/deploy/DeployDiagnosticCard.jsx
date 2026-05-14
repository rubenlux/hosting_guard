import React from 'react';
import { AlertTriangle, ShieldAlert, Wrench, Zap } from 'lucide-react';
import DeployErrorDetails from './DeployErrorDetails';

const CODE_LABELS = {
  github_repo_not_found:                        'Repositorio no encontrado',
  github_private_repo_unauthorized:             'Repositorio privado sin permisos',
  github_branch_not_found:                      'Branch no encontrada',
  github_clone_timeout:                         'Clone demoró demasiado',
  invalid_repo_url:                             'URL de repositorio inválida',
  package_json_not_found:                       'No se encontró package.json',
  multiple_project_roots_detected:              'Múltiples proyectos detectados',
  build_script_missing:                         'Script build no encontrado',
  node_sass_incompatible:                       'Dependencia incompatible: node-sass',
  package_manager_pnpm_detected:                'pnpm no disponible en el build',
  package_manager_yarn_detected:                'Yarn no disponible en el build',
  node_version_mismatch:                        'Versión de Node incompatible',
  next_ssr_not_supported:                       'Next.js SSR no soportado',
  dependency_version_not_found:                 'Versión de dependencia no encontrada',
  module_not_found_build:                       'Módulo no encontrado en el build',
  openssl_build_failed:                         'Error de compatibilidad OpenSSL',
  index_html_not_found:                         'Build sin index.html',
  multiple_output_directories:                  'Múltiples salidas de build',
  unsafe_publish_root:                          'Directorio de publicación inseguro',
  ssl_provisioning_timeout:                     'SSL en proceso de activación',
  npm_supply_chain_tanstack_compromise:          'Alerta de seguridad: compromiso de cadena de suministro npm',
  npm_lockfile_required_for_supply_chain_safety: 'Lockfile requerido para seguridad de cadena de suministro',
  npm_supply_chain_risk:                         'Riesgo de cadena de suministro npm',
  multiple_lockfiles_detected:                   'Múltiples lockfiles detectados',
  lockfile_required:                             'Lockfile requerido',
  npm_ci_failed:                                 'npm ci falló',
  pnpm_install_failed:                           'pnpm install falló',
  yarn_install_failed:                           'yarn install falló',
};

const SUPPLY_CHAIN_CODES = new Set([
  'npm_supply_chain_tanstack_compromise',
  'npm_lockfile_required_for_supply_chain_safety',
  'npm_supply_chain_risk',
]);

export default function DeployDiagnosticCard({ errorData }) {
  const { detail, suggested_fix, code, stage, technical_detail, evidence, request_id } = errorData;
  const codeLabel = CODE_LABELS[code];
  const isSupplyChain = SUPPLY_CHAIN_CODES.has(code);

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

      {isSupplyChain && (
        <div className="flex items-start gap-3 bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3">
          <ShieldAlert className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <p className="text-red-300 text-xs font-semibold">Alerta de seguridad — cadena de suministro npm</p>
            <p className="text-red-400/80 text-xs leading-relaxed">
              Este deploy fue bloqueado porque el proyecto puede referenciar paquetes involucrados
              en el compromiso de la cadena de suministro de TanStack. Fijá una versión segura y
              commiteá un lockfile.
            </p>
          </div>
        </div>
      )}

      <p className="text-gray-200 text-sm leading-relaxed">{detail}</p>

      {evidence?.affected_packages && Object.keys(evidence.affected_packages).length > 0 && (
        <div className="bg-[#1a1a1f] border border-white/8 rounded-xl px-4 py-3">
          <p className="text-xs text-gray-400 mb-2 font-medium">Paquetes comprometidos detectados:</p>
          <ul className="flex flex-col gap-1">
            {Object.entries(evidence.affected_packages).map(([pkg, ver]) => (
              <li key={pkg} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-red-400">{pkg}</span>
                <span className="text-gray-600">@</span>
                <span className="text-orange-400">{ver}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

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
