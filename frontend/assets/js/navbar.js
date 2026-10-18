
/**
 * CGI Navbar — User dropdown interaction
 * Presentation only. Authentication/logout remain handled by V2.
 */

(() => {
    const avatarButton = document.getElementById('avatar-btn');
    const dropdown = document.getElementById('user-dropdown');

    if (!avatarButton || !dropdown) return;

    function setOpen(open) {
        dropdown.hidden = !open;
        avatarButton.setAttribute('aria-expanded', String(open));
    }

    avatarButton.addEventListener('click', (e) => {
        e.stopPropagation();
        setOpen(dropdown.hidden);
    });

    document.addEventListener('click', (event) => {
        if (!event.target.closest('.user-menu')) {
            setOpen(false);
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !dropdown.hidden) {
            setOpen(false);
            avatarButton.focus();
        }
    });
})();
