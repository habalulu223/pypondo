document.querySelectorAll('[data-action="print"]').forEach(function (el) {
    el.addEventListener('click', function () { window.print(); });
});
