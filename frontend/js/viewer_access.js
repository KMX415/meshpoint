/* Presentation for trusted observers. Server dependencies enforce authorization. */
window.installViewerAccess = function (identity) {
    window.meshpointReadOnly = identity?.role !== 'admin';
    if (!window.meshpointReadOnly) return;
    document.documentElement.classList.add('viewer-read-only');
    const selector = '[data-section^="configuration/"]';
    const apply = () => {
        document.querySelectorAll(selector).forEach(section => {
            section.querySelectorAll('input, select, textarea, button').forEach(control => {
                if (!control.disabled) control.disabled = true;
                if (control.title !== 'Read-only: administrator access required') {
                    control.title = 'Read-only: administrator access required';
                }
            });
        });
    };
    // Configuration cards mount lazily and refresh their disabled state.
    const observer = new MutationObserver(apply);
    document.querySelectorAll(selector).forEach(section => observer.observe(section, {
        childList:true, subtree:true, attributes:true, attributeFilter:['disabled'],
    }));
    apply();
    const notice = document.createElement('p');
    notice.className = 'viewer-access-notice';
    notice.textContent = 'Viewer access: read-only. Changes and sending require an administrator.';
    const main = document.querySelector('main');
    main?.prepend(notice);
};
