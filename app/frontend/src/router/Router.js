/**
 * Client-Side SPA Hash Router Component
 */

export class Router {
  constructor(routes = {}, topbar = null) {
    this.routes = routes;
    this.topbar = topbar;
    this.currentRoute = null;
    this.init();
  }

  init() {
    window.__acucalyxRouterActive = true;
    window.addEventListener('hashchange', () => this.handleHashChange());
    // Global navigation helper
    window.portalNavigateTo = (route) => this.navigate(route);
  }

  navigate(routeName) {
    window.location.hash = `#/${routeName}`;
  }

  getRouteFromHash() {
    const raw = window.location.hash.replace('#/', '').replace('#', '');
    return this.routes[raw] ? raw : 'dashboard';
  }

  handleHashChange() {
    const routeName = this.getRouteFromHash();
    document.body.setAttribute('data-active-route', routeName);
    document.documentElement.setAttribute('data-active-route', routeName);
    if (this.currentRoute === routeName) return;
    this.currentRoute = routeName;

    // 1. Update navigation active state in sidebar
    document.querySelectorAll('.sidebar-nav .nav-item').forEach((item) => {
      const target = item.getAttribute('data-view');
      if (target === routeName) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // 2. Switch page view visibility
    document.querySelectorAll('.page-view').forEach((view) => {
      view.classList.remove('active');
    });
    const targetEl = document.getElementById(`view-${routeName}`);
    if (targetEl) {
      targetEl.classList.add('active');
    }

    // 3. Update breadcrumbs
    const labels = {
      dashboard: 'Surgical Control Center',
      cases: 'Private Patient Directory',
      cockpit: '3D Rehearsal Cockpit',
      workbench: 'Multi-Tract Planning Workbench',
      learning: 'Privacy-Preserving Federated Learning',
      usability: 'Human Factors & Cognitive Workload (IEC 62366)',
      validation: 'M15-V CT Urography Validation Gate',
      settings: 'Physician Profile & Privacy Controls',
      login: 'Clinical Physician Access'
    };
    if (this.topbar && labels[routeName]) {
      this.topbar.setBreadcrumb(labels[routeName]);
    }

    // 4. Trigger view mount lifecycle
    const activeView = this.routes[routeName];
    if (activeView && typeof activeView.mount === 'function') {
      activeView.mount();
    }
  }

  start() {
    this.handleHashChange();
  }
}
