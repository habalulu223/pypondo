    (function() {
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            document.dispatchEvent(new CustomEvent('startupSequenceComplete'));
            return;
        }

        if (!document.body || !document.body.classList.contains('startup-active')) {
            return;
        }

        var minimumIntroMs = 5700;
        var lanTimeoutMs = 10000;
        var startedAt = Date.now();
        var statusNode = document.querySelector('.startup-splash__status');
        var completed = false;

        function setStatus(message) {
            if (statusNode) {
                statusNode.classList.add('startup-splash__status--live');
                statusNode.textContent = message;
            }
        }

        function completeStartup() {
            if (completed) {
                return;
            }
            completed = true;
            document.dispatchEvent(new CustomEvent('startupSequenceComplete'));
        }

        function finishAfterIntro() {
            var remainingMs = Math.max(minimumIntroMs - (Date.now() - startedAt), 0);
            window.setTimeout(completeStartup, remainingMs);
        }

        // The splash is now tied to the actual LAN response instead of a fixed
        // delay. This confirms that the server hosting the next page is ready
        // before the login UI is made available.
        var controller = window.AbortController ? new AbortController() : null;
        var timeoutId = window.setTimeout(function() {
            if (controller) {
                controller.abort();
            }
        }, lanTimeoutMs);

        setStatus('Checking LAN connection');
        fetch('/api/server-info', {
            cache: 'no-store',
            signal: controller ? controller.signal : undefined
        })
            .then(function(response) {
                if (!response.ok) {
                    throw new Error('LAN server did not respond successfully.');
                }
                setStatus('LAN connected — opening Techpulse Admin');
            })
            .catch(function() {
                // The page is already served by this host, so let the user
                // continue after a bounded retry period even if the health
                // endpoint is temporarily unavailable.
                setStatus('LAN check timed out — continuing offline');
            })
            .then(function() {
                window.clearTimeout(timeoutId);
                finishAfterIntro();
            });
    })();
