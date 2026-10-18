
<?php
/**
 * components/navbar.php
 * CGI V1 visual design + CGI V2 navigation and authentication.
 * Expects $user from the including page.
 */

$current = basename($_SERVER['PHP_SELF']);
$role = $user['role'] ?? 'farmer';
$base = defined('APP_BASE') ? APP_BASE : '';

$displayName = htmlspecialchars(
    (string) ($user['name'] ?? 'User'),
    ENT_QUOTES,
    'UTF-8'
);

$roleLabels = [
    'admin' => 'System Administrator',
    'officer' => 'Cooperative Officer',
    'farmer' => 'Farmer',
];

$displayRole = htmlspecialchars(
    $roleLabels[$role] ?? ucwords(str_replace('_', ' ', $role)),
    ENT_QUOTES,
    'UTF-8'
);

$navItems = [
    ['dashboard.php', 'Dashboard', true],
    ['history.php', 'History', true],
    ['configuration.php', 'Configuration', $role !== 'farmer'],
];
?>

<header class="site-header">
    <a href="<?= htmlspecialchars($base . '/dashboard.php') ?>"
       class="nav-brand"
       aria-label="CGI Dashboard">

        <span class="brand-mark" aria-hidden="true">
            <img src="<?= htmlspecialchars($base . '/assets/images/cgi-logo.png') ?>"
                 alt=""
                 class="brand-logo"
                 aria-hidden="true">
        </span>

        <div class="nav-brand-text">
            <span class="nav-brand-name">CGI</span>
            <span class="nav-brand-subtitle">
                Coffee Grade Identification
            </span>
        </div>
    </a>

    <nav class="main-nav" aria-label="Main navigation">
        <?php foreach ($navItems as [$navPage, $label, $allowed]): ?>
            <?php if (!$allowed) continue; ?>

            <?php $isActive = $current === $navPage; ?>

            <a href="<?= htmlspecialchars($base . '/' . $navPage) ?>"
               class="<?= $isActive ? 'active' : '' ?>"
               <?= $isActive ? 'aria-current="page"' : '' ?>>
                <?= htmlspecialchars($label) ?>
            </a>
        <?php endforeach; ?>
    </nav>

    <div class="user-menu">
        <button type="button"
                class="user-trigger"
                id="avatar-btn"
                aria-haspopup="true"
                aria-expanded="false"
                aria-controls="user-dropdown"
                aria-label="Open user menu">

            <span class="avatar" aria-hidden="true">
                <svg class="avatar-icon" viewBox="0 0 24 24" focusable="false">
                    <path d="M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Zm0 2c-5 0-8 2.5-8 5.5V21h16v-1.5c0-3-3-5.5-8-5.5Z"/>
                </svg>
            </span>

            <span class="nav-user-identity">
                <strong><?= $displayName ?></strong>
                <span><?= $displayRole ?></span>
            </span>

            <svg class="user-menu-chevron" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <path d="m4 6 4 4 4-4"/>
            </svg>
        </button>

        <div class="user-dropdown" id="user-dropdown" hidden>
            <div class="dropdown-profile">
                <div class="dropdown-avatar">
                    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path d="M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Zm0 2c-5 0-8 2.5-8 5.5V21h16v-1.5c0-3-3-5.5-8-5.5Z"/>
                    </svg>
                </div>

                <div class="dropdown-profile-text">
                    <strong><?= $displayName ?></strong>
                    <span><?= $displayRole ?></span>
                </div>
            </div>

            <div class="cgi-dropdown-divider"></div>

            <?php if ($role === 'admin'): ?>
                <a href="<?= htmlspecialchars($base . '/users.php') ?>"
                   class="cgi-dropdown-item">

                    <span class="dropdown-item-icon">
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3ZM8 11c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3Zm8 2c-2 0-6 1-6 3v2h12v-2c0-2-4-3-6-3ZM8 13c-2.33 0-7 1.17-7 3.5V18h7v-2c0-.85.33-1.57.89-2.18A7.86 7.86 0 0 0 8 13Z"/>
                        </svg>
                    </span>

                    <span>User Management</span>
                </a>

                <div class="cgi-dropdown-divider"></div>
            <?php endif; ?>

            <a href="<?= htmlspecialchars($base . '/logout.php') ?>"
               class="cgi-dropdown-item dropdown-logout">

                <span class="dropdown-item-icon">
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M10 17v2H5V5h5v2h2V3H3v18h9v-4h-2Zm9-5-4-4v3H9v2h6v3l4-4Z"/>
                    </svg>
                </span>

                <span>Log out</span>
            </a>
        </div>
    </div>
</header>
