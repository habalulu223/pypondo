document.querySelectorAll('img[data-hide-on-error]').forEach(function (img) {
    function hide() { img.style.display = 'none'; }
    img.addEventListener('error', hide);
    // The error may have fired before this deferred script ran.
    if (img.complete && img.naturalWidth === 0) hide();
});
