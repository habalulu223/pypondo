        (function() {
            var rows = Array.prototype.slice.call(document.querySelectorAll('[data-payment-row]'));
            var radios = Array.prototype.slice.call(document.querySelectorAll('input[name="payment_id"]'));
            var confirmBtn = document.getElementById('confirmPaymentBtn');

            function syncSelectedState() {
                rows.forEach(function(row) {
                    var radio = row.querySelector('input[name="payment_id"]');
                    row.classList.toggle('selected', !!(radio && radio.checked));
                });

                if (!confirmBtn) {
                    return;
                }

                var selected = radios.find(function(radio) { return radio.checked; });
                confirmBtn.disabled = !selected || selected.getAttribute('data-paid') === '1' || selected.getAttribute('data-cancelled') === '1';
            }

            rows.forEach(function(row) {
                row.addEventListener('click', function(event) {
                    if (event.target && event.target.tagName === 'INPUT') {
                        syncSelectedState();
                        return;
                    }
                    var radio = row.querySelector('input[name="payment_id"]');
                    if (radio) {
                        radio.checked = true;
                        syncSelectedState();
                    }
                });
            });

            radios.forEach(function(radio) {
                radio.addEventListener('change', syncSelectedState);
            });

            syncSelectedState();
        })();
    
