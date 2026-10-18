(() => {
    const initialize = () => {
        const form = document.getElementById('configuration-form');
        const submitButton = document.getElementById('save-configuration');
        if (!form || !submitButton) return;

        form.querySelectorAll('input[type="number"]').forEach((input) => {
            const valueOutput = form.querySelector(`[data-value-for="${input.name}"]`);

            input.addEventListener('input', () => {
                input.closest('.cgi-configuration-card')?.classList.toggle('is-invalid', !input.validity.valid);
                if (valueOutput) valueOutput.textContent = input.value || '0.0000';
            });

            input.addEventListener('blur', () => {
                if (input.value !== '' && input.validity.valid) {
                    input.value = Number(input.value).toFixed(4);
                    if (valueOutput) valueOutput.textContent = input.value;
                }
            });
        });

        form.addEventListener('submit', () => {
            if (!form.checkValidity()) return;
            submitButton.disabled = true;
            submitButton.querySelector('span').textContent = 'Saving Changes...';
        });
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }
})();
