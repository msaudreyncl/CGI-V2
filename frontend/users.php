<?php
require_once __DIR__ . '/api.php';
api_require_auth(['admin']);

$me = api_current_user();
$user = $me;

$flash = $_SESSION['users_flash'] ?? null;
unset($_SESSION['users_flash']);

$msg = is_array($flash)
    ? (string)($flash['message'] ?? '')
    : '';
$msg_type = is_array($flash)
    ? (string)($flash['type'] ?? 'success')
    : 'success';

if ($_SERVER['REQUEST_METHOD'] === 'POST'
    && ($_POST['action'] ?? '') === 'create') {

    $r = api_request('POST', '/api/auth/register', [
        'name' => trim($_POST['name'] ?? ''),
        'email' => trim($_POST['email'] ?? ''),
        'password' => $_POST['password'] ?? '',
        'role' => $_POST['role'] ?? 'farmer',
    ]);

    if ($r['status'] === 201) {
        $_SESSION['users_flash'] = [
            'message' => 'User <strong>' .
                htmlspecialchars($r['data']['name'] ?? '') .
                '</strong> created successfully.',
            'type' => 'success',
        ];
    } else {
        $_SESSION['users_flash'] = [
            'message' => htmlspecialchars(
                $r['data']['detail'] ?? 'Error creating user.'
            ),
            'type' => 'danger',
        ];
    }

    header('Location: users.php', true, 303);
    exit;
}

$users_resp = api_request('GET', '/api/users');
$all_users = api_response_list($users_resp);

$stats_resp = api_request('GET', '/api/users/stats');
$user_stats = $stats_resp['status'] === 200 && is_array($stats_resp['data'])
    ? $stats_resp['data']
    : [];

