<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>CGI — Login</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="assets/css/main.css">
</head>
<body class="cgi-login-bg d-flex align-items-center justify-content-center min-vh-100">

<?php
require_once __DIR__ . '/api.php';

// Redirect if already logged in
if (api_current_user()) {
    header('Location: ' . APP_BASE . '/dashboard.php');
    exit;
}

$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $email    = trim($_POST['email']    ?? '');
    $password = trim($_POST['password'] ?? '');

    if ($email && $password) {
        $resp = api_request('POST', '/api/auth/login', [
            'email'    => $email,
            'password' => $password,
        ]);
        if ($resp['status'] === 200
            && is_array($resp['data'])
            && isset($resp['data']['access_token'])
            && is_array($resp['data']['user'] ?? null)) {
            api_set_token($resp['data']['access_token'], $resp['data']['user']);
            header('Location: ' . APP_BASE . '/dashboard.php');
            exit;
        } else {
            $error = $resp['data']['detail'] ?? 'Invalid email or password.';
        }
    } else {
        $error = 'Please enter your email and password.';
    }
}
?>

<div class="card shadow-sm cgi-login-card">
    <div class="card-body p-4">
        <div class="text-center mb-4">
            <h1 class="h3 fw-bold text-success">☕ CGI</h1>
            <p class="text-muted small">Coffee Grade Identification System</p>
        </div>

        <?php if ($error): ?>
        <div class="alert alert-danger py-2"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>

        <form method="POST" action="<?= APP_BASE ?>/login.php">
            <div class="mb-3">
                <label for="email" class="form-label fw-semibold">Email</label>
                <input type="email" id="email" name="email" class="form-control form-control-lg"
                       value="<?= htmlspecialchars($_POST['email'] ?? '') ?>"
                       autofocus required>
            </div>
            <div class="mb-4">
                <label for="password" class="form-label fw-semibold">Password</label>
                <input type="password" id="password" name="password" class="form-control form-control-lg" required>
            </div>
            <button type="submit" class="btn btn-success btn-lg w-100">Sign In</button>
        </form>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
