/**
 * AcuCalyx Advanced Layout & Resizable Splitter Manager
 * 
 * Provides:
 *  1. Smooth pointer-captured drag-to-resize splitters across all dividing lines:
 *     - Navigation Sidebar ⟷ Main Clinical Workspace
 *     - 3D Rehearsal Cockpit: Left Parameters Panel ⟷ Center 3D Viewport
 *     - 3D Rehearsal Cockpit: Center 3D Viewport ⟷ Right Pareto Decision Panel
 *     - 3D Viewport ⟷ 2D MPR CT Slice Drawer (Horizontal)
 *  2. Full On-Click Open & Close triggers across all sidebars:
 *     - Clicking on the sidebar header / title bar directly toggles open/close
 *     - Clicking on the dividing line / splitter toggle pill directly toggles open/close
 *     - Clicking on the sidebar collapse buttons (⮜ / ⮞)
 *     - Clicking on floating expand tabs when sidebars are collapsed
 *     - Clicking on topbar navigation toggle button
 *  3. Fullscreen 3D Rehearsal Mode (toggle both sidebars simultaneously)
 *  4. High-frequency 60fps Three.js WebGL canvas synchronization during resizing
 *  5. LocalStorage state persistence for user layout preferences and dimensions
 *  6. Double-click on any splitter to reset to canonical clinical default
 *  7. Ergonomic keyboard shortcuts (Ctrl+[, Ctrl+], Ctrl+B, Alt+F)
 */

