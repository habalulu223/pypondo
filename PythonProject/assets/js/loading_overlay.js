(function() {
    var overlay = document.getElementById('pypondo-loading-overlay');
    var message = document.getElementById('pypondo-loading-message');
    var timer = document.getElementById('pypondo-loading-timer');
    var startTime = null;
    var timerInterval = null;

    function formatTime(ms) {
        var seconds = Math.floor(ms / 1000);
        var minutes = Math.floor(seconds / 60);
        seconds = seconds % 60;
        if (minutes > 0) {
            return minutes + 'm ' + seconds + 's';
        }
        return seconds + 's';
    }

    function updateTimer() {
        if (!startTime) return;
        var elapsed = Date.now() - startTime;
        var timeStr = formatTime(elapsed);
        if (timer) {
            timer.textContent = 'Elapsed: ' + timeStr;
        }
    }

    function showLoading(text) {
        if (!overlay) return;
        if (text) message.textContent = text;
        
        startTime = Date.now();
        if (timerInterval) clearInterval(timerInterval);
        if (timer) timer.textContent = 'Elapsed: 0s';
        timerInterval = setInterval(updateTimer, 500);
        
            // Enforce a maximum visible loading time (10 seconds) then refresh
            if (window._pypondoLoadingMaxTimeout) clearTimeout(window._pypondoLoadingMaxTimeout);
            window._pypondoLoadingMaxTimeout = setTimeout(function() {
                try {
                    message.textContent = 'Taking too long — refreshing the page.';
                } catch (e) {}
                // Give a short moment for message to render, then reload
                setTimeout(function() { window.location.reload(true); }, 800);
            }, 10000);

        overlay.classList.add('pypondo-loading-show');
    }

    function hideLoading() {
        if (!overlay) return;
        overlay.classList.remove('pypondo-loading-show');
        if (timerInterval) clearInterval(timerInterval);
        startTime = null;
            if (window._pypondoLoadingMaxTimeout) {
                clearTimeout(window._pypondoLoadingMaxTimeout);
                window._pypondoLoadingMaxTimeout = null;
            }
        if (timer) timer.textContent = '';
    }

    function showLoadingWithTime(text, responseTimeMs) {
        hideLoading();
        if (text && responseTimeMs) {
            message.textContent = text;
            if (timer) {
                timer.textContent = 'Completed in ' + formatTime(responseTimeMs);
            }
            overlay.classList.add('pypondo-loading-show');
            setTimeout(hideLoading, 2000);
        }
    }

    function shouldShowLink(anchor) {
        if (!anchor.href) return false;
        if (anchor.target && anchor.target !== '_self') return false;
        if (anchor.dataset.noLoading !== undefined) return false;
        if (anchor.href.startsWith('javascript:')) return false;
        if (anchor.href.indexOf('#') === 0) return false;
        return true;
    }

    function attachHandlers() {
        document.querySelectorAll('form').forEach(function(form) {
            form.addEventListener('submit', function(e) {
                showLoading('Running request, please wait...');
                var submit = form.querySelector('button[type=submit], input[type=submit]');
                if (submit) submit.disabled = true;
                
                // Intercept form submission to capture timing
                var originalAction = form.action;
                var originalMethod = form.method || 'POST';
                var originalTarget = form.target;
                
                setTimeout(function() {
                    // Re-enable tracking on page reload
                    window.addEventListener('beforeunload', function() {
                        if (timerInterval) clearInterval(timerInterval);
                    });
                }, 100);
            });
        });

        document.querySelectorAll('a').forEach(function(anchor) {
            if (shouldShowLink(anchor)) {
                anchor.addEventListener('click', function() {
                    showLoading('Opening page, please wait...');
                    var href = anchor.href;
                    
                    // For API calls, try to intercept and show timing
                    if (href && href.includes('/api/')) {
                        setTimeout(function() {
                            fetch(href)
                                .then(function(response) {
                                    var timeHeader = response.headers.get('X-Response-Time');
                                    if (timeHeader) {
                                        showLoadingWithTime('Request completed', parseInt(timeHeader));
                                    }
                                })
                                .catch(function() {
                                    // Continue with normal navigation
                                });
                        }, 100);
                    }
                });
            }
        });

        document.querySelectorAll('button').forEach(function(button) {
            if (button.dataset.noLoading !== undefined) return;
            if (button.dataset.loadingNav !== undefined || button.dataset.tabSwitch !== undefined) {
                if (button.type === 'button' || button.type === 'submit' || button.type === '') {
                    button.addEventListener('click', function() {
                        showLoading('Switching view, please wait...');
                    });
                }
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachHandlers);
    } else {
        attachHandlers();
    }

    window.pypondoShowLoading = showLoading;
    window.pypondoHideLoading = hideLoading;
    window.pypondoShowLoadingWithTime = showLoadingWithTime;
})();
