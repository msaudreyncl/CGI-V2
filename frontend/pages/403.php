<?php require_once __DIR__ . '/../api.php'; ?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>403 Forbidden — CGI</title>
<link rel="stylesheet" href="<?= APP_BASE ?>/assets/css/main.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
</head>
<body class="d-flex align-items-center justify-content-center min-vh-100 bg-light">
<div class="text-center">
    <h1 class="display-4 fw-bold text-danger">403</h1>
    <p class="text-muted">You do not have permission to access this page.</p>
    <a href="<?= APP_BASE ?>/dashboard.php" class="btn btn-success">← Back to Dashboard</a>
</div>
</body>
</html>
