        function showDesktopAccessBlockedMessage() {
            window.alert('insuficient balance please top up');
            var walletCard = document.getElementById('wallet-card');
            if (walletCard) {
                walletCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }

        function withPywebviewApi(callback) {
            if (window.pywebview && window.pywebview.api) {
                callback(window.pywebview.api);
                return;
            }
            window.addEventListener('pywebviewready', function () {
                if (window.pywebview && window.pywebview.api) {
                    callback(window.pywebview.api);
                }
            }, { once: true });
        }

        withPywebviewApi(function (api) {
            if (api.enable_kiosk_lock) {
                api.enable_kiosk_lock();
            }
        });

        function formatLocalDate(date) {
            return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
        }

        function formatLocalTime(date) {
            return String(date.getHours()).padStart(2, '0') + ':' + String(date.getMinutes()).padStart(2, '0');
        }

        function wireBookingForms() {
            var leadMinutes = JSON.parse(document.body.dataset.bookingLeadMinutes);
            var bookingForms = document.querySelectorAll('form.booking-form');

            bookingForms.forEach(function (form) {
                var dateInput = form.querySelector('input.booking-date-input');
                var timeInput = form.querySelector('input.booking-time-input');
                if (!dateInput || !timeInput) {
                    return;
                }

                function syncConstraints() {
                    var now = new Date();
                    var cutoff = new Date(now.getTime() + leadMinutes * 60000);
                    var today = formatLocalDate(now);
                    var cutoffDate = formatLocalDate(cutoff);

                    dateInput.min = today;
                    if (!dateInput.value || dateInput.value < cutoffDate) {
                        dateInput.value = cutoffDate;
                    }

                    if (dateInput.value === cutoffDate) {
                        var minTime = formatLocalTime(cutoff);
                        timeInput.min = minTime;
                        if (!timeInput.value || timeInput.value < minTime) {
                            timeInput.value = minTime;
                        }
                        return;
                    }

                    timeInput.min = '';
                }

                dateInput.addEventListener('change', syncConstraints);
                timeInput.addEventListener('focus', syncConstraints);
                syncConstraints();
            });
        }

        wireBookingForms();

        var dashboardTimer = (function () {
            var storageKey = 'pypondo.timer.started_at.user.' + document.body.dataset.userId;
            var hourlyRate = JSON.parse(document.body.dataset.hourlyRate);
            var hasDesktopAccess = JSON.parse(document.body.dataset.hasDesktopAccess);
            var timeNode = document.getElementById('dashboard-timer-time');
            var costNode = document.getElementById('dashboard-timer-cost');
            var noteNode = document.getElementById('dashboard-timer-note');
            var desktopLinkNode = document.getElementById('desktop-access-link');

            function readStartedAt() {
                var rawValue = window.localStorage.getItem(storageKey);
                var parsedValue = parseInt(rawValue, 10);
                return Number.isFinite(parsedValue) && parsedValue > 0 ? parsedValue : null;
            }

            function setAccessState(unlocked) {
                hasDesktopAccess = Boolean(unlocked);
                if (desktopLinkNode) {
                    if (hasDesktopAccess) {
                        desktopLinkNode.textContent = 'Go To Desktop';
                        desktopLinkNode.href = document.body.dataset.desktopUrl;
                        desktopLinkNode.dataset.enabled = 'true';
                        desktopLinkNode.onclick = null;
                    } else {
                        desktopLinkNode.textContent = 'Top Up to Unlock Desktop';
                        desktopLinkNode.href = '#';
                        desktopLinkNode.dataset.enabled = 'false';
                        desktopLinkNode.onclick = function (event) {
                            event.preventDefault();
                            showDesktopAccessBlockedMessage();
                        };
                    }
                }
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
                    noteNode.textContent = 'Add credits below to unlock desktop access and start the timer.';
                    return;
                }

                var startedAt = ensureStartedAt();
                if (!startedAt) {
                    timeNode.textContent = '00:00:00';
                    costNode.textContent = 'PHP 0.00';
                    noteNode.textContent = 'Open desktop access or minimize the app to start the timer, then it will stay visible here as well.';
                    return;
                }

                var elapsedMs = Math.max(Date.now() - startedAt, 0);
                timeNode.textContent = formatElapsed(elapsedMs);
                costNode.textContent = 'PHP ' + ((elapsedMs / 3600000) * hourlyRate).toFixed(2);
                noteNode.textContent = 'The timer is running and will stay synced with the floating desktop timer when the app is minimized.';
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
                if (!result.ok) {
                    return;
                }

                currentBalance = Number(result.balance);
                var balanceText = 'PHP ' + currentBalance.toFixed(2);
                var balanceElements = document.querySelectorAll('[data-balance-display]');
                balanceElements.forEach(function (element) {
                    if (element) {
                        element.textContent = balanceText;
                        element.classList.toggle('balance-ok', currentBalance >= 1);
                        element.classList.toggle('balance-low', currentBalance < 1);
                    }
                });

                if (dashboardTimer && typeof dashboardTimer.setAccessState === 'function') {
                    dashboardTimer.setAccessState(Number(result.balance) >= 1);
                }

                if (currentBalance >= 1) {
                    dashboardTimer.ensureStartedAt();
                    withPywebviewApi(function (api) {
                        if (api.start_timer) {
                            api.start_timer(dashboardTimer.ensureStartedAt());
                        }
                    });
                } else if (window.pywebview && window.pywebview.api && window.pywebview.api.stop_timer) {
                    dashboardTimer.clear();
                    window.pywebview.api.stop_timer();
                }

                // Update minimize button state
                updateMinimizeButtonState();

                // Low balance warning (max 1 warning per 30 seconds)
                if (currentBalance > 0 && currentBalance < lowBalanceThreshold) {
                    var now = Date.now();
                    if (now - lastLowBalanceWarningTime > 30000 || lastLowBalance !== currentBalance) {
                        var minimizeBtn = document.getElementById('minimize-btn-bookings');
                        if (minimizeBtn) {
                            minimizeBtn.title = 'Low balance: ' + balanceText;
                        }
                        lastLowBalanceWarningTime = now;
                        lastLowBalance = currentBalance;
                    }
                }
            })
            .catch(function (error) {
                console.warn('Session status refresh failed:', error);
            });
        }

        setInterval(refreshSessionStatus, 3000);
        setTimeout(refreshSessionStatus, 1000);

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

        function handleMinimizeClick(event) {
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
            if (window.pywebview && window.pywebview.api && window.pywebview.api.minimize) {
                window.pywebview.api.minimize();
                return;
            }
            window.blur();
        }
        
        function updateMinimizeButtonState() {
            var minimizeBtn = document.getElementById('minimize-btn-bookings');
            
            if (minimizeBtn) {
                if (currentBalance <= 0) {
                    minimizeBtn.disabled = false;
                    minimizeBtn.classList.add('btn-disabled');
                    minimizeBtn.setAttribute('aria-disabled', 'true');
                    minimizeBtn.title = 'No balance available';
                } else {
                    minimizeBtn.disabled = false;
                    minimizeBtn.classList.remove('btn-disabled');
                    minimizeBtn.setAttribute('aria-disabled', 'false');
                    if (currentBalance < lowBalanceThreshold) {
                        minimizeBtn.title = 'Low balance: PHP ' + currentBalance.toFixed(2);
                    } else {
                        minimizeBtn.title = '';
                    }
                }
            }
        }
        
        updateMinimizeButtonState();

        function setTopup(amount) {
            var field = document.getElementById('topupAmount');
            if (field) {
                field.value = amount;
            }
        }

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
    

document.querySelectorAll('[data-action="minimize"]').forEach(function (el) {
    el.addEventListener('click', handleMinimizeClick);
});
document.querySelectorAll('[data-action="clear-timer-state"]').forEach(function (el) {
    el.addEventListener('click', clearDashboardTimerState);
});
document.querySelectorAll('[data-action="set-topup"]').forEach(function (btn) {
    btn.addEventListener('click', function () { setTopup(Number(btn.dataset.amount)); });
});
