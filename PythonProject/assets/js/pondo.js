        function isTypingField(target) {
            if (!target || !target.tagName) {
                return false;
            }
            var tag = target.tagName.toLowerCase();
            return tag === 'input' || tag === 'textarea' || target.isContentEditable;
        }

        // Block Windows shortcuts and dangerous key combinations
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
    