function users_escape($value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function fmt_last_login(?string $iso): string {
    if (!$iso) {
        return '<span class="text-muted">Never</span>';
    }

    try {
        $dt = new DateTime($iso, new DateTimeZone('UTC'));
        $dt->setTimezone(new DateTimeZone('Asia/Manila'));
        return users_escape($dt->format('M d, Y, g:i A'));
    } catch (Exception $e) {
        return users_escape($iso);
    }
}

$stat_cards = [
    ['total_users', 'Total Users', 'Registered accounts', 'users'],
    ['total_administrators', 'Administrators', 'Administrative access', 'shield'],
    ['total_officers', 'Cooperative Officers', 'Cooperative access', 'briefcase'],
    ['total_farmers', 'Farmers', 'Farmer accounts', 'leaf'],
    ['total_active', 'Active Accounts', 'Currently authorized', 'check'],
];
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1, viewport-fit=cover">

    <title>User Management | CGI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400;500;600;700&family=Work+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet">

    <link rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">

    <link rel="stylesheet"
          href="<?= users_escape(APP_BASE) ?>/assets/css/main.css">

    <link rel="stylesheet"
          href="<?= users_escape(APP_BASE) ?>/assets/css/navbar.css?v=3">

    <link rel="stylesheet"
          href="<?= users_escape(APP_BASE) ?>/assets/css/users.css?v=4">
</head>

<body class="cgi-users-body">

<?php include __DIR__ . '/components/navbar.php'; ?>

<main class="cgi-users-page">

    <!-- Page Header -->
    <section class="cgi-users-hero">
        <div class="cgi-users-hero-title">
            <div class="cgi-users-hero-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                    <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3ZM8 11c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3Zm8 2c-2 0-6 1-6 3v2h12v-2c0-2-4-3-6-3ZM8 13c-2.33 0-7 1.17-7 3.5V18h7v-2c0-.85.33-1.57.89-2.18A7.86 7.86 0 0 0 8 13Z"/>
                </svg>
            </div>

            <div>
                <span class="cgi-users-eyebrow">
                    SYSTEM ADMINISTRATION
                </span>
                <h1>User Management</h1>
            </div>
        </div>

        <button type="button"
                class="btn cgi-users-add"
                data-bs-toggle="modal"
                data-bs-target="#addUserModal">
            <span aria-hidden="true">+</span>
            Add User
        </button>
    </section>

    <!-- Server feedback is promoted to the shared toast by users.js. -->
    <?php if ($msg): ?>
        <div id="serverAlert"
             data-toast-type="<?= users_escape($msg_type) ?>"
             hidden>
            <?= $msg ?>
        </div>
    <?php endif; ?>

    <!-- Floating feedback popup (one active notification at a time). -->
    <div class="cgi-users-toast-region"
         aria-live="polite"
         aria-atomic="true">
        <div class="cgi-users-toast d-none"
             id="jsAlert"
             role="status">
            <span class="cgi-users-toast-icon"
                  id="jsAlertIcon"
                  aria-hidden="true"></span>
            <span class="cgi-users-toast-message"
                  id="jsAlertMsg"></span>
            <button type="button"
                    class="cgi-users-toast-close"
                    id="jsAlertClose"
                    aria-label="Dismiss notification">&times;</button>
        </div>
    </div>

    <!-- Statistics -->
    <section class="cgi-users-stats"
             aria-label="User account statistics">

        <?php foreach ($stat_cards as [$key, $label, $hint, $icon]): ?>
            <article class="cgi-users-stat-card">
                <div class="cgi-users-stat-icon" aria-hidden="true">
                    <?php if ($icon === 'users'): ?>
                        <span>&#9823;</span>
                    <?php elseif ($icon === 'shield'): ?>
                        <span>&#9670;</span>
                    <?php elseif ($icon === 'briefcase'): ?>
                        <span>&#9635;</span>
                    <?php elseif ($icon === 'leaf'): ?>
                        <span>&#10047;</span>
                    <?php else: ?>
                        <span>&#10003;</span>
                    <?php endif; ?>
                </div>

                <div class="cgi-users-stat-content">
                    <span><?= users_escape($label) ?></span>
                    <strong id="stat-<?= users_escape($key) ?>">
                        <?= (int)($user_stats[$key] ?? 0) ?>
                    </strong>
                    <small><?= users_escape($hint) ?></small>
                </div>
            </article>
        <?php endforeach; ?>
    </section>

    <!-- Users Panel -->
    <section class="cgi-users-panel">
        <!-- Search and Filters -->
        <div class="cgi-users-toolbar">

            <label class="cgi-users-search" for="userSearch">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="m21 19-5.2-5.2A7 7 0 1 0 14 15.8L19 21l2-2ZM5 10a5 5 0 1 1 10 0 5 5 0 0 1-10 0Z"/>
                </svg>

                <input type="search"
                       id="userSearch"
                       placeholder="Search User ID, name, or email..."
                       autocomplete="off">
            </label>

            <div class="cgi-users-filters">

                <label class="cgi-users-filter" for="roleFilter">
                    <span>Role</span>
                    <select id="roleFilter">
                        <option value="">All roles</option>
                        <option value="admin">Administrator</option>
                        <option value="officer">Cooperative Officer</option>
                        <option value="farmer">Farmer</option>
                    </select>
                </label>

                <label class="cgi-users-filter" for="statusFilter">
                    <span>Status</span>
                    <select id="statusFilter">
                        <option value="">All statuses</option>
                        <option value="active">Active</option>
                        <option value="inactive">Inactive</option>
                    </select>
                </label>

                <button type="button"
                        class="cgi-users-reset"
                        id="resetUserFilters">
                    Reset
                </button>
            </div>
        </div>

        <!-- User Table -->
        <div class="cgi-users-table-wrap">
            <table class="table cgi-users-table" id="userTable">
                <thead>
                    <tr>
                        <th>User ID</th>
                        <th>User</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Last Login</th>
                        <th>Actions</th>
                    </tr>
                </thead>

                <tbody>
                <?php foreach ($all_users as $u):
                    $is_me = (string)$u['id'] === (string)$me['id'];
                    $is_protected = !empty($u['is_protected']);
                    $name = (string)($u['name'] ?? '');
                    $initials = strtoupper(substr($name, 0, 1));
                ?>
                    <tr id="row-<?= (int)$u['id'] ?>"
                        class="user-row"
                        data-search="<?= users_escape(strtolower(
                            ($u['user_id_display'] ?? '') . ' ' .
                            $name . ' ' . ($u['email'] ?? '')
                        )) ?>"
                        data-role="<?= users_escape($u['role']) ?>"
                        data-status="<?= $u['is_active'] ? 'active' : 'inactive' ?>">

                        <td>
                            <code><?= users_escape($u['user_id_display'] ?? '-') ?></code>
                        </td>

                        <td>
                            <div class="cgi-users-person">
                                <span class="cgi-users-initial" aria-hidden="true">
                                    <?= users_escape($initials) ?>
                                </span>
                                <strong><?= users_escape($name) ?></strong>
                            </div>
                        </td>

                        <td class="cgi-users-email">
                            <?= users_escape($u['email']) ?>
                        </td>

                        <td>
                            <span class="cgi-users-role cgi-users-role-<?= users_escape($u['role']) ?>">
                                <?= users_escape(ucfirst($u['role'])) ?>
                            </span>
                        </td>

                        <td id="status-<?= (int)$u['id'] ?>">
                            <?php if ($u['is_active']): ?>
                                <span class="badge bg-success">Active</span>
                            <?php else: ?>
                                <span class="badge bg-secondary">Inactive</span>
                            <?php endif; ?>
                        </td>

                        <td class="cgi-users-last-login">
                            <?= fmt_last_login($u['last_login_at'] ?? null) ?>
                        </td>

                        <td>
                            <div class="cgi-users-actions">

                                <?php if (!$is_protected): ?>
                                    <button type="button"
                                            class="btn btn-sm btn-outline-primary btn-edit"
                                            data-id="<?= (int)$u['id'] ?>"
                                            data-name="<?= users_escape($name) ?>"
                                            data-email="<?= users_escape($u['email']) ?>"
                                            data-role="<?= users_escape($u['role']) ?>">
                                        Edit
                                    </button>
                                <?php endif; ?>

                                <?php if ($is_protected): ?>
                                    <span class="badge bg-dark"
                                          title="The original System Admin account cannot be edited, deactivated, or deleted.">
                                        Protected
                                    </span>

                                <?php elseif (!$is_me): ?>
                                    <button type="button"
                                            class="btn btn-sm <?= $u['is_active'] ? 'btn-outline-warning' : 'btn-outline-success' ?> btn-toggle"
                                            data-id="<?= (int)$u['id'] ?>"
                                            data-active="<?= $u['is_active'] ? '1' : '0' ?>"
                                            data-name="<?= users_escape($name) ?>">
                                        <?= $u['is_active'] ? 'Deactivate' : 'Activate' ?>
                                    </button>

                                    <button type="button"
                                            class="btn btn-sm btn-outline-danger btn-delete"
                                            data-id="<?= (int)$u['id'] ?>"
                                            data-name="<?= users_escape($name) ?>">
                                        Delete
                                    </button>
                                <?php else: ?>
                                    <span class="text-muted small fst-italic">
                                        You
                                    </span>
                                <?php endif; ?>

                            </div>
                        </td>
                    </tr>
                <?php endforeach; ?>

                    <tr id="noUsersMatch" class="d-none">
                        <td colspan="7"
                            class="text-center text-muted py-4">
                            No users match your search and filters.
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="cgi-users-panel-footer" id="showingUsersLabel">
            Showing <?= count($all_users) ?> users
        </div>
    </section>
