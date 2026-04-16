import { FileText, ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

const LAST_UPDATED = '16 de abril de 2026';
const CONTACT_EMAIL = 'legal@hostingguard.lat';
const COMPANY_NAME = 'HostingGuard';
const SITE_URL = 'https://hostingguard.lat';

const sections = [
  { id: 'aceptacion',     label: '1. Aceptación de los términos' },
  { id: 'descripcion',    label: '2. Descripción del servicio' },
  { id: 'cuenta',         label: '3. Registro y cuenta' },
  { id: 'uso-aceptable',  label: '4. Uso aceptable' },
  { id: 'planes-pago',    label: '5. Planes y facturación' },
  { id: 'disponibilidad', label: '6. Disponibilidad del servicio' },
  { id: 'soporte',        label: '7. Soporte técnico' },
  { id: 'propiedad',      label: '8. Propiedad intelectual' },
  { id: 'privacidad',     label: '9. Privacidad y datos' },
  { id: 'responsabilidad',label: '10. Limitación de responsabilidad' },
  { id: 'terminacion',    label: '11. Terminación' },
  { id: 'ley-aplicable',  label: '12. Ley aplicable' },
  { id: 'cambios',        label: '13. Cambios a los términos' },
  { id: 'contacto',       label: '14. Contacto' },
];

function Section({ id, title, children }) {
  return (
    <section id={id} className="scroll-mt-24 mb-10">
      <h2 className="text-lg font-bold text-white mb-4 pb-2 border-b border-white/10">{title}</h2>
      <div className="space-y-3 text-gray-400 text-sm leading-relaxed">{children}</div>
    </section>
  );
}

function Li({ children }) {
  return <li className="flex gap-2"><span className="text-primary shrink-0 mt-1">›</span><span>{children}</span></li>;
}

function Prohibited({ children }) {
  return <li className="flex gap-2"><span className="text-red-400 shrink-0 mt-1">✕</span><span>{children}</span></li>;
}

export default function TermsConditions() {
  return (
    <div className="min-h-screen bg-[#080809] text-white">
      {/* Header */}
      <div className="border-b border-white/8 bg-[#0d0d0f]">
        <div className="max-w-4xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" />
            <span className="font-bold text-white">Hosting<span className="text-primary">Guard</span></span>
          </Link>
          <Link to="/" className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Volver al inicio
          </Link>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-14 lg:flex lg:gap-12">
        {/* Sidebar TOC */}
        <aside className="hidden lg:block w-56 shrink-0">
          <div className="sticky top-10">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-gray-600 mb-3">Contenido</div>
            <nav className="space-y-1">
              {sections.map(s => (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  className="block text-xs text-gray-500 hover:text-white py-1 transition-colors truncate"
                >
                  {s.label}
                </a>
              ))}
            </nav>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0">
          <div className="mb-10">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 text-xs font-medium mb-4">
              <FileText className="w-3.5 h-3.5" />
              Documento legal
            </div>
            <h1 className="text-3xl font-black text-white mb-3">Términos y Condiciones</h1>
            <p className="text-gray-500 text-sm">Última actualización: {LAST_UPDATED}</p>
          </div>

          <p className="text-gray-400 text-sm leading-relaxed mb-10 p-4 rounded-xl bg-white/3 border border-white/8">
            Estos Términos y Condiciones ("Términos") regulan el acceso y uso de los servicios ofrecidos por <strong className="text-white">{COMPANY_NAME}</strong> a través del sitio <strong className="text-white">{SITE_URL}</strong>. Al crear una cuenta o usar nuestros servicios, aceptás estos Términos en su totalidad.
          </p>

          <Section id="aceptacion" title="1. Aceptación de los términos">
            <p>Al registrarte en {COMPANY_NAME} o al usar cualquiera de nuestros servicios, declarás que:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li>Tenés al menos 18 años de edad.</Li>
              <Li>Leíste, entendiste y aceptás estos Términos y la <Link to="/privacy" className="text-primary hover:underline">Política de Privacidad</Link>.</Li>
              <Li>Tenés capacidad legal para celebrar contratos en tu jurisdicción.</Li>
            </ul>
            <p className="mt-3">Si usás el servicio en nombre de una empresa u organización, también declarás que tenés autorización para vincular a dicha organización con estos Términos.</p>
          </Section>

          <Section id="descripcion" title="2. Descripción del servicio">
            <p>{COMPANY_NAME} es una plataforma de <strong className="text-white">hosting web administrado en la nube</strong>. El servicio incluye:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li>Provisión de contenedores Docker aislados para alojar sitios web y aplicaciones.</Li>
              <Li>Panel de control para gestionar tus proyectos, logs y métricas de rendimiento.</Li>
              <Li>Motor de diagnóstico y recomendaciones impulsado por inteligencia artificial (función advisory).</Li>
              <Li>Monitoreo de salud del sistema en tiempo real.</Li>
              <Li>Escalado automático de recursos según el plan contratado.</Li>
            </ul>
            <p className="mt-3">Las características específicas disponibles dependen del plan elegido (Free, Personal, Negocio, Agencia).</p>
          </Section>

          <Section id="cuenta" title="3. Registro y cuenta">
            <p>Para usar los servicios deberás crear una cuenta proporcionando información veraz, completa y actualizada. Sos responsable de:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li>Mantener la confidencialidad de tus credenciales de acceso.</Li>
              <Li>Todas las actividades que ocurran bajo tu cuenta.</Li>
              <Li>Notificarnos inmediatamente ante cualquier acceso no autorizado a <a href={`mailto:${CONTACT_EMAIL}`} className="text-primary hover:underline">{CONTACT_EMAIL}</a>.</Li>
              <Li>Mantener actualizado tu email de contacto para recibir notificaciones del servicio.</Li>
            </ul>
            <p className="mt-3">{COMPANY_NAME} se reserva el derecho de suspender o eliminar cuentas que violen estos Términos, que proporcionen información falsa, o que realicen actividades que pongan en riesgo la plataforma o a otros usuarios.</p>
          </Section>

          <Section id="uso-aceptable" title="4. Uso aceptable">
            <p>Al usar los servicios de {COMPANY_NAME} te comprometés a <strong className="text-white">NO</strong> realizar las siguientes actividades:</p>
            <ul className="space-y-1.5 pl-1 mt-3">
              <Prohibited>Alojar, distribuir o transmitir contenido ilegal, incluyendo material que infrinja derechos de autor, patentes o marcas registradas.</Prohibited>
              <Prohibited>Distribuir malware, ransomware, spyware, adware u otro software malicioso.</Prohibited>
              <Prohibited>Lanzar ataques de denegación de servicio (DoS/DDoS) contra cualquier sistema o infraestructura.</Prohibited>
              <Prohibited>Enviar spam o correos masivos no solicitados desde los recursos de la plataforma.</Prohibited>
              <Prohibited>Realizar actividades de minería de criptomonedas (cryptomining) que consuman recursos de la plataforma.</Prohibited>
              <Prohibited>Acceder o intentar acceder a sistemas, datos o cuentas de otros usuarios sin autorización.</Prohibited>
              <Prohibited>Eludir o intentar eludir las medidas de seguridad de la plataforma.</Prohibited>
              <Prohibited>Alojar contenido de explotación sexual infantil (CSAM) o cualquier contenido que dañe a menores.</Prohibited>
              <Prohibited>Usar los servicios para actividades fraudulentas, phishing o ingeniería social.</Prohibited>
              <Prohibited>Revender o sub-arrendar los servicios sin autorización expresa por escrito.</Prohibited>
            </ul>
            <p className="mt-4">El incumplimiento de estas normas puede resultar en la suspensión inmediata del servicio sin previo aviso y en la eliminación permanente de la cuenta, sin derecho a reembolso.</p>
          </Section>

          <Section id="planes-pago" title="5. Planes y facturación">
            <p><strong className="text-white">Plan Free (prueba):</strong> El plan gratuito tiene una duración de 14 días calendario desde la fecha de creación. Al vencimiento, el contenedor se suspende automáticamente. Para reactivar el servicio debés actualizar a un plan pago.</p>

            <p className="mt-3"><strong className="text-white">Planes pagos:</strong> Los planes Personal, Negocio y Agencia son servicios continuos. El cobro se realiza mediante saldo prepago en la plataforma. El saldo se descuenta periódicamente según las tarifas vigentes publicadas en {SITE_URL}/pricing.</p>

            <p className="mt-3"><strong className="text-white">Cambios de plan:</strong> Podés actualizar tu plan en cualquier momento. Los recursos (CPU, RAM, almacenamiento) se ajustan inmediatamente al cambiar de plan.</p>

            <p className="mt-3"><strong className="text-white">Reembolsos:</strong> El saldo prepago no utilizado puede ser reembolsado dentro de los 7 días de la carga, descontando los costos de servicio incurridos. Contactanos en <a href={`mailto:${CONTACT_EMAIL}`} className="text-primary hover:underline">{CONTACT_EMAIL}</a> para gestionar un reembolso.</p>

            <p className="mt-3"><strong className="text-white">Precios:</strong> Nos reservamos el derecho de modificar los precios con un aviso previo de 30 días. Los cambios no afectarán el saldo ya cargado en la plataforma.</p>
          </Section>

          <Section id="disponibilidad" title="6. Disponibilidad del servicio">
            <p>Hacemos todos los esfuerzos razonables para mantener la plataforma disponible de forma continua. Sin embargo:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li>No garantizamos un nivel de disponibilidad específico (SLA) para el plan Free.</Li>
              <Li>Los planes pagos cuentan con un objetivo de disponibilidad del 99% mensual.</Li>
              <Li>Realizamos mantenimientos programados que pueden causar interrupciones breves, comunicando con antelación razonable.</Li>
              <Li>No somos responsables por interrupciones causadas por terceros (proveedores de internet, ataques externos, desastres naturales).</Li>
            </ul>
          </Section>

          <Section id="soporte" title="7. Soporte técnico">
            <p>El soporte técnico se provee según el plan:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li><strong className="text-white">Free:</strong> Soporte vía email con respuesta en 72 horas hábiles.</Li>
              <Li><strong className="text-white">Personal:</strong> Soporte vía email con respuesta en 48 horas hábiles.</Li>
              <Li><strong className="text-white">Negocio:</strong> Soporte prioritario con respuesta en 24 horas hábiles.</Li>
              <Li><strong className="text-white">Agencia:</strong> Soporte dedicado con respuesta en 8 horas hábiles.</Li>
            </ul>
            <p className="mt-3">El soporte remoto (acceso asistido a tu cuenta) solo se realiza con tu consentimiento explícito y queda registrado en el log de auditoría de la plataforma.</p>
          </Section>

          <Section id="propiedad" title="8. Propiedad intelectual">
            <p><strong className="text-white">Tu contenido:</strong> Mantenés todos los derechos sobre el contenido que alojes en la plataforma. Al usar el servicio nos otorgás una licencia limitada para procesar y almacenar dicho contenido únicamente con el fin de prestar el servicio.</p>
            <p className="mt-3"><strong className="text-white">Nuestra plataforma:</strong> El software, diseño, marcas y tecnología de {COMPANY_NAME} son propiedad exclusiva de {COMPANY_NAME} o sus licenciantes. Queda prohibida su reproducción, distribución o ingeniería inversa sin autorización escrita.</p>
          </Section>

          <Section id="privacidad" title="9. Privacidad y datos">
            <p>El tratamiento de tus datos personales está regulado por nuestra <Link to="/privacy" className="text-primary hover:underline">Política de Privacidad</Link>, que forma parte integrante de estos Términos.</p>
          </Section>

          <Section id="responsabilidad" title="10. Limitación de responsabilidad">
            <p>En la máxima medida permitida por la ley aplicable:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li>{COMPANY_NAME} no será responsable por daños indirectos, incidentales, especiales, consecuentes o punitivos.</Li>
              <Li>La responsabilidad total de {COMPANY_NAME} frente a vos no excederá el monto pagado en los últimos 3 meses de servicio.</Li>
              <Li>El servicio se provee "tal cual" (<em>as is</em>) y "según disponibilidad" (<em>as available</em>).</Li>
            </ul>
            <p className="mt-3">Recomendamos mantener copias de seguridad (backups) de tu contenido. {COMPANY_NAME} no garantiza la recuperación de datos perdidos por error del usuario, fuerza mayor o incidentes fuera de nuestro control.</p>
          </Section>

          <Section id="terminacion" title="11. Terminación">
            <p><strong className="text-white">Por tu parte:</strong> Podés cancelar tu cuenta en cualquier momento desde la configuración de cuenta o contactándonos. Al cancelar, tus datos se eliminan en un plazo de 30 días.</p>
            <p className="mt-3"><strong className="text-white">Por nuestra parte:</strong> Podemos suspender o terminar tu cuenta:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li>Por violación de estos Términos o la Política de Uso Aceptable.</Li>
              <Li>Por falta de pago (plan pago con saldo insuficiente por más de 7 días).</Li>
              <Li>Por vencimiento del plan Free sin actualización.</Li>
              <Li>Por actividad sospechosa o fraudulenta.</Li>
            </ul>
            <p className="mt-3">En caso de terminación por violación de Términos, no habrá derecho a reembolso del saldo disponible.</p>
          </Section>

          <Section id="ley-aplicable" title="12. Ley aplicable">
            <p>Estos Términos se rigen por las leyes de la República Argentina. Cualquier disputa derivada de estos Términos se someterá a la jurisdicción exclusiva de los tribunales competentes de la Ciudad Autónoma de Buenos Aires, Argentina, renunciando expresamente a cualquier otro fuero que pudiera corresponder.</p>
          </Section>

          <Section id="cambios" title="13. Cambios a los términos">
            <p>Podemos modificar estos Términos en cualquier momento. Los cambios entrarán en vigencia a los 30 días de su publicación para usuarios activos, y de forma inmediata para nuevos registros. Te notificaremos por email o mediante un aviso en la plataforma. El uso continuado del servicio luego de la vigencia de los cambios implica su aceptación.</p>
          </Section>

          <Section id="contacto" title="14. Contacto">
            <p>Para consultas sobre estos Términos, contactanos en:</p>
            <div className="mt-3 p-4 rounded-xl bg-white/3 border border-white/8">
              <div className="text-white font-semibold mb-1">{COMPANY_NAME}</div>
              <div>Email: <a href={`mailto:${CONTACT_EMAIL}`} className="text-primary hover:underline">{CONTACT_EMAIL}</a></div>
              <div>Web: <a href={SITE_URL} className="text-primary hover:underline">{SITE_URL}</a></div>
            </div>
          </Section>
        </main>
      </div>
    </div>
  );
}
