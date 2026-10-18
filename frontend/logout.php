<?php
require_once __DIR__ . '/api.php';
api_clear_session();
echo '<script>sessionStorage.removeItem("cgi_jwt");</script>';
header('Location: ' . APP_BASE . '/login.php');
exit;
