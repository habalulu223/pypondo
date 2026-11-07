        function wireAdminProfileTabs() {
            var tabs = document.querySelectorAll('[data-admin-tab-target]');
            if (!tabs.length) {
                return;
            }

            tabs.forEach(function (tab) {
                tab.addEventListener('click', function () {
                    tabs.forEach(function (candidate) {
                        var panel = document.getElementById(candidate.dataset.adminTabTarget);
                        var active = candidate === tab;
                        candidate.classList.toggle('active', active);
                        candidate.setAttribute('aria-selected', active ? 'true' : 'false');
                        if (panel) {
                            panel.hidden = !active;
                        }
                    });
                });
            });
        }

        function wireBookingDatePicker() {
            var dateInputs = document.querySelectorAll('input.booking-date-input');
            dateInputs.forEach(function (input) {
                function openNativeCalendar() {
                    if (typeof input.showPicker === 'function') {
                        try { input.showPicker(); } catch (e) {}
                    }
                }
                input.addEventListener('focus', openNativeCalendar);
                input.addEventListener('click', openNativeCalendar);
            });
        }

        function formatLocalDate(date) {
            return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
        }

        function formatLocalTime(date) {
            return String(date.getHours()).padStart(2, '0') + ':' + String(date.getMinutes()).padStart(2, '0');
        }

        function wireBookingLeadTime() {
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

        wireAdminProfileTabs();
        wireBookingDatePicker();
        wireBookingLeadTime();

        // Handle system terminate button
        let terminateSysBtn = document.getElementById('terminate-sys-btn');
        if (terminateSysBtn) {
            terminateSysBtn.addEventListener('click', function() {
                if (confirm('WARNING: This will close the client app!\n\nContinue?')) {
                    if (confirm('Are you ABSOLUTELY SURE? The client app will close!')) {
                        fetch('/admin/terminate-system', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            }
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.ok) {
                                alert(data.message);
                                // Close the app by calling the JavaScript API if available
                                if (typeof window.pywebview !== 'undefined' && window.pywebview.api) {
                                    window.pywebview.api.terminate('PYPONDO_TERMINATE_2026').then(result => {
                                        if (!result) {
                                            console.log('Terminating app...');
                                            window.close();
                                        }
                                    });
                                } else {
                                    // Fallback for non-pywebview mode
                                    window.close();
                                }
                            } else {
                                alert('Error: ' + (data.error || 'Failed to terminate app'));
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            alert('Error: Failed to send terminate command');
                        });
                    }
                }
            });
        }

    
