import { ShieldCheck, ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

const LAST_UPDATED = '16 de abril de 2026';
const CONTACT_EMAIL = 'legal@hostingguard.lat';
const COMPANY_NAME = 'HostingGuard';
const SITE_URL = 'https://hostingguard.lat';

const sections = [
  { id: 'quienes-somos',        label: '1. Quiénes somos' },
  { id: 'datos-recopilados',    label: '2. Datos que recopilamos' },
  { id: 'uso-de-datos',         label: '3. Cómo usamos tus datos' },
  { id: 'base-legal',           label: '4. Base legal del tratamiento' },
  { id: 'compartir-datos',      label: '5. Compartir datos con terceros' },
  { id: 'almacenamiento',       label: '6. Almacenamiento y seguridad' },
  { id: 'derechos',             label: '7. Tus derechos' },
  { id: 'cookies',              label: '8. Cookies' },
  { id: 'menores',              label: '9. Menores de edad' },
  { id: 'cambios',              label: '10. Cambios a esta política' },
  { id: 'contacto',             label: '11. Contacto' },
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

export default function PrivacyPolicy() {
  return (
    <div className="min-h-screen bg-[#080809] text-white">
      {/* Header */}
      <div className="border-b border-white/8 bg-[#0d0d0f]">
        <div className="max-w-4xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-primary" />
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
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium mb-4">
              <ShieldCheck className="w-3.5 h-3.5" />
              Política de Privacidad
            </div>
            <h1 className="text-3xl font-black text-white mb-3">Política de Privacidad</h1>
            <p className="text-gray-500 text-sm">Última actualización: {LAST_UPDATED}</p>
          </div>

          <p className="text-gray-400 text-sm leading-relaxed mb-10 p-4 rounded-xl bg-white/3 border border-white/8">
            En {COMPANY_NAME} nos tomamos en serio la privacidad de tus datos. Esta política describe qué información recopilamos, cómo la usamos, cómo la protegemos y cuáles son tus derechos. Al usar nuestros servicios aceptás esta política.
          </p>

          <Section id="quienes-somos" title="1. Quiénes somos">
            <p>
              <strong className="text-white">{COMPANY_NAME}</strong> es una plataforma de hosting web administrado que provee infraestructura en la nube para alojar sitios web y aplicaciones. Operamos bajo el dominio <strong className="text-white">{SITE_URL}</strong>.
            </p>
            <p>Para consultas relacionadas con privacidad, podés contactarnos en <a href={`mailto:${CONTACT_EMAIL}`} className="text-primary hover:underline">{CONTACT_EMAIL}</a>.</p>
          </Section>

          <Section id="datos-recopilados" title="2. Datos que recopilamos">
            <p>Recopilamos los siguientes tipos de datos personales:</p>

            <div className="mt-3">
              <div className="text-white text-xs font-semibold uppercase tracking-wider mb-2">Datos que nos proporcionás directamente</div>
              <ul className="space-y-1.5 pl-1">
                <Li>Nombre y apellido</Li>
                <Li>Dirección de correo electrónico</Li>
                <Li>Número de teléfono</Li>
                <Li>País de residencia</Li>
                <Li>Contraseña (almacenada siempre como hash bcrypt — jamás en texto plano)</Li>
              </ul>
            </div>

            <div className="mt-4">
              <div className="text-white text-xs font-semibold uppercase tracking-wider mb-2">Datos generados automáticamente</div>
              <ul className="space-y-1.5 pl-1">
                <Li>Dirección IP de acceso (para auditoría de seguridad y detección de fraude)</Li>
                <Li>Métricas de uso de los contenedores: CPU, RAM, tráfico de red</Li>
                <Li>Logs de acceso y errores del servidor de tu hosting</Li>
                <Li>Registros de inicio de sesión (fecha, hora, IP, resultado)</Li>
                <Li>Eventos del orquestador (reinicios, escalado automático, expiraciones)</Li>
              </ul>
            </div>

            <div className="mt-4">
              <div className="text-white text-xs font-semibold uppercase tracking-wider mb-2">Datos de pago</div>
              <ul className="space-y-1.5 pl-1">
                <Li>Saldo prepago en la plataforma. No almacenamos datos de tarjetas de crédito directamente — los pagos son procesados por proveedores de pago de terceros.</Li>
              </ul>
            </div>
          </Section>

          <Section id="uso-de-datos" title="3. Cómo usamos tus datos">
            <p>Usamos tus datos personales exclusivamente para:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li>Crear y gestionar tu cuenta en la plataforma</Li>
              <Li>Proveer, mantener y mejorar los servicios de hosting</Li>
              <Li>Verificar tu identidad y prevenir el fraude</Li>
              <Li>Enviar comunicaciones relacionadas con el servicio (alertas, vencimientos, facturas)</Li>
              <Li>Cumplir con obligaciones legales y regulatorias</Li>
              <Li>Monitorear el rendimiento e infraestructura de los contenedores</Li>
              <Li>Soporte técnico y resolución de incidentes</Li>
            </ul>
            <p className="mt-3">
              <strong className="text-white">No vendemos</strong> tus datos personales a terceros. No usamos tus datos para publicidad de terceros.
            </p>
          </Section>

          <Section id="base-legal" title="4. Base legal del tratamiento">
            <p>El tratamiento de tus datos personales se basa en:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li><strong className="text-white">Ejecución de contrato:</strong> necesitamos procesar tus datos para prestarte el servicio contratado.</Li>
              <Li><strong className="text-white">Interés legítimo:</strong> para proteger la seguridad de la plataforma, prevenir fraudes y abusos.</Li>
              <Li><strong className="text-white">Obligación legal:</strong> cuando debamos cumplir con requerimientos legales aplicables.</Li>
              <Li><strong className="text-white">Consentimiento:</strong> para comunicaciones opcionales de marketing (podés retirar tu consentimiento en cualquier momento).</Li>
            </ul>
          </Section>

          <Section id="compartir-datos" title="5. Compartir datos con terceros">
            <p>Solo compartimos tus datos con terceros en los siguientes casos:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li><strong className="text-white">Proveedores de infraestructura:</strong> los servidores donde corre la plataforma (procesamiento necesario para el servicio).</Li>
              <Li><strong className="text-white">Procesadores de pago:</strong> para procesar transacciones de forma segura.</Li>
              <Li><strong className="text-white">Obligación legal:</strong> si una autoridad competente lo requiere mediante orden judicial o requerimiento legal válido.</Li>
            </ul>
            <p className="mt-3">Todos nuestros proveedores están sujetos a acuerdos de procesamiento de datos que los obligan a proteger tu información.</p>
          </Section>

          <Section id="almacenamiento" title="6. Almacenamiento y seguridad">
            <ul className="space-y-1.5 pl-1">
              <Li>Las contraseñas se almacenan usando <strong className="text-white">bcrypt</strong> con salt individual — nunca en texto plano.</Li>
              <Li>Las sesiones se gestionan con <strong className="text-white">JWT firmados</strong> con expiración corta (15 minutos) y refresh tokens de 7 días.</Li>
              <Li>Los tokens revocados se registran en <strong className="text-white">Redis</strong> para prevenir reutilización.</Li>
              <Li>Las comunicaciones están cifradas con <strong className="text-white">TLS 1.2+</strong> (HTTPS obligatorio en producción).</Li>
              <Li>Conservamos tus datos mientras tu cuenta esté activa. Al eliminar tu cuenta, los datos se eliminan en un plazo de 30 días, salvo obligación legal de retención.</Li>
            </ul>
          </Section>

          <Section id="derechos" title="7. Tus derechos">
            <p>De acuerdo con la normativa de protección de datos aplicable, tenés derecho a:</p>
            <ul className="space-y-1.5 pl-1 mt-2">
              <Li><strong className="text-white">Acceso:</strong> solicitar una copia de los datos personales que tenemos sobre vos.</Li>
              <Li><strong className="text-white">Rectificación:</strong> corregir datos incorrectos o incompletos.</Li>
              <Li><strong className="text-white">Eliminación:</strong> solicitar la eliminación de tus datos ("derecho al olvido").</Li>
              <Li><strong className="text-white">Portabilidad:</strong> recibir tus datos en un formato estructurado y legible por máquina.</Li>
              <Li><strong className="text-white">Oposición:</strong> oponerte al tratamiento de tus datos en ciertas circunstancias.</Li>
              <Li><strong className="text-white">Limitación:</strong> solicitar que restrinjamos el tratamiento de tus datos.</Li>
            </ul>
            <p className="mt-3">Para ejercer cualquiera de estos derechos, escribinos a <a href={`mailto:${CONTACT_EMAIL}`} className="text-primary hover:underline">{CONTACT_EMAIL}</a>. Responderemos en un plazo máximo de 30 días.</p>
          </Section>

          <Section id="cookies" title="8. Cookies">
            <p>Usamos únicamente las cookies estrictamente necesarias para el funcionamiento del servicio:</p>
            <div className="overflow-x-auto mt-3">
              <table className="w-full text-xs border border-white/10 rounded-lg overflow-hidden">
                <thead>
                  <tr className="bg-white/5">
                    <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Cookie</th>
                    <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Propósito</th>
                    <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Duración</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  <tr><td className="px-4 py-2.5 font-mono text-primary">access_token</td><td className="px-4 py-2.5 text-gray-400">Autenticación de sesión</td><td className="px-4 py-2.5 text-gray-500">15 minutos</td></tr>
                  <tr><td className="px-4 py-2.5 font-mono text-primary">refresh_token</td><td className="px-4 py-2.5 text-gray-400">Renovación de sesión</td><td className="px-4 py-2.5 text-gray-500">7 días</td></tr>
                </tbody>
              </table>
            </div>
            <p className="mt-3">No usamos cookies de rastreo ni publicidad de terceros.</p>
          </Section>

          <Section id="menores" title="9. Menores de edad">
            <p>Nuestros servicios están destinados a personas mayores de 18 años. No recopilamos intencionalmente datos de menores de edad. Si creés que un menor registró una cuenta, por favor contactanos para eliminar la información de inmediato.</p>
          </Section>

          <Section id="cambios" title="10. Cambios a esta política">
            <p>Podemos actualizar esta política periódicamente. Cuando lo hagamos, actualizaremos la fecha de "Última actualización" en la parte superior. Si los cambios son significativos, te notificaremos por email o mediante un aviso visible en la plataforma.</p>
          </Section>

          <Section id="contacto" title="11. Contacto">
            <p>Para cualquier consulta sobre privacidad o para ejercer tus derechos, contactanos en:</p>
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
