<?php
require_once __DIR__ . '/api.php';
api_clear_session();
header('Location: ' . APP_BASE . '/login.php');
exit;
