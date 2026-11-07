document.querySelectorAll('[data-action="back"]').forEach(function (el) {
    el.addEventListener('click', function (event) {
        if (history.length > 1) {
            history.back();
            event.preventDefault();
        }
    });
});
