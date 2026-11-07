        (function() {
            var paymongoPublicKey = JSON.parse(document.body.dataset.paymongoPublicKey);
            var paymongoReady = document.body.dataset.paymongoReady === 'true';
            var radioButtons = Array.prototype.slice.call(document.querySelectorAll('input[name="payment_method"]'));
            var selectedMethodInput = document.getElementById('selectedMethod');
            var paymentMethodIdInput = document.getElementById('paymentMethodId');
            var paymentReferenceInput = document.getElementById('paymentReference');
            var paymentError = document.getElementById('paymentError');
            var submitButton = document.getElementById('submitButton');
            var checkoutForm = document.getElementById('checkoutForm');

            var fieldGroups = {
                gcash: document.getElementById('gcashFields'),
                card: document.getElementById('cardFields'),
                cash: document.getElementById('cashFields')
            };

            var labels = {
                gcash: 'Next: GCash',
                card: 'Next: Card',
                cash: 'Save Cash Request'
            };

            function showError(message) {
                paymentError.textContent = message;
                paymentError.classList.add('active');
            }

            function clearError() {
                paymentError.textContent = '';
                paymentError.classList.remove('active');
            }

            function normalizeCardYear(value) {
                var raw = String(value || '').trim();
                if (raw.length === 2) {
                    return '20' + raw;
                }
                return raw;
            }

            function setActiveMethod(method) {
                selectedMethodInput.value = method;
                paymentMethodIdInput.value = '';
                paymentReferenceInput.value = '';
                clearError();

                Object.keys(fieldGroups).forEach(function(key) {
                    fieldGroups[key].classList.toggle('active', key === method);
                });

                submitButton.textContent = labels[method] || 'Continue';
                submitButton.disabled = (!paymongoReady && method !== 'cash');
            }

            async function createPayMongoPaymentMethod(method) {
                var payload;

                if (method === 'gcash') {
                    var gcashName = document.getElementById('gcashName').value.trim();
                    var gcashEmail = document.getElementById('gcashEmail').value.trim();
                    var gcashPhone = document.getElementById('gcashPhone').value.trim();

                    if (!gcashName || !gcashEmail || !gcashPhone) {
                        throw new Error('Complete the GCash name, email, and mobile number fields.');
                    }

                    payload = {
                        data: {
                            attributes: {
                                type: 'gcash',
                                billing: {
                                    name: gcashName,
                                    email: gcashEmail,
                                    phone: gcashPhone
                                }
                            }
                        }
                    };
                } else {
                    var cardName = document.getElementById('cardName').value.trim();
                    var cardEmail = document.getElementById('cardEmail').value.trim();
                    var cardNumber = document.getElementById('cardNumber').value.replace(/\s+/g, '');
                    var cardExpMonth = document.getElementById('cardExpMonth').value.trim();
                    var cardExpYear = normalizeCardYear(document.getElementById('cardExpYear').value);
                    var cardCvc = document.getElementById('cardCvc').value.trim();

                    if (!cardName || !cardEmail || !cardNumber || !cardExpMonth || !cardExpYear || !cardCvc) {
                        throw new Error('Complete all card fields before continuing.');
                    }

                    payload = {
                        data: {
                            attributes: {
                                type: 'card',
                                details: {
                                    card_number: cardNumber,
                                    exp_month: parseInt(cardExpMonth, 10),
                                    exp_year: parseInt(cardExpYear, 10),
                                    cvc: cardCvc
                                },
                                billing: {
                                    name: cardName,
                                    email: cardEmail
                                }
                            }
                        }
                    };
                }

                var response = await fetch('https://api.paymongo.com/v1/payment_methods', {
                    method: 'POST',
                    headers: {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'Authorization': 'Basic ' + btoa(paymongoPublicKey + ':')
                    },
                    body: JSON.stringify(payload)
                });

                var body = await response.json().catch(function() { return {}; });
                if (!response.ok) {
                    var detail = 'Unable to create the payment method.';
                    if (body && body.errors && body.errors.length && body.errors[0].detail) {
                        detail = body.errors[0].detail;
                    }
                    throw new Error(detail);
                }

                if (!body || !body.data || !body.data.id) {
                    throw new Error('PayMongo did not return a payment method id.');
                }

                return body.data.id;
            }

            radioButtons.forEach(function(radio) {
                radio.addEventListener('change', function() {
                    setActiveMethod(radio.value);
                });
            });

            checkoutForm.addEventListener('submit', async function(event) {
                var method = selectedMethodInput.value;
                clearError();

                if (method === 'cash') {
                    return;
                }

                event.preventDefault();

                if (!paymongoReady) {
                    showError('Online payment is not ready. Please choose Cash or ask staff for help.');
                    return;
                }

                submitButton.disabled = true;
                submitButton.textContent = 'Connecting...';

                try {
                    var paymentMethodId = await createPayMongoPaymentMethod(method);
                    paymentMethodIdInput.value = paymentMethodId;
                    paymentReferenceInput.value = paymentMethodId;
                    checkoutForm.submit();
                } catch (error) {
                    showError(error.message || 'Payment setup failed.');
                    submitButton.disabled = false;
                    submitButton.textContent = labels[method] || 'Continue';
                }
            });

            setActiveMethod('gcash');
        })();
    
