/**
 * assets/js/api.js — Shared fetch wrapper that injects the JWT from sessionStorage.
 *
 * Pages that need authenticated API calls include this script and use window.CGI_API.
 * The JWT is stored in sessionStorage under the key "cgi_jwt".
 *
 * Usage:
 *   const resp = await CGI_API.get('/api/dashboard/summary');
 *   const data = await resp.json();
 *
 *   const resp = await CGI_API.post('/api/transactions', { inspection_id: 1, ... });
 */
(function (global) {
    const API_BASE = window.CGI_API_BASE || '';

    function getToken() {
        return sessionStorage.getItem('cgi_jwt') || '';
    }

    function headers(extra) {
        const h = { 'Content-Type': 'application/json' };
        const token = getToken();
        if (token) h['Authorization'] = 'Bearer ' + token;
        return Object.assign(h, extra || {});
    }

    function request(method, path, body) {
        const opts = {
            method:  method,
            headers: headers(),
        };
        if (body !== undefined && body !== null) {
            opts.body = JSON.stringify(body);
        }
        return fetch(API_BASE + path, opts).then(resp => {
            if (resp.status === 401) {
                // Token expired — redirect to login
                sessionStorage.removeItem('cgi_jwt');
                window.location.href = (window.CGI_BASE || '') + '/login.php';
            }
            return resp;
        });
    }

    global.CGI_API = {
        get:    (path)        => request('GET',    path),
        post:   (path, body)  => request('POST',   path, body),
        put:    (path, body)  => request('PUT',    path, body),
        del:    (path)        => request('DELETE', path),
    };

})(window);
