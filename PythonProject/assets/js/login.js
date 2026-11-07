        var passwordInput = document.getElementById('password');
        var togglePasswordButton = document.getElementById('toggle-password');
        if (passwordInput && togglePasswordButton) {
            function syncEyeVisibility() {
                togglePasswordButton.classList.toggle('is-visible', passwordInput.value.length > 0);
            }
            passwordInput.addEventListener('input', syncEyeVisibility);
            togglePasswordButton.addEventListener('click', function() {
                var show = passwordInput.type === 'password';
                passwordInput.type = show ? 'text' : 'password';
                document.getElementById('eye-icon').classList.toggle('is-closed', show);
                togglePasswordButton.setAttribute('aria-pressed', String(show));
                togglePasswordButton.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
                togglePasswordButton.setAttribute('title', show ? 'Hide password' : 'Show password');
            });
            syncEyeVisibility();
        }

        document.addEventListener('startupSequenceComplete', function() {
            document.body.classList.remove('startup-active');
            document.body.classList.add('startup-complete');
        });

        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            document.body.classList.remove('startup-active');
            document.body.classList.add('startup-complete');
        }

        // Keep kiosk lock enabled on login page until a user/admin is authenticated.
        if (window.pywebview && window.pywebview.api && window.pywebview.api.enable_kiosk_lock) {
            window.pywebview.api.enable_kiosk_lock();
        }

        function isTypingField(target) {
            if (!target || !target.tagName) {
                return false;
            }
            var tag = target.tagName.toLowerCase();
            return tag === 'input' || tag === 'textarea' || target.isContentEditable;
        }

        // Block Windows shortcuts and dangerous key combinations when not logged in
        document.addEventListener('keydown', function(event) {
            if (isTypingField(event.target) || isTypingField(document.activeElement)) {
                if (
                    (event.altKey && event.key === 'Tab') ||
                    (event.altKey && event.key === 'Escape') ||
                    (event.ctrlKey && event.altKey && event.key === 'Delete') ||
                    event.key === 'Meta' ||
                    event.key === 'Win' ||
                    event.key === 'OS' ||
                    event.keyCode === 91 || event.keyCode === 92 ||
                    (event.code && event.code.toLowerCase().includes('meta')) ||
                    (event.altKey && event.key === 'F4') ||
                    (event.ctrlKey && event.key === 'w') ||
                    (event.ctrlKey && event.key === 'W') ||
                    (event.ctrlKey && event.key === 'Escape') ||
                    (event.ctrlKey && event.altKey && event.key === 'Escape')
                ) {
                    event.preventDefault();
                    return false;
                }
                return;
            }

            if (
                (event.altKey && event.key === 'Tab') ||
                (event.altKey && event.key === 'Escape') ||
                (event.ctrlKey && event.altKey && event.key === 'Delete') ||
                event.key === 'Meta' ||
                event.key === 'Win' ||
                event.key === 'OS' ||
                event.keyCode === 91 || event.keyCode === 92 ||
                (event.code && event.code.toLowerCase().includes('meta')) ||
                (event.altKey && event.key === 'F4') ||
                (event.ctrlKey && event.key === 'w') ||
                (event.ctrlKey && event.key === 'W') ||
                (event.ctrlKey && event.key === 'Escape') ||
                (event.ctrlKey && event.altKey && event.key === 'Escape')
            ) {
                event.preventDefault();
                return false;
            }
        });
    