(function () {
  'use strict';

  // Canonical layout defaults & constraints (px)
  const PANE_CONFIGS = {
    'clinical-sidebar': {
      key: 'clinical-sidebar',
      elementId: 'clinical-sidebar',
      splitterId: 'splitter-app-sidebar',
      collapseBtnId: 'btn-collapse-clinical-sidebar',
      direction: 'left',
      defaultDim: 250,
      minDim: 180,
      maxDim: 450,
      storageKey: 'acucalyx_layout_clinical_sidebar',
      isVertical: true
    },
    'sidebar-left': {
      key: 'sidebar-left',
      elementId: 'sidebar-left',
      splitterId: 'splitter-cockpit-left',
      expandBtnId: 'btn-expand-sidebar-left',
      collapseBtnId: 'btn-collapse-sidebar-left',
      direction: 'left',
      defaultDim: 285,
      minDim: 200,
      maxDim: 520,
      storageKey: 'acucalyx_layout_sidebar_left',
      isVertical: true
    },
    'sidebar-right': {
      key: 'sidebar-right',
      elementId: 'sidebar-right',
      splitterId: 'splitter-cockpit-right',
      expandBtnId: 'btn-expand-sidebar-right',
      collapseBtnId: 'btn-collapse-sidebar-right',
      direction: 'right',
      defaultDim: 325,
      minDim: 220,
      maxDim: 580,
      storageKey: 'acucalyx_layout_sidebar_right',
      isVertical: true
    },
    'mpr-viewport': {
      key: 'mpr-viewport',
      elementId: 'mpr-viewport',
      splitterId: 'splitter-cockpit-mpr',
      direction: 'bottom',
      defaultDim: 260,
      minDim: 160,
      maxDim: 600,
      storageKey: 'acucalyx_layout_mpr_viewport',
      isVertical: false
    }
  };

  class LayoutManager {
    constructor() {
      this.activeDrag = null;
      this.rafId = null;
      this.init();
    }

    init() {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => this.setup());
      } else {
        this.setup();
      }
    }

    setup() {
      this.initSplitters();
      this.initCollapsibleButtons();
      this.initKeyboardShortcuts();
      this.restoreSavedLayout();
    }

    /**
     * Wires pointer capture, drag-to-resize, and on-click open/close on splitters
     */
    initSplitters() {
      Object.keys(PANE_CONFIGS).forEach(key => {
        const cfg = PANE_CONFIGS[key];
        const splitter = document.getElementById(cfg.splitterId);
        const pane = document.getElementById(cfg.elementId) || document.querySelector('.' + cfg.elementId);

        if (!splitter || !pane) return;

        splitter.addEventListener('pointerdown', (e) => this.onPointerDown(e, cfg, pane, splitter));
        splitter.addEventListener('dblclick', (e) => {
          e.stopPropagation();
          this.resetPane(cfg, pane);
        });

        // Wire dedicated center toggle pill if present
        const pill = splitter.querySelector('.splitter-toggle-pill');
        if (pill) {
          pill.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleSidebar(cfg.key);
          });
        }
      });

      // Synchronize horizontal MPR splitter visibility with MPR toggle
      const origToggleMPR = window.toggleMPRView;
      window.toggleMPRView = () => {
        if (typeof origToggleMPR === 'function') origToggleMPR();
        const mpr = document.getElementById('mpr-viewport');
        const mprSplitter = document.getElementById('splitter-cockpit-mpr');
        if (mpr && mprSplitter) {
          const isVisible = (mpr.style.display !== 'none' && mpr.offsetParent !== null);
          mprSplitter.style.display = isVisible ? 'flex' : 'none';
        }
      };
    }

    onPointerDown(e, cfg, pane, splitter) {
      // If pane is currently collapsed, clicking the splitter immediately opens it!
      if (pane.classList.contains('collapsed')) {
        e.preventDefault();
        this.toggleSidebar(cfg.key, true);
        return;
      }

      e.preventDefault();
      e.stopPropagation();

      splitter.setPointerCapture(e.pointerId);

      const computed = window.getComputedStyle(pane);
      const startDim = cfg.isVertical ? parseFloat(computed.width) : parseFloat(computed.height);

      this.activeDrag = {
        pointerId: e.pointerId,
        cfg,
        pane,
        splitter,
        startX: e.clientX,
        startY: e.clientY,
        startDim,
        hasMoved: false
      };

      splitter.classList.add('active-resizing');
      document.body.classList.add(cfg.isVertical ? 'is-resizing-vertical' : 'is-resizing-horizontal');

      const onPointerMove = (evt) => this.onPointerMove(evt);
      const onPointerUp = (evt) => {
        if (evt.pointerId !== e.pointerId) return;
        splitter.removeEventListener('pointermove', onPointerMove);
        splitter.removeEventListener('pointerup', onPointerUp);
        splitter.removeEventListener('pointercancel', onPointerUp);
        this.onPointerUp(evt);
      };

      splitter.addEventListener('pointermove', onPointerMove);
      splitter.addEventListener('pointerup', onPointerUp);
      splitter.addEventListener('pointercancel', onPointerUp);
    }

    onPointerMove(e) {
      if (!this.activeDrag) return;

      const { cfg, pane, startX, startY, startDim } = this.activeDrag;

      // Detect if user intended to drag or just clicked
      if (Math.abs(e.clientX - startX) > 4 || Math.abs(e.clientY - startY) > 4) {
        this.activeDrag.hasMoved = true;
      }

      if (!this.activeDrag.hasMoved) return;

      let newDim = startDim;

      if (cfg.direction === 'left') {
        const deltaX = e.clientX - startX;
        newDim = startDim + deltaX;
      } else if (cfg.direction === 'right') {
        const deltaX = startX - e.clientX;
        newDim = startDim + deltaX;
      } else if (cfg.direction === 'bottom') {
        const deltaY = startY - e.clientY;
        newDim = startDim + deltaY;
      }

      // Dynamic max constraints based on current screen size
      let maxAllowed = cfg.maxDim;
      if (cfg.isVertical) {
        maxAllowed = Math.min(cfg.maxDim, window.innerWidth * 0.45);
      } else {
        const viewportCenter = document.querySelector('.viewport-center');
        const vh = viewportCenter ? viewportCenter.clientHeight : window.innerHeight;
        maxAllowed = Math.min(cfg.maxDim, vh * 0.65);
      }

      newDim = Math.max(cfg.minDim, Math.min(maxAllowed, newDim));

      if (cfg.isVertical) {
        pane.style.width = `${newDim}px`;
        pane.style.minWidth = `${newDim}px`;
        pane.style.maxWidth = `${newDim}px`;
      } else {
        pane.style.height = `${newDim}px`;
        pane.style.maxHeight = `${newDim}px`;
      }

      // Throttled high-framerate Three.js canvas refresh
      if (!this.rafId) {
        this.rafId = requestAnimationFrame(() => {
          this.rafId = null;
          this.triggerViewerResize();
        });
      }
    }

    onPointerUp(e) {
      if (!this.activeDrag) return;

      const { cfg, pane, splitter, pointerId, hasMoved } = this.activeDrag;
      try {
        splitter.releasePointerCapture(pointerId);
      } catch (_) {}

      splitter.classList.remove('active-resizing');
      document.body.classList.remove('is-resizing-vertical', 'is-resizing-horizontal');

      // If user clicked without dragging, toggle open/close!
      if (!hasMoved) {
        this.activeDrag = null;
        this.toggleSidebar(cfg.key);
        return;
      }

      // Persist size preference
      const computed = window.getComputedStyle(pane);
      const finalDim = cfg.isVertical ? parseFloat(computed.width) : parseFloat(computed.height);
      if (finalDim && !isNaN(finalDim)) {
        try {
          localStorage.setItem(cfg.storageKey + '_dim', finalDim.toString());
        } catch (_) {}
      }

      this.activeDrag = null;
      this.triggerViewerResize();
      window.dispatchEvent(new Event('resize'));
    }

    /**
     * Resets a pane to its clinical default dimension
     */
    resetPane(cfg, pane) {
      if (!pane) return;
      if (cfg.isVertical) {
        pane.style.width = `${cfg.defaultDim}px`;
        pane.style.minWidth = `${cfg.defaultDim}px`;
        pane.style.maxWidth = `${cfg.defaultDim}px`;
      } else {
        pane.style.height = `${cfg.defaultDim}px`;
        pane.style.maxHeight = `${cfg.defaultDim}px`;
      }

      try {
        localStorage.removeItem(cfg.storageKey + '_dim');
      } catch (_) {}

      this.triggerViewerResize();
      window.dispatchEvent(new Event('resize'));
    }

    /**
     * Sets up click triggers on sidebars, headers, and collapse buttons
     */
    initCollapsibleButtons() {
      // 1. Navigation Sidebar: Toggle button in topbar + collapse button in sidebar header + brand click
      const btnToggleNav = document.getElementById('btn-toggle-clinical-sidebar');
      if (btnToggleNav) {
        btnToggleNav.addEventListener('click', () => this.toggleSidebar('clinical-sidebar'));
      }

      const btnCollapseNav = document.getElementById('btn-collapse-clinical-sidebar');
      if (btnCollapseNav) {
        btnCollapseNav.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleSidebar('clinical-sidebar', false);
        });
      }

      const sidebarBrand = document.querySelector('.sidebar-brand');
      if (sidebarBrand) {
        sidebarBrand.style.cursor = 'pointer';
        sidebarBrand.title = 'Click to toggle Navigation Sidebar (Ctrl+B)';
        sidebarBrand.addEventListener('click', (e) => {
          // If clicked directly on the brand title or icon, toggle
          if (e.target.closest('#btn-collapse-clinical-sidebar')) return;
          this.toggleSidebar('clinical-sidebar');
        });
      }

      // 2. Cockpit Left Sidebar: button + full header bar click
      const btnCollapseLeft = document.getElementById('btn-collapse-sidebar-left');
      const btnExpandLeft = document.getElementById('btn-expand-sidebar-left');
      const leftHeader = document.querySelector('.sidebar-left .sidebar-top-controls');

      if (btnCollapseLeft) {
        btnCollapseLeft.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleSidebar('sidebar-left', false);
        });
      }
      if (btnExpandLeft) {
        btnExpandLeft.addEventListener('click', () => this.toggleSidebar('sidebar-left', true));
      }
      if (leftHeader) {
        leftHeader.title = 'Click to collapse / expand (Ctrl+[)';
        leftHeader.addEventListener('click', (e) => {
          if (e.target.closest('#btn-collapse-sidebar-left')) return;
          this.toggleSidebar('sidebar-left');
        });
      }

      // 3. Cockpit Right Sidebar: button + full header bar click
      const btnCollapseRight = document.getElementById('btn-collapse-sidebar-right');
      const btnExpandRight = document.getElementById('btn-expand-sidebar-right');
      const rightHeader = document.querySelector('.sidebar-right .sidebar-top-controls');

      if (btnCollapseRight) {
        btnCollapseRight.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleSidebar('sidebar-right', false);
        });
      }
      if (btnExpandRight) {
        btnExpandRight.addEventListener('click', () => this.toggleSidebar('sidebar-right', true));
      }
      if (rightHeader) {
        rightHeader.title = 'Click to collapse / expand (Ctrl+])';
        rightHeader.addEventListener('click', (e) => {
          if (e.target.closest('#btn-collapse-sidebar-right')) return;
          this.toggleSidebar('sidebar-right');
        });
      }

      // 4. Fullscreen 3D (Toggle both sidebars)
      const btnBoth = document.getElementById('btn-toggle-both-sidebars');
      if (btnBoth) {
        btnBoth.addEventListener('click', () => this.toggleBothSidebars());
      }
    }

    /**
     * Toggles a sidebar open or closed with smooth transition
     * @param {string} paneKey 
     * @param {boolean|undefined} forceState (true = open, false = close)
     */
    toggleSidebar(paneKey, forceState) {
      const cfg = PANE_CONFIGS[paneKey];
      if (!cfg) return;

      const pane = document.getElementById(cfg.elementId) || document.querySelector('.' + cfg.elementId);
      const splitter = document.getElementById(cfg.splitterId);
      const expandBtn = document.getElementById(cfg.expandBtnId);

      if (!pane) return;

      const isCurrentlyCollapsed = pane.classList.contains('collapsed');
      const shouldOpen = (forceState !== undefined) ? forceState : isCurrentlyCollapsed;

      if (shouldOpen) {
        // Open
        pane.classList.remove('collapsed');
        if (expandBtn) expandBtn.style.display = 'none';

        // Restore saved width or default
        let savedDim = cfg.defaultDim;
        try {
          const stored = localStorage.getItem(cfg.storageKey + '_dim');
          if (stored) savedDim = parseFloat(stored);
        } catch (_) {}

        if (cfg.isVertical) {
          pane.style.width = `${savedDim}px`;
          pane.style.minWidth = `${savedDim}px`;
          pane.style.maxWidth = `${savedDim}px`;
        }

        try {
          localStorage.setItem(cfg.storageKey + '_collapsed', 'false');
        } catch (_) {}
      } else {
        // Close / Collapse
        pane.classList.add('collapsed');
        if (expandBtn) expandBtn.style.display = 'flex';

        try {
          localStorage.setItem(cfg.storageKey + '_collapsed', 'true');
        } catch (_) {}
      }

      // Update chevron in splitter toggle pill
      this.updateSplitterPillIcon(cfg, !shouldOpen);

      this.updateFullscreen3DButtonState();

      // Ensure Three.js canvas refits perfectly
      setTimeout(() => {
        this.triggerViewerResize();
        window.dispatchEvent(new Event('resize'));
      }, 240);
    }

    /**
     * Updates the chevron icon on the splitter toggle pill based on collapsed state
     */
    updateSplitterPillIcon(cfg, isCollapsed) {
      const splitter = document.getElementById(cfg.splitterId);
      if (!splitter) return;
      const pill = splitter.querySelector('.splitter-toggle-pill svg');
      if (!pill) return;

      if (cfg.direction === 'left') {
        // Left sidebar: when open points left (to close), when closed points right (to open)
        pill.innerHTML = isCollapsed
          ? '<path d="M2 2L6 6L2 10" stroke="currentColor" stroke-width="2"/>'
          : '<path d="M6 2L2 6L6 10" stroke="currentColor" stroke-width="2"/>';
      } else if (cfg.direction === 'right') {
        // Right sidebar: when open points right (to close), when closed points left (to open)
        pill.innerHTML = isCollapsed
          ? '<path d="M6 2L2 6L6 10" stroke="currentColor" stroke-width="2"/>'
          : '<path d="M2 2L6 6L2 10" stroke="currentColor" stroke-width="2"/>';
      }
    }

    /**
     * Toggles both cockpit sidebars (left & right) for maximum 3D stage area
     */
    toggleBothSidebars() {
      const leftPane = document.querySelector('.sidebar-left');
      const rightPane = document.querySelector('.sidebar-right');

      const isLeftOpen = leftPane && !leftPane.classList.contains('collapsed');
      const isRightOpen = rightPane && !rightPane.classList.contains('collapsed');

      if (isLeftOpen || isRightOpen) {
        // At least one is open -> collapse both
        this.toggleSidebar('sidebar-left', false);
        this.toggleSidebar('sidebar-right', false);
      } else {
        // Both are collapsed -> restore both
        this.toggleSidebar('sidebar-left', true);
        this.toggleSidebar('sidebar-right', true);
      }
    }

    updateFullscreen3DButtonState() {
      const leftPane = document.querySelector('.sidebar-left');
      const rightPane = document.querySelector('.sidebar-right');
      const btnBoth = document.getElementById('btn-toggle-both-sidebars');
      if (!btnBoth) return;

      const bothCollapsed = (leftPane?.classList.contains('collapsed')) && (rightPane?.classList.contains('collapsed'));
      if (bothCollapsed) {
        btnBoth.innerHTML = '⮌ Restore Panels';
        btnBoth.style.color = 'var(--accent-teal)';
        btnBoth.style.borderColor = 'rgba(4, 120, 87, 0.5)';
      } else {
        btnBoth.innerHTML = '⛶ Fullscreen 3D';
        btnBoth.style.color = 'var(--accent-cyan)';
        btnBoth.style.borderColor = 'rgba(2, 132, 199, 0.4)';
      }
    }

    /**
     * Keyboard navigation shortcuts
     */
    initKeyboardShortcuts() {
      window.addEventListener('keydown', (e) => {
        // Skip shortcuts when typing in inputs / textareas
        const tag = e.target.tagName?.toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

        // Ctrl+[ or Alt+[: Toggle left sidebar
        if ((e.ctrlKey || e.metaKey || e.altKey) && (e.key === '[' || e.code === 'BracketLeft')) {
          e.preventDefault();
          this.toggleSidebar('sidebar-left');
        }

        // Ctrl+] or Alt+]: Toggle right sidebar
        if ((e.ctrlKey || e.metaKey || e.altKey) && (e.key === ']' || e.code === 'BracketRight')) {
          e.preventDefault();
          this.toggleSidebar('sidebar-right');
        }

        // Ctrl+B: Toggle navigation sidebar
        if ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B')) {
          e.preventDefault();
          this.toggleSidebar('clinical-sidebar');
        }

        // Alt+F: Toggle Fullscreen 3D Stage
        if (e.altKey && (e.key === 'f' || e.key === 'F')) {
          e.preventDefault();
          this.toggleBothSidebars();
        }
      });
    }

    /**
     * Restores saved widths/heights and collapsed states on initialization
     */
    restoreSavedLayout() {
      Object.keys(PANE_CONFIGS).forEach(key => {
        const cfg = PANE_CONFIGS[key];
        const pane = document.getElementById(cfg.elementId) || document.querySelector('.' + cfg.elementId);
        const splitter = document.getElementById(cfg.splitterId);
        const expandBtn = document.getElementById(cfg.expandBtnId);

        if (!pane) return;

        try {
          // 1. Restore dimensions
          const storedDim = localStorage.getItem(cfg.storageKey + '_dim');
          if (storedDim) {
            const val = parseFloat(storedDim);
            if (!isNaN(val) && val >= cfg.minDim && val <= cfg.maxDim) {
              if (cfg.isVertical) {
                pane.style.width = `${val}px`;
                pane.style.minWidth = `${val}px`;
                pane.style.maxWidth = `${val}px`;
              } else {
                pane.style.height = `${val}px`;
                pane.style.maxHeight = `${val}px`;
              }
            }
          }

          // 2. Restore collapsed state
          const isCollapsed = localStorage.getItem(cfg.storageKey + '_collapsed') === 'true';
          if (isCollapsed) {
            pane.classList.add('collapsed');
            if (expandBtn) expandBtn.style.display = 'flex';
          } else {
            if (expandBtn) expandBtn.style.display = 'none';
          }

          this.updateSplitterPillIcon(cfg, isCollapsed);
        } catch (_) {}
      });

      this.updateFullscreen3DButtonState();

      // Trigger initial resize sync
      setTimeout(() => {
        this.triggerViewerResize();
      }, 100);
    }

    triggerViewerResize() {
      if (window.viewer3d && typeof window.viewer3d.onWindowResize === 'function') {
        window.viewer3d.onWindowResize();
      }
      if (window.__acucalyxApp?.viewport3D && typeof window.__acucalyxApp.viewport3D.onWindowResize === 'function') {
        window.__acucalyxApp.viewport3D.onWindowResize();
      }
    }
  }

  // Instantiate and expose globally
  window.layoutManager = new LayoutManager();
})();
