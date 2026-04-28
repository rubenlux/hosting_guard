<?php
/**
 * Plugin Name: HostingGuard Audit
 * Description: Sends security and activity events to the HostingGuard platform.
 * Version: 1.0.0
 *
 * Must-use plugin — placed in wp-content/mu-plugins/ automatically.
 * Configuration via wp-config.php constants:
 *   define('HG_HOSTING_ID', 42);                              // required
 *   define('HG_AUDIT_TOKEN', 'your-hmac-token-here');         // required
 *   define('HG_API_URL', 'https://api.hostingguard.lat');     // optional
 *
 * Token derivation (matches wp_audit.py):
 *   HMAC-SHA256(key=WP_AUDIT_SECRET, msg="wp-audit:{hosting_id}")
 */

if ( ! defined('ABSPATH') ) exit;

// ─── Configuration ────────────────────────────────────────────────────────────

define('HG_API_ENDPOINT', (defined('HG_API_URL') ? HG_API_URL : 'https://api.hostingguard.lat') . '/internal/wp-audit/event');
define('HG_SEND_TIMEOUT', 3); // seconds — non-blocking best-effort

// ─── Core send function ───────────────────────────────────────────────────────

function hg_send_event(array $payload): void {
    if ( ! defined('HG_HOSTING_ID') || ! defined('HG_AUDIT_TOKEN') ) return;

    $body = array_merge([
        'hosting_id' => (int) HG_HOSTING_ID,
        'token'      => HG_AUDIT_TOKEN,
        'category'   => 'wordpress',
        'severity'   => 'info',
    ], $payload);

    wp_remote_post(HG_API_ENDPOINT, [
        'body'      => wp_json_encode($body),
        'headers'   => ['Content-Type' => 'application/json'],
        'timeout'   => HG_SEND_TIMEOUT,
        'blocking'  => false, // fire-and-forget, never delays page load
        'sslverify' => true,
    ]);
}

function hg_current_user_login(): ?string {
    $u = wp_get_current_user();
    return ($u && $u->ID) ? $u->user_login : null;
}

// ─── Auth events ──────────────────────────────────────────────────────────────

add_action('wp_login', function(string $login) {
    hg_send_event([
        'event_type' => 'wp_login_success',
        'category'   => 'auth',
        'title'      => "Login WordPress: $login",
        'wp_user'    => $login,
    ]);
});

add_action('wp_login_failed', function(string $username) {
    hg_send_event([
        'event_type' => 'wp_login_failed',
        'category'   => 'auth',
        'severity'   => 'warning',
        'title'      => "Intento de login fallido: $username",
        'wp_user'    => $username,
        'metadata'   => ['ip' => $_SERVER['REMOTE_ADDR'] ?? null],
    ]);
});

add_action('wp_logout', function() {
    $login = hg_current_user_login();
    hg_send_event([
        'event_type' => 'wp_logout',
        'category'   => 'auth',
        'title'      => 'Logout WordPress' . ($login ? ": $login" : ''),
        'wp_user'    => $login,
    ]);
});

// ─── User management events ───────────────────────────────────────────────────

add_action('user_register', function(int $user_id) {
    $user = get_userdata($user_id);
    hg_send_event([
        'event_type' => 'wp_user_created',
        'category'   => 'user',
        'title'      => 'Nuevo usuario WordPress creado',
        'wp_user'    => $user ? $user->user_login : null,
        'metadata'   => ['new_user_id' => $user_id],
    ]);
});

add_action('delete_user', function(int $user_id) {
    $user = get_userdata($user_id);
    hg_send_event([
        'event_type' => 'wp_user_deleted',
        'category'   => 'user',
        'severity'   => 'warning',
        'title'      => 'Usuario WordPress eliminado',
        'wp_user'    => hg_current_user_login(),
        'metadata'   => ['deleted_user' => $user ? $user->user_login : $user_id],
    ]);
});

