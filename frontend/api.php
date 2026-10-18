<?php
/**
 * api.php — Thin PHP API proxy helper.
 * Stores the JWT in the PHP session and provides a helper to call the FastAPI backend.
 */
session_start();

define('API_BASE', getenv('CGI_API_BASE') ?: 'http://localhost:8000');

// Auto-detect the base URL path (e.g. "/CGI/frontend") so redirects work
// regardless of where the project is placed inside htdocs.
if (!defined('APP_BASE')) {
    $docRoot = rtrim(str_replace('\\', '/', $_SERVER['DOCUMENT_ROOT']), '/');
    $selfDir = rtrim(str_replace('\\', '/', __DIR__), '/');
    define('APP_BASE', str_replace($docRoot, '', $selfDir));
}

function api_get_token(): ?string {
    return $_SESSION['jwt'] ?? null;
}

function api_set_token(string $token, array $user): void {
    $_SESSION['jwt']  = $token;
    $_SESSION['user'] = $user;
}

function api_clear_session(): void {
    session_destroy();
}

function api_current_user(): ?array {
    return $_SESSION['user'] ?? null;
}

/**
 * Emit an inline <script> that seeds the JWT into sessionStorage so that
 * client-side JS (api.js, users.php, etc.) can attach it to fetch() calls.
 * Call this once per page, just before </body> or right after <body>.
 * Safe to call even when no token exists (emits nothing).
 */
function api_inject_jwt_script(): void {
    $token = $_SESSION['jwt'] ?? null;
    if (!$token) return;
    $safe = json_encode($token); // properly escapes any special chars
    echo "<script>if(!sessionStorage.getItem('cgi_jwt')){sessionStorage.setItem('cgi_jwt',{$safe});}</script>\n";
}

function api_require_auth(array $allowed_roles = []): void {
    $user = api_current_user();
    if (!$user) {
        header('Location: ' . APP_BASE . '/login.php');
        exit;
    }
    if ($allowed_roles && !in_array($user['role'], $allowed_roles)) {
        http_response_code(403);
        include __DIR__ . '/pages/403.php';
        exit;
    }
}

/**
 * Make an authenticated request to the FastAPI backend.
 *
 * @param string $method  GET | POST | PUT | DELETE
 * @param string $path    e.g. "/api/dashboard/summary"
 * @param mixed  $body    Array to JSON-encode for POST/PUT
 * @return array          ['status' => int, 'data' => mixed]
 */
function api_request(string $method, string $path, $body = null): array {
    $url     = rtrim(API_BASE, '/') . $path;
    $token   = api_get_token();
    $headers = ['Content-Type: application/json'];
    if ($token) {
        $headers[] = "Authorization: Bearer $token";
    }

    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);

    if ($method === 'POST') {
        curl_setopt($ch, CURLOPT_POST, true);
        if ($body !== null) curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($body));
    } elseif ($method === 'PUT') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PUT');
        if ($body !== null) curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($body));
    } elseif ($method === 'DELETE') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'DELETE');
    }

    $response = curl_exec($ch);
    $status   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    return ['status' => $status, 'data' => json_decode($response, true)];
}