</main>

<!-- Add User Modal -->
<div class="modal fade"
     id="addUserModal"
     tabindex="-1"
     aria-labelledby="addUserModalTitle"
     aria-hidden="true">

    <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content">
            <form method="POST" id="addUserForm" novalidate>
                <input type="hidden" name="action" value="create">

                <div class="modal-header">
                    <div>
                        <span class="cgi-users-eyebrow">NEW SYSTEM ACCOUNT</span>
                        <h5 class="modal-title" id="addUserModalTitle">
                            Add User
                        </h5>
                        <p class="cgi-users-modal-description">
                            Create an account authorized to access CGI.
                        </p>
                    </div>

                    <button type="button"
                            class="btn-close"
                            data-bs-dismiss="modal"
                            aria-label="Close"></button>
                </div>

                <div class="modal-body">
                    <div class="mb-3">
                        <label for="addName" class="form-label">Full Name</label>
                        <input type="text"
                               name="name"
                               id="addName"
                               class="form-control"
                               required>
                    </div>

                    <div class="mb-3">
                        <label for="addEmail" class="form-label">Email</label>
                        <input type="email"
                               name="email"
                               id="addEmail"
                               class="form-control"
                               required>
                    </div>

                    <div class="mb-3">
                        <label for="addPassword" class="form-label">Password</label>
                        <input type="password"
                               name="password"
                               id="addPassword"
                               class="form-control"
                               minlength="8"
                               autocomplete="new-password"
                               required>
                        <div class="form-text">Minimum 8 characters.</div>
                    </div>

                    <div class="mb-3">
                        <label for="addRole" class="form-label">Role</label>
                        <select name="role"
                                id="addRole"
                                class="form-select"
                                required>
                            <option value="farmer">Farmer</option>
                            <option value="officer">Cooperative Officer</option>
                            <option value="admin">Administrator</option>
                        </select>
                    </div>
                </div>

                <div class="modal-footer">
                    <button type="button"
                            class="btn btn-secondary"
                            data-bs-dismiss="modal">
                        Cancel
                    </button>
                    <button type="submit" class="btn btn-success">
                        Create User
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- Edit User Modal -->
<div class="modal fade"
     id="editUserModal"
     tabindex="-1"
     aria-labelledby="editUserModalTitle"
     aria-hidden="true">

    <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable">
        <div class="modal-content">

            <div class="modal-header">
                <div>
                    <span class="cgi-users-eyebrow">ACCOUNT DETAILS</span>
                    <h5 class="modal-title" id="editUserModalTitle">
                        Edit User
                    </h5>
                    <p class="cgi-users-modal-description">
                        Update account information and access level.
                    </p>
                </div>

                <button type="button"
                        class="btn-close"
                        data-bs-dismiss="modal"
                        aria-label="Close"></button>
            </div>

            <div class="modal-body">
                <input type="hidden" id="editUserId">

                <div class="mb-3">
                    <label for="editName" class="form-label">Full Name</label>
                    <input type="text"
                           id="editName"
                           class="form-control"
                           required>
                </div>

                <div class="mb-3">
                    <label for="editEmail" class="form-label">Email</label>
                    <input type="email"
                           id="editEmail"
                           class="form-control"
                           required>
                </div>

                <div class="mb-3">
                    <label for="editRole" class="form-label">Role</label>
                    <select id="editRole" class="form-select">
                        <option value="farmer">Farmer</option>
                        <option value="officer">Cooperative Officer</option>
                        <option value="admin">Administrator</option>
                    </select>
                </div>

                <div class="mb-3">
                    <label for="editPassword" class="form-label">
                        New Password
                        <span class="text-muted">
                            (leave blank to keep current)
                        </span>
                    </label>
                    <input type="password"
                           id="editPassword"
                           class="form-control"
                           minlength="8"
                           autocomplete="new-password">
                </div>

                <div id="editError" class="d-none" aria-hidden="true"></div>
            </div>

            <div class="modal-footer">
                <button type="button"
                        class="btn btn-secondary"
                        data-bs-dismiss="modal">
                    Cancel
                </button>
                <button type="button"
                        class="btn btn-primary"
                        id="saveEditBtn">
                    Save Changes
                </button>
            </div>

        </div>
    </div>
