        function withPywebviewApi(callback) {
            function attempt() {
                if (window.pywebview && window.pywebview.api) {
                    callback(window.pywebview.api);
                    return true;
                }
                return false;
            }

            if (attempt()) {
                return;
            }

            window.addEventListener('pywebviewready', function () {
                attempt();
            }, { once: true });

            setTimeout(attempt, 200);
            setTimeout(attempt, 1000);
        }

        var dashboardTimer = (function () {
            var storageKey = 'pypondo.timer.started_at.user.' + document.body.dataset.userId;
            var hourlyRate = JSON.parse(document.body.dataset.hourlyRate);
            var hasDesktopAccess = JSON.parse(document.body.dataset.hasDesktopAccess);
            // Expose a global flag to reliably check access from other helpers
            window._pypondo_has_desktop_access = Boolean(hasDesktopAccess);
            var timeNode = document.getElementById('dashboard-timer-time');
            var costNode = document.getElementById('dashboard-timer-cost');

            function readStartedAt() {
                var rawValue = window.localStorage.getItem(storageKey);
                var parsedValue = parseInt(rawValue, 10);
                return Number.isFinite(parsedValue) && parsedValue > 0 ? parsedValue : null;
            }

            function setAccessState(unlocked) {
                hasDesktopAccess = Boolean(unlocked);
                window._pypondo_has_desktop_access = Boolean(unlocked);
            }

            function ensureStartedAt() {
                if (!hasDesktopAccess) {
                    return null;
                }
                var startedAt = readStartedAt();
                if (!startedAt) {
                    startedAt = Date.now();
                    window.localStorage.setItem(storageKey, String(startedAt));
                }
                return startedAt;
            }

            function formatElapsed(elapsedMs) {
                var totalSeconds = Math.max(Math.floor(elapsedMs / 1000), 0);
                var hours = Math.floor(totalSeconds / 3600);
                var minutes = Math.floor((totalSeconds % 3600) / 60);
                var seconds = totalSeconds % 60;
                return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
            }

            function render() {
                if (!hasDesktopAccess) {
                    window.localStorage.removeItem(storageKey);
                    timeNode.textContent = '00:00:00';
                    costNode.textContent = 'PHP 0.00';
                    // Ensure desktop timer process is stopped when access revoked
                    try {
                        if (window.pywebview && window.pywebview.api && window.pywebview.api.stop_timer) {
                            window.pywebview.api.stop_timer();
                        }
                    } catch (e) {}
                    try { updateDesktopAccessUI(false); } catch (e) {}
                    return;
                }

                var startedAt = ensureStartedAt();
                var elapsedMs = Math.max(Date.now() - startedAt, 0);
                timeNode.textContent = formatElapsed(elapsedMs);
                costNode.textContent = 'PHP ' + ((elapsedMs / 3600000) * hourlyRate).toFixed(2);
            }

            render();
            window.setInterval(render, 1000);

            return {
                ensureStartedAt: ensureStartedAt,
                setAccessState: setAccessState,
                clear: function () {
                    window.localStorage.removeItem(storageKey);
                    timeNode.textContent = '00:00:00';
                    costNode.textContent = 'PHP 0.00';
                }
            };
        })();

        var currentBalance = Number(document.body.dataset.currentBalance);
        var lowBalanceThreshold = 10;

        function updateDesktopAccessUI(unlocked) {
            var btns = document.querySelectorAll('.minimize-timer-btn');
            btns.forEach(function(b) {
                try {
                    var hasMinimizeBalance = currentBalance > 0;
                    b.disabled = false;
                    b.classList.toggle('btn-disabled', !hasMinimizeBalance);
                    b.setAttribute('aria-disabled', hasMinimizeBalance ? 'false' : 'true');
                    if (!hasMinimizeBalance) {
                        b.title = 'No balance available';
                    } else if (currentBalance < lowBalanceThreshold) {
                        b.title = 'Low balance: PHP ' + currentBalance.toFixed(2);
                    } else {
                        b.title = '';
                    }
                } catch (e) {}
            });

            var note = document.getElementById('desktop-access-note');
            if (note) {
                note.textContent = unlocked ? 'You have enough balance to use this PC.' : 'Please add balance before using this PC.';
            }

            // Hide top-up form elements when balance is zero
            var topupForm = document.getElementById('topup-form');
            if (topupForm) {
                topupForm.style.display = unlocked ? '' : 'none';
            }
        }

        // Initialize UI state based on initial server-rendered access
        try { updateDesktopAccessUI(hasDesktopAccess); } catch (e) {}

        function startTimerIfAvailable() {
            var startedAt = dashboardTimer ? dashboardTimer.ensureStartedAt() : null;
            if (!startedAt) {
                return;
            }
            withPywebviewApi(function (api) {
                if (api.start_timer) {
                    api.start_timer(startedAt);
                }
            });
        }

        startTimerIfAvailable();

        function ensureTimerOnClose() {
            var startedAt = dashboardTimer ? dashboardTimer.ensureStartedAt() : null;
            if (!startedAt) {
                return;
            }
            withPywebviewApi(function (api) {
                if (api.start_timer) {
                    api.start_timer(startedAt);
                }
            });
        }

        window.addEventListener('beforeunload', ensureTimerOnClose);
        window.addEventListener('pagehide', ensureTimerOnClose);

        function clearDashboardTimerState() {
            if (dashboardTimer) {
                dashboardTimer.clear();
            }
            withPywebviewApi(function (api) {
                if (api.stop_timer) {
                    api.stop_timer();
                }
            });
            return true;
        }

        function chargeBalance() {
            fetch('/api/charge-balance', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(function (response) {
                return response.json();
            })
            .then(function (result) {
                if (!result.ok) {
                    console.warn('Charge balance failed:', result.message);
                }
            })
            .catch(function (error) {
                console.warn('Charge balance request failed:', error);
            });
        }

        if (JSON.parse(document.body.dataset.hasDesktopAccess)) {
            setTimeout(chargeBalance, 5000);
            setInterval(chargeBalance, 60000);
        }

        var lastLowBalanceWarningTime = 0;
        var lastLowBalance = null;

        function refreshSessionStatus() {
            fetch('/api/session-status', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(function (response) {
                return response.json();
            })
            .then(function (result) {
                if (result.ok) {
                    // Update balance displays
                    currentBalance = Number(result.balance);
                    var balanceText = 'PHP ' + currentBalance.toFixed(2);
                    var topBalanceElement = document.getElementById('user-balance-top');
                    var bottomBalanceElement = document.getElementById('user-balance-bottom');
                    var balanceElements = document.querySelectorAll('[data-balance-display]');
                    if (topBalanceElement) {
                        topBalanceElement.textContent = balanceText;
                    }
                    if (bottomBalanceElement) {
                        bottomBalanceElement.textContent = balanceText;
                    }
                    balanceElements.forEach(function (element) {
                        if (element && element !== topBalanceElement && element !== bottomBalanceElement) {
                            element.textContent = balanceText;
                        }
                    });

                    if (dashboardTimer && typeof dashboardTimer.setAccessState === 'function') {
                        dashboardTimer.setAccessState(currentBalance >= 1);
                        try { updateDesktopAccessUI(currentBalance >= 1); } catch (e) {}
                    }

                    if (currentBalance >= 1) {
                        startTimerIfAvailable();
                    } else if (window.pywebview && window.pywebview.api && window.pywebview.api.stop_timer) {
                        dashboardTimer.clear();
                        window.pywebview.api.stop_timer();
                        try { updateDesktopAccessUI(false); } catch (e) {}
                    }

                    // Update cost display if we have session data
                    if (result.has_session) {
                        var costElement = document.getElementById('dashboard-timer-cost');
                        if (costElement) {
                            costElement.textContent = 'PHP ' + result.cost.toFixed(2);
                        }
                    }

                    // Low balance warning (max 1 warning per 30 seconds)
                    if (currentBalance > 0 && currentBalance < lowBalanceThreshold) {
                        var now = Date.now();
                        if (now - lastLowBalanceWarningTime > 30000 || lastLowBalance !== currentBalance) {
                            var minimizeBtn = document.querySelector('.minimize-timer-btn');
                            if (minimizeBtn) {
                                minimizeBtn.title = 'Low balance: ' + balanceText;
                            }
                            lastLowBalanceWarningTime = now;
                            lastLowBalance = currentBalance;
                        }
                    }
                }
            })
            .catch(function (error) {
                console.warn('Session status refresh failed:', error);
            });
        }

        // Refresh session status every 3 seconds for live updates
        setInterval(refreshSessionStatus, 3000);
        // Initial refresh
        setTimeout(refreshSessionStatus, 1000);

        function handleMinimizeClickDesktop(event) {
            if (currentBalance <= 0) {
                event.preventDefault();
                event.stopPropagation();
                alert('You have no balance in your account. Please top up to use the desktop.');
                return false;
            }
            if (currentBalance < lowBalanceThreshold) {
                alert('Your balance is low. Please top up soon. Recommended minimum balance is PHP ' + lowBalanceThreshold.toFixed(2) + '.');
            }
            minimizeClientApp();
            return true;
        }

        function minimizeClientApp() {
            withPywebviewApi(function (api) {
                if (api.minimize) {
                    Promise.resolve(api.minimize())
                        .catch(function (e) {
                            console.warn('Minimize API failed:', e);
                            if (typeof window.close === 'function') {
                                window.close();
                            } else {
                                window.blur();
                            }
                        });
                    return;
                }
                if (typeof window.close === 'function') {
                    window.close();
                } else {
                    window.blur();
                }
            });
        }
        

        function setTopup(amount) {
            var field = document.getElementById('topupAmount');
            if (field) {
                field.value = amount;
            }
        }

        // Termination dialog functionality
        let terminateDialog = document.getElementById('terminate-dialog');
        let secretKeyInput = document.getElementById('secret-key');
        let terminateBtn = document.getElementById('terminate-btn');
        let cancelBtn = document.getElementById('cancel-btn');

        // Listen for Ctrl+Shift+T to show termination dialog
        document.addEventListener('keydown', function(event) {
            if (event.ctrlKey && event.shiftKey && event.key === 'T') {
                event.preventDefault();
                terminateDialog.style.display = 'flex';
                secretKeyInput.focus();
            }
        });

        // Handle terminate button click
        terminateBtn.addEventListener('click', function() {
            let secretKey = secretKeyInput.value.trim();
            if (window.pywebview && window.pywebview.api && window.pywebview.api.terminate) {
                let result = window.pywebview.api.terminate(secretKey);
                if (result) {
                    terminateDialog.style.display = 'none';
                    alert('Application will terminate.');
                } else {
                    alert('Invalid secret key!');
                    secretKeyInput.value = '';
                    secretKeyInput.focus();
                }
            }
        });

        // Handle cancel button click
        cancelBtn.addEventListener('click', function() {
            terminateDialog.style.display = 'none';
            secretKeyInput.value = '';
        });

        // Handle Enter key in input
        secretKeyInput.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                terminateBtn.click();
            } else if (event.key === 'Escape') {
                cancelBtn.click();
            }
        });

        // Close dialog when clicking outside
        terminateDialog.addEventListener('click', function(event) {
            if (event.target === terminateDialog) {
                cancelBtn.click();
            }
        });
    

document.querySelectorAll('[data-action="minimize-desktop"]').forEach(function (el) {
    el.addEventListener('click', handleMinimizeClickDesktop);
});
document.querySelectorAll('[data-action="clear-timer-state"]').forEach(function (el) {
    el.addEventListener('click', clearDashboardTimerState);
});
document.querySelectorAll('[data-action="set-topup"]').forEach(function (btn) {
    btn.addEventListener('click', function () { setTopup(Number(btn.dataset.amount)); });
});