add_action('set_user_role', function(int $user_id, string $role, array $old_roles) {
    $user = get_userdata($user_id);
    $old  = implode(', ', $old_roles) ?: 'none';
    hg_send_event([
        'event_type' => 'wp_user_role_changed',
        'category'   => 'user',
        'severity'   => 'warning',
        'title'      => "Rol de usuario cambiado: $old → $role",
        'wp_user'    => hg_current_user_login(),
        'metadata'   => ['target_user' => $user ? $user->user_login : $user_id, 'old_roles' => $old_roles, 'new_role' => $role],
    ]);
}, 10, 3);

// ─── Plugin events ────────────────────────────────────────────────────────────

add_action('activated_plugin', function(string $plugin) {
    hg_send_event([
        'event_type' => 'wp_plugin_activated',
        'category'   => 'plugin',
        'title'      => "Plugin activado: $plugin",
        'wp_user'    => hg_current_user_login(),
        'metadata'   => ['plugin' => $plugin],
    ]);
});

add_action('deactivated_plugin', function(string $plugin) {
    hg_send_event([
        'event_type' => 'wp_plugin_deactivated',
        'category'   => 'plugin',
        'title'      => "Plugin desactivado: $plugin",
        'wp_user'    => hg_current_user_login(),
        'metadata'   => ['plugin' => $plugin],
    ]);
});

add_action('upgrader_process_complete', function($upgrader, array $options) {
    $type   = $options['type'] ?? '';
    $action = $options['action'] ?? '';
    if ($action !== 'update') return;

    $items = $options['plugins'] ?? $options['themes'] ?? [];
    foreach ((array) $items as $item) {
        hg_send_event([
            'event_type' => "wp_{$type}_updated",
            'category'   => $type === 'theme' ? 'theme' : 'plugin',
            'title'      => ucfirst($type) . " actualizado: $item",
            'wp_user'    => hg_current_user_login(),
            'metadata'   => [$type => $item],
        ]);
    }
}, 10, 2);

// ─── Theme events ─────────────────────────────────────────────────────────────

add_action('switch_theme', function(string $new_name) {
    hg_send_event([
        'event_type' => 'wp_theme_switched',
        'category'   => 'theme',
        'title'      => "Tema cambiado a: $new_name",
        'wp_user'    => hg_current_user_login(),
        'metadata'   => ['theme' => $new_name],
    ]);
});

// ─── Core update ──────────────────────────────────────────────────────────────

add_action('_core_updated_successfully', function(string $wp_version) {
    hg_send_event([
        'event_type' => 'wp_core_updated',
        'category'   => 'system',
        'severity'   => 'warning',
        'title'      => "WordPress actualizado a $wp_version",
        'wp_user'    => hg_current_user_login(),
        'metadata'   => ['version' => $wp_version],
    ]);
});

// ─── File modification detection (options that hint at malware) ───────────────

add_action('update_option_active_plugins', function($old, $new) {
    $added   = array_diff((array)$new, (array)$old);
    $removed = array_diff((array)$old, (array)$new);
    if ($added) {
        hg_send_event([
            'event_type' => 'wp_plugin_list_changed',
            'category'   => 'security_internal',
            'severity'   => 'warning',
            'title'      => 'Lista de plugins activos modificada',
            'wp_user'    => hg_current_user_login(),
            'metadata'   => ['added' => array_values($added), 'removed' => array_values($removed)],
        ]);
    }
}, 10, 2);

// ─── Post/page events (optional — comment out if too noisy) ──────────────────

add_action('transition_post_status', function(string $new, string $old, $post) {
    if ($old === 'auto-draft') return; // skip initial draft saves
    if (!in_array($post->post_type, ['post', 'page'], true)) return;
    if ($new === $old) return;

    hg_send_event([
        'event_type' => 'wp_post_status_changed',
        'category'   => 'content',
        'title'      => "Contenido [{$post->post_type}] {$old} → {$new}: {$post->post_title}",
        'wp_user'    => hg_current_user_login(),
        'metadata'   => ['post_id' => $post->ID, 'post_type' => $post->post_type, 'old' => $old, 'new' => $new],
    ]);
}, 10, 3);
