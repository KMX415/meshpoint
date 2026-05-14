/**
 * Sub-tabs inside System view (shell from meshpoint-compliant reference).
 */
export function initSystemShell() {
  const root = document.getElementById("tab-system");
  if (!root) return;

  root.querySelectorAll(".sys-nav__btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.sys;
      if (!name) return;
      root.querySelectorAll(".sys-nav__btn").forEach((b) => {
        b.classList.toggle("sys-nav__btn--active", b === btn);
      });
      root.querySelectorAll(".sys-panel").forEach((p) => {
        p.classList.toggle("sys-panel--active", p.id === `sys-${name}`);
      });
    });
  });
}
