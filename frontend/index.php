<?php
require_once __DIR__ . '/api.php';
api_require_auth();
header('Location: ' . APP_BASE . '/dashboard.php');
exit;
