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
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Login | Coffee Grade Identification</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>

    <link
        href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Work+Sans:wght@400;500;600;700&display=swap"
        rel="stylesheet">

    <link rel="stylesheet" href="assets/css/login.css?v=20261025-1">
</head>

<body>

    <main class="login-page">

        <section class="login-experience">

            <!-- =====================================================
                 VISUAL / BRAND SIDE
            ====================================================== -->

            <section class="visual-panel">

                <div class="visual-glow visual-glow-top"></div>
                <div class="visual-glow visual-glow-bottom"></div>

                <div class="vision-grid" aria-hidden="true"></div>

                <div class="brand-header">

                    <div class="brand-identity">

                        <img
                            src="assets/images/cgi-logo.png"
                            alt="Coffee Grade Identification logo"
                            class="brand-logo">

                        <div class="brand-copy">
                            <span>COFFEE GRADE</span>
                            <strong>IDENTIFICATION</strong>
                        </div>

                    </div>

                </div>

                <div class="visual-content">

                    <h1>
                        Every bean tells
                        <span>a story.</span>
                    </h1>

                    <p class="hero-description">
                        CGI transforms green Robusta coffee assessment into
                        measurable data through computer vision, defect
                        analysis, and intelligent transaction support.
                    </p>

                    <!-- COFFEE VISION GRAPHIC -->

                    <div class="vision-stage" aria-hidden="true">

                        <div class="vision-orbit orbit-one"></div>
                        <div class="vision-orbit orbit-two"></div>

                        <div class="vision-crosshair horizontal"></div>
                        <div class="vision-crosshair vertical"></div>

                        <div class="coffee-bean-visual">

                            <div class="bean-half bean-left"></div>
                            <div class="bean-half bean-right"></div>
                            <div class="bean-groove"></div>

                            <span class="scan-line"></span>

                            <span class="corner corner-tl"></span>
                            <span class="corner corner-tr"></span>
                            <span class="corner corner-bl"></span>
                            <span class="corner corner-br"></span>

                        </div>

                        <div class="vision-tag vision-tag-one">
                            <span>01</span>
                            IMAGE ACQUISITION
                        </div>

                        <div class="vision-tag vision-tag-two">
                            <span>02</span>
                            DEFECT DETECTION
                        </div>

                        <div class="vision-tag vision-tag-three">
                            <span>03</span>
                            QUALITY ASSESSMENT
                        </div>

                    </div>

                </div>

            </section>

            <!-- =====================================================
                 LOGIN SIDE
            ====================================================== -->

            <section class="login-panel">

                <div class="login-panel-inner">

                    <div class="mobile-brand">

                        <img
                            src="assets/images/cgi-logo.png"
                            alt=""
                            class="mobile-logo">

                        <div>
                            <span>COFFEE GRADE</span>
                            <strong>IDENTIFICATION</strong>
                        </div>

                    </div>

                    <div class="login-heading">

                        <span class="login-eyebrow">
                            SECURE SYSTEM ACCESS
                        </span>

                        <h2>Welcome back.</h2>

                        <p>
                            Enter your account credentials to continue
                            to the Coffee Grade Identification system.
                        </p>

                    </div>

                    <?php if (!empty($error)): ?>

                        <div class="login-alert" role="alert">

                            <span class="alert-symbol">!</span>

                            <div>
                                <strong>Unable to sign in</strong>
                                <span><?= htmlspecialchars($error) ?></span>
                            </div>

                        </div>

                    <?php endif; ?>

                    <form
                        class="login-form"
                        action="<?= APP_BASE ?>/login.php"
                        method="POST">

                        <div class="field-group">

                            <label for="email">
                                Email
                            </label>

                            <div class="field">

                                <span class="field-icon">
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5Zm0 2c-3.33 0-10 1.67-10 5v3h20v-3c0-3.33-6.67-5-10-5Z"/>
                                    </svg>
                                </span>

                                <input
                                    type="email"
                                    id="email"
                                    name="email"
                                    value="<?= htmlspecialchars($_POST['email'] ?? '') ?>"
                                    placeholder="Enter email"
                                    autocomplete="username"
                                    autofocus
                                    required>

                                <span class="field-line"></span>

                            </div>

                        </div>

                        <div class="field-group">

                            <label for="password">
                                Password
                            </label>

                            <div class="field">

                                <span class="field-icon">
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M17 8h-1V6a4 4 0 0 0-8 0v2H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2Zm-7-2a2 2 0 0 1 4 0v2h-4V6Zm2 11.7a2 2 0 1 1 1-3.73V17a1 1 0 0 1-2 0v-3.03a2 2 0 0 1 1 3.73Z"/>
                                    </svg>
                                </span>

                                <input
                                    type="password"
                                    id="password"
                                    name="password"
                                    placeholder="Enter password"
                                    autocomplete="current-password"
                                    required>

                                <button
                                    type="button"
                                    class="password-toggle"
                                    id="password-toggle"
                                    aria-label="Show password"
                                    aria-pressed="false"
                                    aria-controls="password">

                                    <svg class="eye-open" viewBox="0 0 24 24">
                                        <path d="M12 5c-5.5 0-9.5 5.1-9.7 5.3a1 1 0 0 0 0 1.4C2.5 11.9 6.5 17 12 17s9.5-5.1 9.7-5.3a1 1 0 0 0 0-1.4C21.5 10.1 17.5 5 12 5Zm0 10c-3.6 0-6.6-2.8-7.6-4 1-1.2 4-4 7.6-4s6.6 2.8 7.6 4c-1 1.2-4 4-7.6 4Zm0-6a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/>
                                    </svg>

                                    <svg class="eye-closed" viewBox="0 0 24 24">
                                        <path d="m3.3 2 18.7 18.7-1.3 1.3-3.1-3.1A10.8 10.8 0 0 1 12 20C6.5 20 2.5 14.9 2.3 14.7a1 1 0 0 1 0-1.4 17 17 0 0 1 3.1-3.1L2 6.7 3.3 5.4 6.7 8.8A10.9 10.9 0 0 1 12 7c5.5 0 9.5 5.1 9.7 5.3a1 1 0 0 1 0 1.4 16.4 16.4 0 0 1-2.6 2.7l-1.4-1.4a14.3 14.3 0 0 0 1.9-1.9c-1-1.2-4-4-7.6-4-1.3 0-2.5.4-3.6.9l1.5 1.5A3 3 0 0 1 14.5 16l1.5 1.5 1.6 1.4-1.4 1.4-2-2-3.4-3.4L3.3 7.4V2Z"/>
                                    </svg>

                                </button>

                                <span class="field-line"></span>

                            </div>

                        </div>

                        <button
                            type="submit"
                            class="login-button">

                            <span class="button-text">
                                Enter CGI System
                            </span>

                            <span class="button-arrow">
                                <svg viewBox="0 0 24 24">
                                    <path d="m13 5-1.4 1.4 4.6 4.6H4v2h12.2l-4.6 4.6L13 19l7-7-7-7Z"/>
                                </svg>
                            </span>

                        </button>

                    </form>

                    <div class="access-note">

                        <div class="access-icon">
                            <svg viewBox="0 0 24 24">
                                <path d="M12 2 4 5v6c0 5.1 3.4 9.8 8 11 4.6-1.2 8-5.9 8-11V5l-8-3Zm0 17.9c-3.3-1.2-6-4.9-6-8.9V6.4l6-2.3 6 2.3V11c0 4-2.7 7.7-6 8.9Z"/>
                            </svg>
                        </div>

                        <div>
                            <strong>Protected system</strong>
                            <span>
                                Access is restricted to authorized
                                CGI personnel.
                            </span>
                        </div>

                    </div>

                </div>

            </section>

        </section>

    </main>

    <script src="assets/js/login.js?v=20261025-1"></script>

</body>

</html>