</div>

<!-- Reusable action confirmation popup. -->
<div class="modal fade cgi-users-confirm-modal"
     id="userActionConfirmModal"
     tabindex="-1"
     aria-labelledby="userActionConfirmTitle"
     aria-describedby="userActionConfirmMessage"
     aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content">
            <div class="cgi-users-confirm-icon"
                 id="userActionConfirmIcon"
                 aria-hidden="true">!</div>
            <div class="modal-body">
                <h2 class="modal-title" id="userActionConfirmTitle">
                    Confirm action
                </h2>
                <p class="cgi-users-confirm-user"
                   id="userActionConfirmUser"></p>
                <p class="cgi-users-confirm-message"
                   id="userActionConfirmMessage"></p>
            </div>
            <div class="modal-footer">
                <button type="button"
                        class="btn btn-secondary"
                        id="userActionCancelBtn">
                    Cancel
                </button>
                <button type="button"
                        class="btn btn-primary"
                        id="userActionConfirmBtn">
                    Confirm
                </button>
            </div>
        </div>
    </div>
</div>

<?php api_inject_jwt_script(); ?>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

<script>
    window.CGI_BASE = <?= json_encode(APP_BASE) ?>;
    window.CGI_API_BASE = <?= json_encode(API_BASE) ?>;
</script>

<script src="<?= users_escape(APP_BASE) ?>/assets/js/navbar.js?v=3"></script>
<script src="<?= users_escape(APP_BASE) ?>/assets/js/users.js?v=3"></script>
</body>
</html>
