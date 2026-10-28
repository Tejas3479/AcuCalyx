    // Automatic Authorization Header Interceptor for HIPAA/FDA Compliance (F-12)
    (function() {
      const _origFetch = window.fetch;
      window.fetch = function(input, init = {}) {
        try {
          const url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
          if (url.startsWith('/api/')) {
            init = init || {};
            const headers = new Headers(init.headers || {});
            if (!headers.has('Authorization')) {
              const stored = localStorage.getItem('acucalyx_doctor_auth');
              if (stored) {
                const parsed = JSON.parse(stored);
                if (parsed && parsed.token) {
                  headers.set('Authorization', 'Bearer ' + parsed.token);
                }
              }
            }
            init.headers = headers;
          }
        } catch(e) {}
        return _origFetch.call(this, input, init);
      };
    })();

    // Global non-blocking Toast notification system (FIX-5)
    window.showToast = window.showToast || function(message, type = 'info', durationMs = 3500) {
      const toast = document.createElement('div');
      toast.className = `clinical-toast toast-${type}`;
      toast.textContent = message;
      document.body.appendChild(toast);
      requestAnimationFrame(() => toast.classList.add('visible'));
      setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
      }, durationMs);
    };

    function alert(msg) {
      const isError = /error|failed|rejection|violation|invalid|required/i.test(msg);
      const isSuccess = /success|passed|saved|completed|unlocked/i.test(msg);
      const isWarning = /warning|caution|stale|interlock/i.test(msg);
      const type = isError ? 'error' : (isSuccess ? 'success' : (isWarning ? 'warning' : 'info'));
      window.showToast(msg, type, isError ? 4500 : 3500);
    }

    let viewer3d = null;
    let currentSlicePlane = 'coronal';
    let sliceInverted = false;
    let mprViewer = null;
    let currentCaseId = null;
    let currentCandidates = [];
    let selectedCandidateId = null;
    let currentCaseMeta = null;
    let currentVerifiedLaterality = null;

    function applyAppTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      const sel = document.getElementById('theme-select');
      if (sel && sel.value !== theme) sel.value = theme;
      try { localStorage.setItem('acucalyx_theme', theme); } catch(e) {}
      if (window.viewer3d && typeof window.viewer3d.setTheme === 'function') {
        window.viewer3d.setTheme(theme);
      }
    }
    window.applyAppTheme = applyAppTheme;

    document.addEventListener('DOMContentLoaded', async () => {
      // 0. Initialize Theme
      let savedTheme = 'hybrid';
      try { savedTheme = localStorage.getItem('acucalyx_theme') || 'hybrid'; } catch(e) {}
      applyAppTheme(savedTheme);

      // 1. Initialize Viewers (guard against duplicate WebGL instances)
      if (!window.viewer3d) {
        viewer3d = new AcuCalyxViewer3D('three-container');
        window.viewer3d = viewer3d;
      } else {
        viewer3d = window.viewer3d;
      }
      viewer3d.setTheme(savedTheme);

      if (!window.mprViewer) {
        mprViewer = new AcuCalyxMPRViewer('mpr-slice-img', 'mpr-slider', 'mpr-slice-label');
        window.mprViewer = mprViewer;
      } else {
        mprViewer = window.mprViewer;
      }

      // 2. Wire Trajectory Selection from 3D Scene
      window.addEventListener('acucalyx:trajectory-selected', (e) => {
        selectTrajectory(e.detail.candidateId);
      });

      // 3. UI Buttons
      // Note: #btn-new-demo and #btn-run-plan click handlers are centrally managed by Topbar.js to avoid duplicate submissions
      document.getElementById('btn-download-pdf').addEventListener('click', downloadPDF);
      document.getElementById('btn-provenance').addEventListener('click', showProvenance);
      document.getElementById('btn-approve-trajectory').addEventListener('click', approveTrajectory);
      document.getElementById('btn-open-rehearsal').addEventListener('click', openRehearsal);
      document.getElementById('btn-open-ultrasound')?.addEventListener('click', () => {
        openRehearsal();
        switchRehearsalTab('us');
      });
      document.getElementById('btn-open-laterality').addEventListener('click', openLateralityModal);
      document.getElementById('btn-open-position-confirm')?.addEventListener('click', openPositionConfirmModal);
      document.getElementById('btn-open-endoscopy')?.addEventListener('click', openEndoscopyModal);
      document.getElementById('btn-submit-laterality').addEventListener('click', submitLateralityConfirmation);
      document.getElementById('btn-open-verbal-protocol').addEventListener('click', openVerbalProtocolCard);
      document.getElementById('btn-validate-carm-entry').addEventListener('click', validateCarmAngleEntry);
      document.getElementById('btn-open-phantom').addEventListener('click', () => {
        document.getElementById('modal-phantom').style.display = 'flex';
        loadPhantomModalData();
      });
      document.getElementById('rehearsal-slider').addEventListener('input', updateRehearsalAdvancement);
      document.getElementById('rehearsal-contrast-toggle')?.addEventListener('change', loadRehearsalDrrImages);
      document.getElementById('btn-open-fluoroscopy').addEventListener('click', openFluoroscopy);
      document.getElementById('btn-manual-override').addEventListener('click', () => {
        document.getElementById('modal-override').style.display = 'flex';
      });
      document.getElementById('btn-submit-override').addEventListener('click', submitOverride);
      document.getElementById('btn-open-comparison-matrix')?.addEventListener('click', openComparisonMatrix);
      document.getElementById('btn-open-comparison-matrix-sidebar')?.addEventListener('click', openComparisonMatrix);
      document.getElementById('btn-open-summary-card')?.addEventListener('click', openSummaryCard);
      document.getElementById('btn-open-summary-card-sidebar')?.addEventListener('click', openSummaryCard);

      // Layer Toggles
      document.getElementById('layer-kidney').addEventListener('change', (e) => viewer3d.setLayerVisibility('kidney', e.target.checked));
      document.getElementById('opacity-kidney').addEventListener('input', (e) => viewer3d.setLayerOpacity('kidney', parseFloat(e.target.value)));

      document.getElementById('layer-capsule').addEventListener('change', (e) => viewer3d.setLayerVisibility('renal_capsule', e.target.checked));
      document.getElementById('opacity-capsule').addEventListener('input', (e) => viewer3d.setLayerOpacity('renal_capsule', parseFloat(e.target.value)));

      document.getElementById('layer-pyramids').addEventListener('change', (e) => viewer3d.setLayerVisibility('medulla_pyramids', e.target.checked));
      document.getElementById('opacity-pyramids').addEventListener('input', (e) => viewer3d.setLayerOpacity('medulla_pyramids', parseFloat(e.target.value)));

      document.getElementById('layer-collecting').addEventListener('change', (e) => viewer3d.setLayerVisibility('collecting_system', e.target.checked));
      document.getElementById('opacity-collecting').addEventListener('input', (e) => viewer3d.setLayerOpacity('collecting_system', parseFloat(e.target.value)));

      document.getElementById('layer-arteries').addEventListener('change', (e) => viewer3d.setLayerVisibility('renal_arteries', e.target.checked));
      document.getElementById('opacity-arteries').addEventListener('input', (e) => viewer3d.setLayerOpacity('renal_arteries', parseFloat(e.target.value)));

      document.getElementById('layer-veins').addEventListener('change', (e) => viewer3d.setLayerVisibility('renal_veins', e.target.checked));
      document.getElementById('opacity-veins').addEventListener('input', (e) => viewer3d.setLayerOpacity('renal_veins', parseFloat(e.target.value)));

      document.getElementById('layer-nerves').addEventListener('change', (e) => viewer3d.setLayerVisibility('renal_nerves', e.target.checked));
      document.getElementById('opacity-nerves').addEventListener('input', (e) => viewer3d.setLayerOpacity('renal_nerves', parseFloat(e.target.value)));

      document.getElementById('layer-nephrons').addEventListener('change', (e) => viewer3d.setLayerVisibility('nephrons', e.target.checked));
      document.getElementById('opacity-nephrons').addEventListener('input', (e) => viewer3d.setLayerOpacity('nephrons', parseFloat(e.target.value)));

      document.getElementById('layer-stones').addEventListener('change', (e) => viewer3d.setLayerVisibility('stones', e.target.checked));
      document.getElementById('opacity-stones').addEventListener('input', (e) => viewer3d.setLayerOpacity('stones', parseFloat(e.target.value)));

      document.getElementById('layer-colon').addEventListener('change', (e) => viewer3d.setLayerVisibility('colon', e.target.checked));
      document.getElementById('opacity-colon').addEventListener('input', (e) => viewer3d.setLayerOpacity('colon', parseFloat(e.target.value)));

      document.getElementById('layer-ribs').addEventListener('change', (e) => viewer3d.setLayerVisibility('ribs', e.target.checked));
      document.getElementById('opacity-ribs').addEventListener('input', (e) => viewer3d.setLayerOpacity('ribs', parseFloat(e.target.value)));

      // Anatomical Slicing & Virtual Scalpel Resection Controls
      const sliceSlider = document.getElementById('slice-depth-slider');
      const sliceVal = document.getElementById('slice-depth-val');
      const sliceToggle = document.getElementById('slice-enable-toggle');
      const sliceSepSlider = document.getElementById('slice-separation-slider');
      const sliceSepVal = document.getElementById('slice-separation-val');
      const sliceYawSlider = document.getElementById('slice-yaw-slider');
      const sliceYawVal = document.getElementById('slice-yaw-val');
      const slicePitchSlider = document.getElementById('slice-pitch-slider');
      const slicePitchVal = document.getElementById('slice-pitch-val');
      const sliceGizmoToggle = document.getElementById('slice-gizmo-toggle');

      if (sliceSlider) {
        sliceSlider.addEventListener('input', (e) => {
          const val = parseFloat(e.target.value);
          if (sliceVal) sliceVal.textContent = `${val >= 0 ? '+' : ''}${Math.round(val)} mm`;
          if (viewer3d) {
            viewer3d.setSlicingParameters({ offsetMm: val, enabled: sliceToggle ? sliceToggle.checked : true });
          }
        });
      }

      if (sliceToggle) {
        sliceToggle.addEventListener('change', (e) => {
          const isEnabled = e.target.checked;
          if (viewer3d) {
            viewer3d.setSlicingParameters({ enabled: isEnabled });
          }
        });
      }

      if (sliceSepSlider) {
        sliceSepSlider.addEventListener('input', (e) => {
          const val = parseFloat(e.target.value);
          if (sliceSepVal) sliceSepVal.textContent = `${Math.round(val)} mm`;
          if (viewer3d) {
            viewer3d.setSlicingParameters({ separationMm: val, mode: 'bivalve', enabled: true });
          }
        });
      }

      if (sliceYawSlider) {
        sliceYawSlider.addEventListener('input', (e) => {
          const val = parseFloat(e.target.value);
          if (sliceYawVal) sliceYawVal.textContent = `${Math.round(val)}°`;
          if (viewer3d) {
            viewer3d.setSlicingParameters({ angleYaw: val, enabled: true });
          }
        });
      }

      if (slicePitchSlider) {
        slicePitchSlider.addEventListener('input', (e) => {
          const val = parseFloat(e.target.value);
          if (slicePitchVal) slicePitchVal.textContent = `${val >= 0 ? '+' : ''}${Math.round(val)}°`;
          if (viewer3d) {
            viewer3d.setSlicingParameters({ anglePitch: val, enabled: true });
          }
        });
      }

      if (sliceGizmoToggle) {
        sliceGizmoToggle.addEventListener('change', (e) => {
          if (viewer3d) {
            viewer3d.setSlicingParameters({ showGizmo: e.target.checked });
          }
        });
      }

      // Initialize Scalpel Touch / Pencil / Mouse Freehand Overlay
      initScalpelDrawOverlay();

      // Note: #file-upload and #case-select change handlers are centrally managed by Topbar.js to avoid duplicate triggers

      window.__cockpitWorkflowAttached = true;

      // Load initial cases
      await loadCasesList();
    });

    async function loadCasesList() {
      const res = await fetch('/api/cases');
      const cases = await res.json();
      const sel = document.getElementById('case-select');
      sel.innerHTML = '';

      if (cases.length === 0) {
        sel.innerHTML = '<option value="">No cases available (Create Demo)</option>';
        return;
      }

      cases.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.case_id;
        const displayId = c.case_id.length > 18 ? `${c.case_id.substring(0, 14)}…` : c.case_id;
        opt.textContent = `${displayId} [${c.state}]`;
        opt.title = c.case_id;
        sel.appendChild(opt);
      });

      if (!currentCaseId && cases.length > 0) {
        selectCase(cases[0].case_id);
      }
    }

    async function createDemoCase() {
      const btn = document.getElementById('btn-new-demo');
      btn.textContent = '⏳ Creating...';
      try {
        const res = await fetch('/api/cases/demo', { method: 'POST' });
        const data = await res.json();
        await loadCasesList();
        selectCase(data.case_id);
      } catch (err) {
        alert('Demo creation failed: ' + err.message);
      } finally {
        btn.textContent = '+ Synthetic Demo';
      }
    }

    async function selectCase(caseId) {
      currentCaseId = caseId;
      document.getElementById('case-select').value = caseId;

      // Fetch status
      const res = await fetch(`/api/cases/${caseId}/status`);
      const meta = await res.json();
      currentCaseMeta = meta;
      currentVerifiedLaterality = meta.target_side || 'left';

      updateStateBadge(meta.state, meta.is_stale);
      document.getElementById('target-side-label').textContent = `${(meta.target_side || 'left').toUpperCase()} KIDNEY`;

      const poseConfirmed = meta.surgical_position_confirmation && meta.surgical_position_confirmation.is_confirmed;
      const poseVal = meta.surgical_position_confirmation?.operative_position || 'PRONE_STANDARD';
      const poseEl = document.getElementById('info-surgical-pose');
      if (poseEl) {
        poseEl.textContent = poseConfirmed ? `${poseVal} (U2 VERIFIED)` : `${poseVal} (U2 PENDING)`;
        poseEl.style.color = poseConfirmed ? 'var(--accent-teal)' : '#a78bfa';
      }

      mprViewer.setCase(caseId);
      viewer3d.clearScene();

      // If already planned, fetch artifacts; otherwise load full anatomical baseline
      if (meta.state === 'PLAN_GENERATED' || meta.state === 'CLINICIAN_REVIEW' || meta.state === 'FINALIZED') {
        await loadCaseArtifacts(caseId);
      } else {
        await loadAnatomicalMeshesOnly(caseId);
      }
    }

    function updateStateBadge(state, isStale) {
      const badge = document.getElementById('case-state-badge');
      if (isStale) {
        badge.className = 'state-badge state-stale';
        badge.textContent = 'STALE PLAN';
      } else {
        badge.className = `state-badge state-${state.toLowerCase()}`;
        badge.textContent = state;
      }
    }

    async function runPlanning(options = {}) {
      if (!currentCaseId) return;
      const btn = document.getElementById('btn-run-plan');

      // Pre-planning guided wizard: For non-demo cases, ensure U1 and U2 are satisfied first
      if (currentCaseMeta && !currentCaseMeta.is_demo) {
        const latConf = currentCaseMeta.laterality_confirmation;
        if (!latConf || !latConf.is_verified) {
          const latModal = document.getElementById('modal-laterality');
          if (latModal) {
            latModal.style.display = 'flex';
            if (typeof window.showToast === 'function') {
              window.showToast('Laterality Verification (Interlock U1) required before planning.', 'warning', 4000);
            }
            return;
          }
        }
        const posConf = currentCaseMeta.surgical_position_confirmation;
        if (!posConf || !posConf.is_confirmed) {
          const posModal = document.getElementById('modal-position-confirm');
          if (posModal) {
            posModal.style.display = 'flex';
            if (typeof loadPositionConfirmationData === 'function') loadPositionConfirmationData();
            if (typeof window.showToast === 'function') {
              window.showToast('Patient Operative Pose Gate (Interlock U2) required before planning.', 'warning', 4000);
            }
            return;
          }
        }
      }

      const plannedSide = (currentVerifiedLaterality || (currentCaseMeta && currentCaseMeta.target_side) || 'left').toLowerCase();
      btn.textContent = `⏳ Planning (${plannedSide.toUpperCase()})...`;
      btn.disabled = true;

      const allowFallback = options.allow_fallback_segmentation !== undefined
        ? options.allow_fallback_segmentation
        : (document.getElementById('check-fallback-segmentation')?.checked || false);

      try {
        const res = await fetch(`/api/cases/${currentCaseId}/plan`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_side: plannedSide,
            coarse_step_mm: 15.0,
            allow_fallback_segmentation: allowFallback
          })
        });
        if (!res.ok) {
          const err = await res.json();
          // If server failed due to missing neural weights and fallback is available
          if (res.status === 500 && (err.detail || '').includes('TotalSegmentator native execution unavailable')) {
            const consent = confirm(
              "TotalSegmentator Neural Weights Unmounted on Server.\n\n" +
              "Authorize Audited Heuristic Anatomical Fallback (Research & Feasibility Mode) and re-run planning?"
            );
            if (consent) {
              return await runPlanning({ allow_fallback_segmentation: true });
            }
          }
          throw new Error(err.detail || 'Planning failed');
        }
        const data = await res.json();
        updateStateBadge(data.state, data.is_stale);
        await loadCaseArtifacts(currentCaseId);
        if (typeof window.showToast === 'function') {
          window.showToast('Preoperative surgical access planning completed successfully!', 'success', 3500);
        }
      } catch (err) {
        if (typeof window.showToast === 'function') {
          window.showToast('Planning error: ' + err.message, 'error', 4500);
        } else {
          alert('Planning error: ' + err.message);
        }
      } finally {
        btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> <span>Run Planning Pipeline</span>';
        btn.disabled = false;
      }
    }

    async function loadAnatomicalMeshesOnly(caseId) {
      const warnBadge = document.getElementById('synthetic-mesh-warning');
      if (warnBadge) warnBadge.style.display = 'block';
      viewer3d.clearScene();
      await viewer3d.loadMesh(caseId, 'kidney', 'kidney', 0.45);
      await viewer3d.loadMesh(caseId, 'renal_capsule', 'renal_capsule', 0.20);
      await viewer3d.loadMesh(caseId, 'medulla_pyramids', 'medulla_pyramids', 0.85);
      await viewer3d.loadMesh(caseId, 'collecting_system', 'collecting_system', 0.90);
      await viewer3d.loadMesh(caseId, 'renal_arteries', 'renal_arteries', 0.85);
      await viewer3d.loadMesh(caseId, 'renal_veins', 'renal_veins', 0.80);
      await viewer3d.loadMesh(caseId, 'renal_nerves', 'renal_nerves', 0.95);
      await viewer3d.loadMesh(caseId, 'nephron_unit', 'nephrons', 0.85);
      await viewer3d.loadMesh(caseId, 'stones', 'stones', 1.0);
      try { await viewer3d.loadMesh(caseId, 'colon', 'colon', 0.22); } catch(e) {}
      try { await viewer3d.loadMesh(caseId, 'ribs', 'ribs', 0.50); } catch(e) {}

      // Synchronize layer visibility with checkboxes
      const organCheckboxMap = {
        'kidney': 'layer-kidney',
        'renal_capsule': 'layer-capsule',
        'medulla_pyramids': 'layer-pyramids',
        'collecting_system': 'layer-collecting',
        'renal_arteries': 'layer-arteries',
        'renal_veins': 'layer-veins',
        'renal_nerves': 'layer-nerves',
        'nephrons': 'layer-nephrons',
        'stones': 'layer-stones',
        'colon': 'layer-colon',
        'ribs': 'layer-ribs'
      };
      Object.entries(organCheckboxMap).forEach(([organKey, elId]) => {
        const el = document.getElementById(elId);
        if (el) {
          viewer3d.setLayerVisibility(organKey, el.checked);
        }
      });
    }

    async function loadCaseArtifacts(caseId) {
      // 1. Stones
      try {
        const sRes = await fetch(`/api/cases/${caseId}/stones`);
        const stones = await sRes.json();
        if (stones.length > 0) {
          document.getElementById('info-stone-count').textContent = stones.length;
          const totalVol = stones.reduce((acc, s) => acc + s.volume_mm3, 0);
          document.getElementById('info-stone-vol').textContent = `${totalVol.toFixed(1)} mm³`;
          const maxFeret = Math.max(...stones.map(s => s.max_feret_diameter_mm));
          document.getElementById('info-stone-feret').textContent = `${maxFeret.toFixed(1)} mm`;
          document.getElementById('info-stone-hu').textContent = `${Math.round(stones[0].peak_hu)} HU`;
          document.getElementById('info-composition').textContent = stones[0].composition_inference;
        }
      } catch (e) {}

      // 1b. Milestone M11: Descriptive Nephrolithometry
      try {
        const nRes = await fetch(`/api/cases/${caseId}/nephrolithometry`);
        if (nRes.ok) {
          const nData = await nRes.json();
          const guysGrade = nData.guys_stone_score.grade.replace('_', ' ');
          document.getElementById('info-guys-grade').textContent = guysGrade;
          document.getElementById('info-stone-score').textContent = `${nData.stone_nephrolithometry.total_score} / 13 (${nData.stone_nephrolithometry.complexity_tier})`;
        }
      } catch (e) {}

      // 2. Candidates
      try {
        const cRes = await fetch(`/api/cases/${caseId}/candidates`);
        currentCandidates = await cRes.json();
        renderCandidatesList(currentCandidates);
      } catch (e) {}

      // 3. 3D Meshes (Realistic Anatomical Kidney Cross-Section & Highlighted Stone)
      const warnBadge = document.getElementById('synthetic-mesh-warning');
      if (warnBadge) {
        if (currentCaseMeta && (currentCaseMeta.is_demo || currentCaseMeta.segmentation_provenance?.source === 'SYNTHETIC_TEMPLATE' || currentCaseMeta.segmentation_provenance?.model === 'SYNTHETIC_TEMPLATE')) {
          warnBadge.style.display = 'block';
        } else {
          warnBadge.style.display = 'none';
        }
      }
      viewer3d.clearScene();
      await viewer3d.loadMesh(caseId, 'kidney', 'kidney', 0.45);
      await viewer3d.loadMesh(caseId, 'renal_capsule', 'renal_capsule', 0.20);
      await viewer3d.loadMesh(caseId, 'medulla_pyramids', 'medulla_pyramids', 0.85);
      await viewer3d.loadMesh(caseId, 'collecting_system', 'collecting_system', 0.90);
      await viewer3d.loadMesh(caseId, 'renal_arteries', 'renal_arteries', 0.85);
      await viewer3d.loadMesh(caseId, 'renal_veins', 'renal_veins', 0.80);
      await viewer3d.loadMesh(caseId, 'renal_nerves', 'renal_nerves', 0.95);
      await viewer3d.loadMesh(caseId, 'nephron_unit', 'nephrons', 0.85);
      await viewer3d.loadMesh(caseId, 'stones', 'stones', 1.0);
      try { await viewer3d.loadMesh(caseId, 'colon', 'colon', 0.22); } catch(e) {}
      try { await viewer3d.loadMesh(caseId, 'ribs', 'ribs', 0.50); } catch(e) {}

      // Synchronize layer visibility with checkboxes
      const organCheckboxMap = {
        'kidney': 'layer-kidney',
        'renal_capsule': 'layer-capsule',
        'medulla_pyramids': 'layer-pyramids',
        'collecting_system': 'layer-collecting',
        'renal_arteries': 'layer-arteries',
        'renal_veins': 'layer-veins',
        'renal_nerves': 'layer-nerves',
        'nephrons': 'layer-nephrons',
        'stones': 'layer-stones',
        'colon': 'layer-colon',
        'ribs': 'layer-ribs'
      };
      Object.entries(organCheckboxMap).forEach(([organKey, elId]) => {
        const el = document.getElementById(elId);
        if (el) {
          viewer3d.setLayerVisibility(organKey, el.checked);
        }
      });

      // Trajectories
      currentCandidates.forEach((c, idx) => {
        viewer3d.addTrajectory(c, idx === 0);
      });

      if (currentCandidates.length > 0) {
        selectTrajectory(currentCandidates[0].candidate_id);
      }
    }

    // Nephron 3D Inspector Modal Subsystem
    let nephronViewer = null;

    function openNephronMagnifier() {
      const modal = document.getElementById('modal-nephron-magnifier');
      if (!modal) return;
      modal.style.display = 'flex';

      const container = document.getElementById('nephron-canvas-container');
      if (!container) return;

      if (!nephronViewer) {
        nephronViewer = initNephron3DViewer(container, currentCaseId || 'demo-case-001');
      }

      // Responsive redraw on initial layout paint
      requestAnimationFrame(() => {
        if (nephronViewer && nephronViewer.resize) nephronViewer.resize();
      });
      setTimeout(() => {
        if (nephronViewer && nephronViewer.resize) nephronViewer.resize();
      }, 50);
    }

    function closeNephronMagnifier() {
      const modal = document.getElementById('modal-nephron-magnifier');
      if (modal) modal.style.display = 'none';
    }

    window.openNephronMagnifier = openNephronMagnifier;
    window.closeNephronMagnifier = closeNephronMagnifier;

    function initNephron3DViewer(container, caseId) {
      container.innerHTML = '';
      const width = container.clientWidth || 500;
      const height = container.clientHeight || 440;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x060913);

      const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 1000.0);
      camera.position.set(0, 4, 46);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.0));
      renderer.outputEncoding = THREE.sRGBEncoding;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.15;
      container.appendChild(renderer.domElement);

      const controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.05;
      controls.target.set(0, 0, 0);

      // Studio Multi-Angle Lighting
      const ambLight = new THREE.AmbientLight(0xffffff, 0.95);
      scene.add(ambLight);

      const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
      keyLight.position.set(30, 45, 35);
      scene.add(keyLight);

      const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.65);
      fillLight.position.set(-30, 15, -25);
      scene.add(fillLight);

      const rimLight = new THREE.DirectionalLight(0xfbbf24, 0.5);
      rimLight.position.set(0, -35, 15);
      scene.add(rimLight);

      let nephronModel = null;

      function createProceduralNephron() {
        const group = new THREE.Group();

        // 1. Glomerulus (Red capillary tuft)
        const glomGeo = new THREE.SphereGeometry(2.2, 32, 32);
        const glomMat = new THREE.MeshStandardMaterial({
          color: 0xef4444,
          roughness: 0.3,
          metalness: 0.15,
          emissive: 0x7f1d1d,
          emissiveIntensity: 0.35
        });
        const glom = new THREE.Mesh(glomGeo, glomMat);
        glom.position.set(0, 10, 0);
        group.add(glom);

        // 2. Bowman's Capsule (Gold translucent cup)
        const bowmanGeo = new THREE.SphereGeometry(3.0, 32, 16, 0, Math.PI * 2, 0, Math.PI * 0.75);
        const bowmanMat = new THREE.MeshStandardMaterial({
          color: 0xfbbf24,
          roughness: 0.2,
          metalness: 0.1,
          transparent: true,
          opacity: 0.65,
          side: THREE.DoubleSide
        });
        const bowman = new THREE.Mesh(bowmanGeo, bowmanMat);
        bowman.position.set(0, 10, 0);
        group.add(bowman);

        // 3. Arterioles (Afferent & Efferent)
        const affCurve = new THREE.CubicBezierCurve3(
          new THREE.Vector3(-6, 8, -2),
          new THREE.Vector3(-3, 8.5, -1),
          new THREE.Vector3(-2, 9.5, 0),
          new THREE.Vector3(-0.8, 10, 0)
        );
        const affGeo = new THREE.TubeGeometry(affCurve, 20, 0.45, 8, false);
        const artMat = new THREE.MeshStandardMaterial({ color: 0xdc2626, roughness: 0.35 });
        group.add(new THREE.Mesh(affGeo, artMat));

        const effCurve = new THREE.CubicBezierCurve3(
          new THREE.Vector3(-0.8, 11, 0.5),
          new THREE.Vector3(-2, 11.5, 1),
          new THREE.Vector3(-4, 12, 1.5),
          new THREE.Vector3(-6, 12.5, 2)
        );
        const effGeo = new THREE.TubeGeometry(effCurve, 20, 0.38, 8, false);
        group.add(new THREE.Mesh(effGeo, artMat));

        // 4. Proximal Convoluted Tubule (PCT - Amber looping tube)
        const pctCurve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(2.2, 10, 0),
          new THREE.Vector3(4.5, 11, 2),
          new THREE.Vector3(3.5, 12.5, 3),
          new THREE.Vector3(1.5, 12, 2.5),
          new THREE.Vector3(1.0, 9.5, 1.5),
          new THREE.Vector3(2.5, 8.5, 0),
          new THREE.Vector3(1.0, 7.0, -1)
        ]);
        const pctGeo = new THREE.TubeGeometry(pctCurve, 32, 0.5, 8, false);
        const pctMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, roughness: 0.3 });
        group.add(new THREE.Mesh(pctGeo, pctMat));

        // 5. Loop of Henle (Blue U-turn hairpin descending into medulla)
        const henleCurve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(1.0, 7.0, -1),
          new THREE.Vector3(0.5, 2.0, -1),
          new THREE.Vector3(0.0, -6.0, -0.5),
          new THREE.Vector3(-0.5, -14.0, 0),
          new THREE.Vector3(-1.2, -18.0, 0.2),
          new THREE.Vector3(-2.0, -18.0, 0.2),
          new THREE.Vector3(-2.5, -14.0, 0),
          new THREE.Vector3(-3.0, -6.0, -0.5),
          new THREE.Vector3(-3.5, 2.0, -1),
          new THREE.Vector3(-3.8, 7.0, -0.5)
        ]);
        const henleGeo = new THREE.TubeGeometry(henleCurve, 48, 0.42, 8, false);
        const henleMat = new THREE.MeshStandardMaterial({ color: 0x3b82f6, roughness: 0.3 });
        group.add(new THREE.Mesh(henleGeo, henleMat));

        // 6. Distal Convoluted Tubule (DCT - Orange convoluted tube)
        const dctCurve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(-3.8, 7.0, -0.5),
          new THREE.Vector3(-4.5, 9.5, 0.5),
          new THREE.Vector3(-3.0, 11.5, 1.5),
          new THREE.Vector3(-1.5, 11.0, 0.8),
          new THREE.Vector3(-2.5, 9.0, -0.5),
          new THREE.Vector3(-4.0, 8.0, -1.5)
        ]);
        const dctGeo = new THREE.TubeGeometry(dctCurve, 28, 0.45, 8, false);
        const dctMat = new THREE.MeshStandardMaterial({ color: 0xf97316, roughness: 0.3 });
        group.add(new THREE.Mesh(dctGeo, dctMat));

        // 7. Collecting Duct (Yellow vertical conduit down to papilla)
        const cdCurve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(-4.0, 8.0, -1.5),
          new THREE.Vector3(-4.8, 6.0, -1.8),
          new THREE.Vector3(-5.2, 0.0, -2.0),
          new THREE.Vector3(-5.6, -10.0, -2.2),
          new THREE.Vector3(-6.0, -20.0, -2.4)
        ]);
        const cdGeo = new THREE.TubeGeometry(cdCurve, 32, 0.58, 8, false);
        const cdMat = new THREE.MeshStandardMaterial({ color: 0xeab308, roughness: 0.35 });
        group.add(new THREE.Mesh(cdGeo, cdMat));

        return group;
      }

      const pivot = new THREE.Group();
      scene.add(pivot);

      function mountNephronModel(model) {
        while (pivot.children.length > 0) {
          pivot.remove(pivot.children[0]);
        }
        model.rotation.x = -Math.PI / 2;
        model.updateMatrixWorld(true);

        const box = new THREE.Box3().setFromObject(model);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());

        model.position.sub(center);
        pivot.add(model);

        const maxDim = Math.max(size.x, size.y, size.z) || 30;
        camera.position.set(0, 4, maxDim * 1.75);
        controls.target.set(0, 0, 0);
        camera.lookAt(0, 0, 0);
        controls.update();
      }

      // Load mesh from server with fallback
      if (typeof THREE.GLTFLoader !== 'undefined') {
        const loader = new THREE.GLTFLoader();
        const url = `/api/cases/${caseId}/meshes/nephron_unit.glb`;
        loader.load(
          url,
          (gltf) => {
            const model = gltf.scene;
            model.traverse((child) => {
              if (child.isMesh) {
                child.material = new THREE.MeshStandardMaterial({
                  color: 0xffffff,
                  vertexColors: true,
                  roughness: 0.35,
                  metalness: 0.1,
                  side: THREE.DoubleSide
                });
              }
            });
            mountNephronModel(model);
          },
          undefined,
          (err) => {
            console.warn('Nephron GLB load fallback to procedural model:', err);
            mountNephronModel(createProceduralNephron());
          }
        );
      } else {
        mountNephronModel(createProceduralNephron());
      }

      function animate() {
        requestAnimationFrame(animate);
        pivot.rotation.y += 0.006;
        controls.update();
        renderer.render(scene, camera);
      }
      animate();

      return {
        resize: () => {
          const w = container.clientWidth || 500;
          const h = container.clientHeight || 440;
          if (w === 0 || h === 0) return;
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
        }
      };
    }

    function toggleMPRView() {
      const mpr = document.getElementById('mpr-viewport');
      const btn = document.getElementById('btn-toggle-mpr');
      if (!mpr) return;
      if (mpr.style.display === 'none' || !mpr.style.display) {
        mpr.style.display = 'flex';
        if (btn) {
          btn.style.color = '#38bdf8';
          btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> <span>Close 2D Slice</span>';
        }
      } else {
        mpr.style.display = 'none';
        if (btn) {
          btn.style.color = '#a78bfa';
          btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg> <span>2D CT Slice</span>';
        }
      }
      setTimeout(() => {
        if (viewer3d) viewer3d.onWindowResize();
      }, 60);
    }
    window.toggleMPRView = toggleMPRView;

    function renderCandidatesList(candidates) {
      const container = document.getElementById('candidates-container');
      const badge = document.getElementById('candidates-count-badge');
      badge.textContent = `${candidates.length} Available`;

      if (candidates.length === 0) {
        container.innerHTML = '<div style="padding: 15px; color: var(--text-secondary); text-align: center;">No feasible candidates found.</div>';
        return;
      }

      container.innerHTML = '';
      candidates.forEach((c, idx) => {
        const card = document.createElement('div');
        card.className = `candidate-card ${idx === 0 ? 'active' : ''}`;
        card.id = `card-${c.candidate_id}`;
        card.onclick = () => selectTrajectory(c.candidate_id);

        const letter = String.fromCharCode(65 + (idx % 26));
        let badgeClass = 'badge-preferred';
        let badgeLabel = 'FEASIBLE';
        let badgeIcon = '';

        if (c.safety_badge === 'REJECTED') {
          badgeClass = 'badge-rejected';
          badgeIcon = '';
          badgeLabel = 'REJECTED';
        } else if (c.safety_badge === 'CONDITIONAL' || c.safety_badge === 'MARGINAL') {
          badgeClass = 'badge-conditional';
          badgeIcon = '';
          badgeLabel = 'MARGINAL';
        } else {
          badgeClass = 'badge-preferred';
          badgeIcon = '';
          badgeLabel = 'FEASIBLE';
        }

        let mcHtml = '';
        if (c.uncertainty && c.uncertainty.length > 0) {
          mcHtml = c.uncertainty.map(u => `
            <div class="metric-row">
              <span>MC Risk (${u.hazard_name}):</span>
              <strong class="metric-val" style="color: ${u.collision_probability > 0.05 ? 'var(--accent-red)' : 'var(--accent-teal)'};">
                ${(u.collision_probability * 100).toFixed(1)}% [${u.risk_category}]
              </strong>
            </div>
          `).join('');
        }

        card.innerHTML = `
          <div class="candidate-header">
            <span style="font-weight: 700; color: var(--text-primary);">Candidate ${letter} (${c.candidate_id})</span>
            <span class="${badgeClass}">${badgeIcon} ${badgeLabel}</span>
          </div>
          <div class="metric-row">
            <span>Target Calyx:</span>
            <strong>${c.target_calyx}</strong>
          </div>
          <div class="metric-row">
            <span>Tract Length:</span>
            <strong class="metric-val">${c.tract_length_mm.toFixed(1)} mm</strong>
          </div>
          <div class="metric-row">
            <span>Min Clearance:</span>
            <strong class="metric-val" style="color: ${c.min_effective_clearance_mm > 10 ? 'var(--accent-teal)' : 'var(--accent-amber)'};">${c.min_effective_clearance_mm.toFixed(1)} mm</strong>
          </div>
          <div class="metric-row">
            <span>Stone Reach:</span>
            <strong class="metric-val">${(c.reachable_stone_fraction * 100).toFixed(0)}%</strong>
          </div>
          <div class="metric-row">
            <span>Rib Approach:</span>
            <strong>${c.access_rib_classification}</strong>
          </div>
          ${mcHtml}
        `;
        container.appendChild(card);
      });
    }

    function selectTrajectory(candidateId) {
      selectedCandidateId = candidateId;
      document.querySelectorAll('.candidate-card').forEach(c => c.classList.remove('active'));
      const card = document.getElementById(`card-${candidateId}`);
      if (card) card.classList.add('active');

      viewer3d.setActiveTrajectory(candidateId);
      const candObj = currentCandidates.find(c => c.candidate_id === candidateId);
      if (candObj) {
        mprViewer.setActiveCandidate(candObj);
      }
      updateKeyframePreview();
    }

    async function approveTrajectory() {
      if (!currentCaseId || !selectedCandidateId) {
        alert('Please select a trajectory first.');
        return;
      }
      try {
        const res = await fetch(`/api/cases/${currentCaseId}/select`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            candidate_id: selectedCandidateId,
            clinician_id: 'Surgeon_Attending_01',
            clinical_rationale: 'Approved optimal lower pole access.'
          })
        });
        const data = await res.json();
        updateStateBadge(data.state, false);
        alert(`Access Trajectory ${selectedCandidateId} approved and auditable signature logged.`);
      } catch (err) {
        alert('Approval failed: ' + err.message);
      }
    }

    async function openFluoroscopy() {
      if (!currentCaseId || !selectedCandidateId) {
        alert('Please select a trajectory candidate first.');
        return;
      }
      try {
        const res = await fetch(`/api/cases/${currentCaseId}/fluoroscopy/${selectedCandidateId}`);
        const data = await res.json();
        const views = data.views;

        document.getElementById('fluoro-bullseye-info').innerHTML = `
          Projected Length: <strong>${views.BULLS_EYE.projected_needle_length_2d_mm.toFixed(1)} mm</strong><br>
          Axis Alignment Error: <strong>${views.BULLS_EYE.alignment_angle_deg.toFixed(1)}°</strong><br>
          Optical Axis: [${views.BULLS_EYE.optical_axis_unit.join(', ')}]
        `;

        document.getElementById('fluoro-progression-info').innerHTML = `
          Projected Length: <strong>${views.PROGRESSION.projected_needle_length_2d_mm.toFixed(1)} mm</strong><br>
          Detector Position: [${views.PROGRESSION.detector_position_lps.join(', ')}]<br>
          Depth View: <strong>Orthogonal 90°</strong>
        `;

        document.getElementById('modal-fluoroscopy').style.display = 'flex';
      } catch (err) {
        alert('Could not fetch fluoroscopy data: ' + err.message);
      }
    }

    async function submitOverride() {
      const type = document.getElementById('override-type').value;
      const reason = document.getElementById('override-reason').value;
      if (!reason.trim()) {
        alert('Clinical rationale is required for CDS audit.');
        return;
      }
      try {
        const res = await fetch(`/api/cases/${currentCaseId}/override`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            override_type: type,
            reason: reason,
            clinician_id: 'Surgeon_Attending_01'
          })
        });
        const data = await res.json();
        document.getElementById('modal-override').style.display = 'none';
        updateStateBadge('STALE', true);
        alert('Override recorded. Current plan flagged as STALE per AcuCalyx governance.');
      } catch (err) {
        alert('Override submission failed: ' + err.message);
      }
    }

    function downloadPDF() {
      if (!currentCaseId) {
        alert('Please select or plan a case first.');
        return;
      }
      openPdfModal();
    }

    let currentKeyframeTab = 'axial';

    function switchKeyframeTab(tab) {
      currentKeyframeTab = tab;
      ['axial', 'coronal', 'bullseye'].forEach(t => {
        const btn = document.getElementById(`tab-kf-${t}`);
        if (btn) btn.classList.toggle('active', t === tab);
      });
      updateKeyframePreview();
    }

    function updateKeyframePreview() {
      if (!currentCaseId) return;
      const img = document.getElementById('keyframe-preview-img');
      const caption = document.getElementById('keyframe-caption');
      const pendingCard = document.getElementById('keyframe-pending-card');
      if (!img) return;

      const t = Date.now();
      let kfName = 'axial_keyframe.png';
      let capText = 'Axial MPR @ Target: needle corridor ±5mm margin, skin entry & 20mm scale bar.';

      if (currentKeyframeTab === 'coronal') {
        kfName = 'coronal_keyframe.png';
        capText = 'Coronal MPR @ Calyx Axis: longitudinal puncture slope & cranial-caudal alignment.';
      } else if (currentKeyframeTab === 'bullseye') {
        kfName = 'bullseye_keyframe.png';
        capText = 'C-Arm Bull\'s-Eye Projection: coaxial down-the-barrel reticle with calibrated gantry presets.';
      }

      // Hide image while loading to prevent broken image icon flash
      img.style.display = 'none';
      if (pendingCard) pendingCard.style.display = 'flex';

      fetch(`/api/cases/${currentCaseId}/keyframes/${kfName}?t=${t}`)
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.blob();
        })
        .then(blob => {
          if (img._prevBlobUrl) {
            URL.revokeObjectURL(img._prevBlobUrl);
          }
          const blobUrl = URL.createObjectURL(blob);
          img._prevBlobUrl = blobUrl;
          img.src = blobUrl;
          img.style.display = 'block';
          if (pendingCard) pendingCard.style.display = 'none';
        })
        .catch(() => {
          img.style.display = 'none';
          if (pendingCard) pendingCard.style.display = 'flex';
        });

      if (caption) caption.textContent = capText;

      const activeBadge = document.getElementById('keyframe-active-cand-badge');
      if (activeBadge) {
        activeBadge.textContent = selectedCandidateId || 'ACTIVE TRACT';
      }
    }

    function openKeyframeLightbox() {
      if (!currentCaseId) {
        alert('Please load an active planning case first.');
        return;
      }
      const t = Date.now();
      const badge = document.getElementById('lightbox-cand-badge');
      if (badge) badge.textContent = selectedCandidateId ? `TRACT: ${selectedCandidateId}` : 'ACTIVE CANDIDATE';
      document.getElementById('lightbox-img-axial').src = `/api/cases/${currentCaseId}/keyframes/axial_keyframe.png?t=${t}`;
      document.getElementById('lightbox-img-coronal').src = `/api/cases/${currentCaseId}/keyframes/coronal_keyframe.png?t=${t}`;
      document.getElementById('lightbox-img-bullseye').src = `/api/cases/${currentCaseId}/keyframes/bullseye_keyframe.png?t=${t}`;
      document.getElementById('modal-keyframe-lightbox').style.display = 'flex';
    }

    function openPdfModal() {
      if (!currentCaseId) {
        alert('Please load or plan a case first.');
        return;
      }
      const modal = document.getElementById('modal-pdf-report');
      const iframe = document.getElementById('pdf-report-iframe');
      const downloadLink = document.getElementById('pdf-direct-download-btn');
      const url = `/api/cases/${currentCaseId}/report?t=${Date.now()}`;
      iframe.src = url;
      downloadLink.href = url;
      downloadLink.setAttribute('download', `AcuCalyx_${currentCaseId}_Preoperative_Report.pdf`);
      modal.style.display = 'flex';
    }

    async function loadSelectedScenario(scenarioId) {
      if (!scenarioId) return;
      try {
        const res = await fetch(`/api/usability/scenarios/${scenarioId}/load`, {
          method: 'POST'
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Could not load benchmark scenario');
        }
        const data = await res.json();
        window.showToast(`Loaded scenario: ${data.title}`, 'info');
        await loadCasesList();
        document.getElementById('case-select').value = data.case_id;
        await selectCase(data.case_id);
        updateKeyframePreview();
      } catch (err) {
        alert('Scenario Loading Error: ' + err.message);
      } finally {
        document.getElementById('scenario-select').value = '';
      }
    }

    async function showProvenance() {
      if (!currentCaseId) return;
      try {
        const res = await fetch(`/api/cases/${currentCaseId}/provenance`);
        const data = await res.json();
        alert(`AcuCalyx Cryptographic Provenance Manifest:\n\nCase ID: ${data.case_id}\nSoftware Version: ${data.software_version}\nInput SHA-256: ${data.input_data_sha256}\nConfig SHA-256: ${data.configuration_sha256}\nTimestamp: ${data.analysis_timestamp}`);
      } catch (err) {
        alert('Provenance record not found. Run planning first.');
      }
    }

    async function openRehearsal() {
      if (!currentCaseId) return;
      document.getElementById('modal-rehearsal').style.display = 'flex';
      try {
        const candParam = selectedCandidateId ? `?candidate_id=${selectedCandidateId}` : '';
        const cardRes = await fetch(`/api/cases/${currentCaseId}/rehearsal/transfer-card${candParam}`);
        if (cardRes.ok) {
          const card = await cardRes.json();
          const beSignP = card.bullseye_primary_angle_deg >= 0 ? 'LAO' : 'RAO';
          const beSignS = card.bullseye_secondary_angle_deg >= 0 ? 'CRAN' : 'CAUD';
          const dvSignP = card.depth_primary_angle_deg >= 0 ? 'LAO' : 'RAO';
          const dvSignS = card.depth_secondary_angle_deg >= 0 ? 'CRAN' : 'CAUD';

          document.getElementById('transfer-angles-display').innerHTML = `
            Bull's-Eye: <span style="color: #00e5a3;">${beSignP} ${Math.abs(card.bullseye_primary_angle_deg)}° ${beSignS} ${Math.abs(card.bullseye_secondary_angle_deg)}°</span> | 
            Depth: <span style="color: #f59e0b;">${dvSignP} ${Math.abs(card.depth_primary_angle_deg)}° ${dvSignS} ${Math.abs(card.depth_secondary_angle_deg)}°</span>
          `;
          document.getElementById('rehearsal-be-angles').innerText = `${beSignP} ${Math.abs(card.bullseye_primary_angle_deg)}° ${beSignS} ${Math.abs(card.bullseye_secondary_angle_deg)}°`;
          document.getElementById('rehearsal-dv-angles').innerText = `${dvSignP} ${Math.abs(card.depth_primary_angle_deg)}° ${dvSignS} ${Math.abs(card.depth_secondary_angle_deg)}°`;
          
          if (card.laterality) {
            document.getElementById('transfer-laterality-badge').innerText = card.laterality;
          }
          if (card.projection_confidence) {
            document.getElementById('transfer-confidence-badge').innerText = card.projection_confidence;
          }
          if (card.calibration_revision) {
            document.getElementById('transfer-cal-rev-badge').innerText = card.calibration_revision;
          }
          if (card.mandatory_assumption_block) {
            const cleanAssumption = card.mandatory_assumption_block.replace('VIRTUAL PREOPERATIVE PLAN ASSUMPTION BLOCK: ', '');
            document.getElementById('transfer-assumption-block').innerHTML = `<strong>VIRTUAL PREOPERATIVE PLAN ASSUMPTION BLOCK:</strong> ${cleanAssumption}`;
          }
        }
        await loadRehearsalDrrImages();
        await updateRehearsalAdvancement();
      } catch (err) {
        console.error('Error opening rehearsal:', err);
      }
    }

    async function loadRehearsalDrrImages() {
      if (!currentCaseId) return;
      const contrastChecked = document.getElementById('rehearsal-contrast-toggle')?.checked ?? true;
      const candId = selectedCandidateId || 'candidate_a';
      const beImg = document.getElementById('rehearsal-be-img');
      const dvImg = document.getElementById('rehearsal-dv-img');
      const beFallback = document.getElementById('rehearsal-be-fallback');
      const dvFallback = document.getElementById('rehearsal-dv-fallback');

      if (beImg) {
        beImg.src = `/api/cases/${currentCaseId}/drr/${candId}/bullseye?enable_contrast=${contrastChecked}&resolution=256`;
        beImg.onload = () => {
          beImg.style.display = 'block';
          if (beFallback) beFallback.style.background = 'rgba(0,0,0,0.3)';
        };
        beImg.onerror = () => {
          beImg.style.display = 'none';
        };
      }
      if (dvImg) {
        dvImg.src = `/api/cases/${currentCaseId}/drr/${candId}/depth_verification?enable_contrast=${contrastChecked}&resolution=256`;
        dvImg.onload = () => {
          dvImg.style.display = 'block';
          if (dvFallback) dvFallback.style.background = 'rgba(0,0,0,0.3)';
        };
        dvImg.onerror = () => {
          dvImg.style.display = 'none';
        };
      }
    }

    async function updateRehearsalAdvancement() {
      if (!currentCaseId) return;
      const slider = document.getElementById('rehearsal-slider');
      const frac = parseFloat(slider.value) / 100.0;
      try {
        const res = await fetch(`/api/cases/${currentCaseId}/rehearsal/state?advancement=${frac}`);
        if (!res.ok) return;
        const state = await res.json();
        document.getElementById('rehearsal-phase-badge').innerText = `${state.active_progression_phase} (${Math.round(frac * 100)}%)`;
        document.getElementById('rehearsal-depth-readout').innerText = `${state.penetration_depth_mm} mm / ${state.total_planned_depth_mm} mm`;
        document.getElementById('rehearsal-tip-coords').innerText = `Tip LPS: [${state.current_tip_lps.join(', ')}] mm | Phase: ${state.active_progression_phase}`;
        
        const isCollapsed = state.bullseye_projection.is_collapsed;
        document.getElementById('rehearsal-be-shaft').innerText = isCollapsed ? 
          `0.0 px (Collapsed En-Face)` : `${state.bullseye_projection.shaft_length_px} px`;

        // U5 Dynamic Depth Boundary Alarm Interlock
        try {
          const depthRes = await fetch(`/api/usability/cases/${currentCaseId}/depth-check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              planned_depth_mm: state.total_planned_depth_mm,
              current_penetration_mm: state.penetration_depth_mm,
              calyx_luminal_depth_mm: 8.0,
              metrology_uncertainty_u95_mm: 1.64
            })
          });
          if (depthRes.ok) {
            const depthData = await depthRes.json();
            const tel = depthData.telemetry;
            const banner = document.getElementById('rehearsal-depth-alarm-banner');
            const icon = document.getElementById('rehearsal-alarm-icon');
            const text = document.getElementById('rehearsal-alarm-text');
            const dist = document.getElementById('rehearsal-alarm-dist');
            
            text.innerText = tel.message;
            dist.innerText = `Medial Margin: ${tel.distance_to_medial_wall_mm} mm`;
            
            if (tel.status === 'COUNTER_PUNCTURE_CRITICAL_STOP') {
              banner.style.background = 'rgba(225, 29, 72, 0.25)';
              banner.style.borderColor = '#e11d48';
              banner.style.color = '#ff4d6d';
              icon.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ef4444;box-shadow:0 0 8px #ef4444;"></span>';
            } else if (tel.status === 'MEDIAL_WALL_WARNING') {
              banner.style.background = 'rgba(245, 158, 11, 0.2)';
              banner.style.borderColor = '#f59e0b';
              banner.style.color = '#fbbf24';
              icon.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f59e0b;box-shadow:0 0 8px #f59e0b;"></span>';
            } else if (tel.status === 'LUMINAL_ACCESS') {
              banner.style.background = 'rgba(0, 210, 255, 0.15)';
              banner.style.borderColor = '#00d2ff';
              banner.style.color = '#38bdf8';
              icon.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#38bdf8;box-shadow:0 0 8px #38bdf8;"></span>';
            } else if (tel.status === 'TARGET_PAPILLA_ZONE') {
              banner.style.background = 'rgba(0, 229, 163, 0.15)';
              banner.style.borderColor = '#00e5a3';
              banner.style.color = '#34d399';
              icon.innerText = '⬢';
            } else {
              banner.style.background = 'rgba(148, 163, 184, 0.1)';
              banner.style.borderColor = '#475569';
              banner.style.color = '#94a3b8';
              icon.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#00e5a3;box-shadow:0 0 8px #00e5a3;"></span>';
            }
          }
        } catch (e) {
          console.debug('Depth check error:', e);
        }

        // Synchronize simulated ultrasound views if US or Tri tab is active
        const usView = document.getElementById('rehearsal-us-view');
        if (usView && usView.style.display !== 'none') {
          updateUltrasoundViews();
        }
      } catch (err) {
        console.error('Error updating rehearsal state:', err);
      }
    }

    function switchRehearsalTab(tab) {
      const fluroView = document.getElementById('rehearsal-fluro-view');
      const usView = document.getElementById('rehearsal-us-view');
      const tabFluro = document.getElementById('tab-rehearsal-fluro');
      const tabUs = document.getElementById('tab-rehearsal-us');
      const tabTri = document.getElementById('tab-rehearsal-tri');

      if (!tabFluro || !tabUs || !tabTri) return;

      tabFluro.className = 'btn btn-sm';
      tabUs.className = 'btn btn-sm';
      tabTri.className = 'btn btn-sm';

      if (tab === 'fluro') {
        tabFluro.className = 'btn btn-sm btn-primary';
        if (fluroView) fluroView.style.display = 'block';
        if (usView) usView.style.display = 'none';
      } else if (tab === 'us') {
        tabUs.className = 'btn btn-sm btn-primary';
        if (fluroView) fluroView.style.display = 'none';
        if (usView) usView.style.display = 'block';
        updateUltrasoundViews();
      } else if (tab === 'tri') {
        tabTri.className = 'btn btn-sm btn-primary';
        if (fluroView) fluroView.style.display = 'block';
        if (usView) usView.style.display = 'block';
        updateUltrasoundViews();
      }
    }

    async function updateUltrasoundViews() {
      if (!currentCaseId) return;
      const candId = selectedCandidateId || 'candidate_a';
      const probeId = document.getElementById('us-probe-select')?.value || 'CURV_C5_2';
      const pos = document.getElementById('us-position-select')?.value || 'PRONE_STANDARD';
      const vent = document.getElementById('us-ventilation-select')?.value || 'MECHANICAL_TIDAL';
      const habitus = document.getElementById('us-habitus-select')?.value || 'NORMAL_BMI';

      const depthReadout = document.getElementById('rehearsal-depth-readout')?.innerText || '0.0 mm';
      const penetrationMm = parseFloat(depthReadout.split(' ')[0]) || 0.0;

      // 1. Update B-Mode Simulated Ultrasound Image
      const usImg = document.getElementById('rehearsal-us-img');
      if (usImg) {
        usImg.src = `/api/cases/${currentCaseId}/us/${candId}/simulated-bmode?insertion_depth_mm=${penetrationMm}&probe_id=${probeId}&dynamic_range_db=65.0`;
      }

      // 2. Update Flank Acoustic Window Report
      try {
        const winRes = await fetch(`/api/cases/${currentCaseId}/us/${candId}/acoustic-window?probe_id=${probeId}`);
        if (winRes.ok) {
          const winData = await winRes.json();
          const winBadge = document.getElementById('us-window-badge');
          if (winBadge) {
            winBadge.innerText = winData.window_category;
            winBadge.style.background = winData.window_category === 'GOOD' ? 'rgba(0, 229, 163, 0.15)' :
                                       winData.window_category === 'CONDITIONAL' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(225, 29, 72, 0.15)';
            winBadge.style.color = winData.window_category === 'GOOD' ? '#00e5a3' :
                                   winData.window_category === 'CONDITIONAL' ? '#f59e0b' : '#e11d48';
          }
          const ribElem = document.getElementById('us-rib-occ');
          if (ribElem) ribElem.innerText = `${winData.corridor_rib_occlusion_pct}%`;
          const pleuraElem = document.getElementById('us-pleura-dist');
          if (pleuraElem) pleuraElem.innerText = `${winData.pleural_clearance_mm} mm`;
          const skinElem = document.getElementById('us-skin-contact');
          if (skinElem) skinElem.innerText = `${winData.skin_contact_conformance_pct}%`;
          const naviElem = document.getElementById('us-navi-val');
          if (naviElem) naviElem.innerText = `${winData.navi_score}`;
        }
      } catch (e) {
        console.debug('Ultrasound window fetch error:', e);
      }

      // 3. Update Positioning Uncertainty & Monte Carlo Clearance
      try {
        const posRes = await fetch(`/api/cases/${currentCaseId}/us/${candId}/position-uncertainty?position=${pos}&habitus=${habitus}&ventilation=${vent}`);
        if (posRes.ok) {
          const posData = await posRes.json();
          const mc = posData.monte_carlo_clearance;
          const mcElem = document.getElementById('us-mc-prob');
          if (mcElem) mcElem.innerText = `${(mc.overall_clearance_probability * 100).toFixed(1)}%`;
          const marginElem = document.getElementById('us-mc-margin');
          if (marginElem) marginElem.innerText = `${mc.fifth_percentile_margin_mm} mm`;
          
          const tierBadge = document.getElementById('us-tier-badge');
          if (tierBadge) {
            tierBadge.innerText = posData.safety_tier;
            tierBadge.style.background = posData.safety_tier === 'PREFERRED' ? 'rgba(0, 229, 163, 0.15)' :
                                        posData.safety_tier === 'FEASIBLE' ? 'rgba(0, 210, 255, 0.15)' :
                                        posData.safety_tier === 'CONDITIONAL' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(225, 29, 72, 0.2)';
            tierBadge.style.color = posData.safety_tier === 'PREFERRED' ? '#00e5a3' :
                                    posData.safety_tier === 'FEASIBLE' ? '#00d2ff' :
                                    posData.safety_tier === 'CONDITIONAL' ? '#f59e0b' : '#e11d48';
          }
          const advisoryBox = document.getElementById('us-clinical-advisory');
          if (advisoryBox) advisoryBox.innerText = posData.clinical_advisory;
        }
      } catch (e) {
        console.debug('Ultrasound position uncertainty fetch error:', e);
      }
    }

    // Interlock U1: Pre-Puncture Laterality Verification
    function openLateralityModal() {
      if (!currentCaseId) {
        alert('Please load or create an active case first.');
        return;
      }
      document.getElementById('lat-case-id-display').innerText = currentCaseId;
      const targetSide = document.getElementById('target-side-label').innerText.includes('RIGHT') ? 'RIGHT' : 'LEFT';
      document.getElementById('lat-ct-side-display').innerText = `${targetSide} KIDNEY`;
      document.getElementById('modal-laterality').style.display = 'flex';
    }

    async function submitLateralityConfirmation() {
      if (!currentCaseId) return;
      const isTwoStep = document.getElementById('check-twostep-confirm').checked;
      if (!isTwoStep) {
        alert('Interlock U1 Violation: Explicit Two-Step confirmation signature required.');
        return;
      }

      const selectedSide = document.querySelector('input[name="lat-target-side"]:checked').value;
      const ctSide = document.getElementById('target-side-label').innerText.includes('RIGHT') ? 'RIGHT' : 'LEFT';
      const landmarks = {
        spleen_left_quadrant: document.getElementById('check-landmark-spleen').checked,
        liver_right_quadrant: document.getElementById('check-landmark-liver').checked,
        spine_prone_table_concordant: document.getElementById('check-landmark-spine').checked
      };

      try {
        const res = await fetch(`/api/usability/cases/${currentCaseId}/laterality-confirm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clinician_selected_side: selectedSide,
            ct_metadata_side: ctSide,
            landmark_checks: landmarks,
            is_two_step_confirmed: true
          })
        });

        if (!res.ok) {
          const errData = await res.json();
          alert(`Interlock U1 Rejection:\n\n${errData.detail || 'Laterality verification failed.'}`);
          return;
        }

        const data = await res.json();
        currentVerifiedLaterality = (data.confirmed_side || selectedSide).toLowerCase();
        if (currentCaseMeta) {
          currentCaseMeta.target_side = currentVerifiedLaterality;
        }
        document.getElementById('target-side-label').textContent = `${currentVerifiedLaterality.toUpperCase()} KIDNEY (U1 VERIFIED)`;
        document.getElementById('modal-laterality').style.display = 'none';
        if (typeof window.showToast === 'function') {
          window.showToast(`Interlock U1 Passed: Laterality verified for ${data.confirmed_side} KIDNEY.`, 'success', 3500);
        } else {
          // toast already displayed above
        }
        // Auto-transition to Interlock U2 Operative Pose Gate if not yet confirmed
        if (!currentCaseMeta?.surgical_position_confirmation?.is_confirmed) {
          const posModal = document.getElementById('modal-position-confirm');
          if (posModal) {
            posModal.style.display = 'flex';
            if (typeof loadPositionConfirmationData === 'function') loadPositionConfirmationData();
          }
        }
      } catch (err) {
        alert('Laterality check network error: ' + err.message);
      }
    }

    // =========================================================================
    // Interlock U2: Surgical Patient Position & Orientation Gate
    // =========================================================================
    function openPositionConfirmModal() {
      if (!currentCaseId) {
        alert('Please load or create an active case first.');
        return;
      }
      document.getElementById('pos-case-id-display').innerText = currentCaseId;
      const ctTag = (currentCaseMeta && currentCaseMeta.patient_position_tag) ? currentCaseMeta.patient_position_tag : 'HFS (Head First Supine)';
      document.getElementById('pos-ct-tag-display').innerText = ctTag;

      const confirmedPose = currentCaseMeta?.surgical_position_confirmation?.operative_position || 'PRONE_STANDARD';
      const rad = document.querySelector(`input[name="surgical-pose-opt"][value="${confirmedPose}"]`);
      if (rad) rad.checked = true;
      updatePoseTransformPreview(confirmedPose);

      document.getElementById('modal-position-confirm').style.display = 'flex';
    }

    function updatePoseTransformPreview(pose) {
      const descEl = document.getElementById('pose-transform-desc');
      if (!descEl) return;
      if (pose === 'PRONE_STANDARD' || pose === 'PRONE_SPLIT_LEG') {
        descEl.innerHTML = `CT Supine (HFS) &rarr; <strong>Prone Operative Setup</strong>: Inverts Left-Right (X) and Anterior-Posterior (Y) axes: <code>diag(-1, -1, 1, 1)</code>. AcuCalyx automatically applies this rigid transformation to all C-arm gantry projections and needle entry vectors.`;
      } else if (pose === 'FLANK_LATERAL') {
        descEl.innerHTML = `CT Supine (HFS) &rarr; <strong>Flank Lateral Pose</strong>: Applies 90&deg; roll rotation about cranial-caudal (Z) axis. C-arm frontal becomes lateral; oblique angles rotate accordingly.`;
      } else if (pose === 'SUPINE_VALDIVIA') {
        descEl.innerHTML = `CT Supine (HFS) &rarr; <strong>Supine Valdivia / Galdakao Pose</strong>: Concordant with CT supine acquisition frame. Identity spatial transformation applied with slight flank elevation tilt compensation.`;
      }
    }

    async function submitPositionConfirmation() {
      if (!currentCaseId) return;
      const isClinicianSigned = document.getElementById('check-pos-twostep').checked;
      if (!isClinicianSigned) {
        alert('Interlock U2 Violation: Clinician authorization signature checkbox is required.');
        return;
      }

      const selectedPose = document.querySelector('input[name="surgical-pose-opt"]:checked')?.value || 'PRONE_STANDARD';
      const ctAcq = (currentCaseMeta && currentCaseMeta.patient_position_tag) ? currentCaseMeta.patient_position_tag : 'HFS';

      try {
        const res = await fetch(`/api/usability/cases/${currentCaseId}/position-confirm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ct_acquisition_position: ctAcq,
            planned_operative_position: selectedPose,
            is_clinician_confirmed: true
          })
        });

        if (!res.ok) {
          const errData = await res.json();
          alert(`Interlock U2 Rejection:\n\n${errData.detail || 'Position confirmation failed.'}`);
          return;
        }

        const data = await res.json();
        if (currentCaseMeta) {
          if (!currentCaseMeta.surgical_position_confirmation) {
            currentCaseMeta.surgical_position_confirmation = {};
          }
          currentCaseMeta.surgical_position_confirmation.is_confirmed = true;
          currentCaseMeta.surgical_position_confirmation.operative_position = selectedPose;
        }

        const poseEl = document.getElementById('info-surgical-pose');
        if (poseEl) {
          poseEl.textContent = `${selectedPose} (U2 VERIFIED)`;
          poseEl.style.color = 'var(--accent-teal)';
        }

        document.getElementById('modal-position-confirm').style.display = 'none';
        window.showToast(`Interlock U2 Passed: Position verified as ${selectedPose}`, 'success');
      } catch (err) {
        alert('Position verification network error: ' + err.message);
      }
    }

    // =========================================================================
    // Milestone M15: Flexible Endoscopic Reachability & Stone Clearance Cockpit
    // =========================================================================
    let currentEndoKeyframes = [];

    function openEndoscopyModal() {
      if (!currentCaseId) {
        alert('Please load or create an active case first.');
        return;
      }
      const candId = selectedCandidateId || (currentCandidates[0] ? (currentCandidates[0].candidate_id || currentCandidates[0].id) : 'cand-001');
      const tractLabel = currentCandidates[0]?.target_calyx || 'Posterior Lower Pole';
      document.getElementById('endo-tract-display').innerText = `${candId} (${tractLabel})`;
      document.getElementById('modal-endoscopy').style.display = 'flex';
      loadEndoscopyData();
    }

    function switchEndoTab(tabKey) {
      const tabs = ['reach', 'stone', 'caliber', 'flythrough'];
      tabs.forEach(t => {
        const btn = document.getElementById(`tab-endo-btn-${t}`);
        const content = document.getElementById(`endo-tab-${t}`);
        if (btn) btn.classList.toggle('active', t === tabKey);
        if (content) content.style.display = (t === tabKey) ? 'block' : 'none';
      });
    }

    async function loadEndoscopyData() {
      if (!currentCaseId) return;
      const candId = selectedCandidateId || (currentCandidates[0] ? (currentCandidates[0].candidate_id || currentCandidates[0].id) : 'cand-001');
      const instModel = document.getElementById('endo-instrument-select').value;
      const toolConfig = document.getElementById('endo-tool-select').value;
      const isDemo = currentCaseMeta?.is_demo !== false;

      try {
        // 1. Fetch Reachability
        const reachUrl = `/api/cases/${currentCaseId}/endoscopy/${candId}/reachability?instrument_model_id=${instModel}&tool=${toolConfig}&demo_mode=${isDemo}`;
        const reachRes = await fetch(reachUrl);
        if (reachRes.ok) {
          const reachData = await reachRes.json();
          renderEndoReachability(reachData);
        }

        // 2. Fetch Stone Coverage
        const stoneUrl = `/api/cases/${currentCaseId}/endoscopy/${candId}/stone-coverage?instrument_model_id=${instModel}&tool=${toolConfig}&demo_mode=${isDemo}`;
        const stoneRes = await fetch(stoneUrl);
        if (stoneRes.ok) {
          const stoneData = await stoneRes.json();
          renderEndoStoneCoverage(stoneData);
        }

        // 3. Fetch Access Caliber Profiles
        const caliberUrl = `/api/cases/${currentCaseId}/endoscopy/${candId}/access-caliber-profiles?demo_mode=${isDemo}`;
        const caliberRes = await fetch(caliberUrl);
        if (caliberRes.ok) {
          const caliberData = await caliberRes.json();
          renderEndoCaliberProfiles(caliberData);
        }

        // 4. Fetch Flythrough Rehearsal Keyframes
        const flyUrl = `/api/cases/${currentCaseId}/endoscopy/${candId}/endoluminal-rehearsal?instrument_model_id=${instModel}&tool=${toolConfig}&demo_mode=${isDemo}`;
        const flyRes = await fetch(flyUrl);
        if (flyRes.ok) {
          const flyData = await flyRes.json();
          currentEndoKeyframes = flyData.keyframes || [];
          const slider = document.getElementById('endo-kf-slider');
          if (slider && currentEndoKeyframes.length > 0) {
            slider.max = currentEndoKeyframes.length - 1;
            slider.value = 0;
            onEndoSliderChange(0);
          }
        }
      } catch (err) {
        console.error('Error fetching endoscopy analytics:', err);
      }
    }

    function renderEndoReachability(data) {
      const calyces = data.calyces || [];
      const accessibleCount = calyces.filter(c => c.accessible).length;
      const totalCount = calyces.length || 1;
      const covPct = Math.round((accessibleCount / totalCount) * 100);

      document.getElementById('endo-kpi-coverage').innerText = `${covPct}%`;
      document.getElementById('endo-kpi-calyces-count').innerText = `${accessibleCount} of ${totalCount} Calyces Accessible`;

      const minMargin = calyces.reduce((min, c) => Math.min(min, c.deflection_clearance_deg), 999);
      const marginEl = document.getElementById('endo-kpi-margin');
      if (marginEl) {
        marginEl.innerText = minMargin < 900 ? `+${minMargin.toFixed(1)}°` : 'N/A';
        marginEl.style.color = minMargin > 15 ? '#10b981' : (minMargin > 0 ? '#f59e0b' : '#ef4444');
      }

      const secEl = document.getElementById('endo-kpi-secondary');
      if (secEl) {
        const needSec = accessibleCount < totalCount;
        secEl.innerText = needSec ? 'SECOND TRACT ADVISED' : 'NOT REQUIRED';
        secEl.style.color = needSec ? '#f59e0b' : '#10b981';
      }

      const tbody = document.getElementById('endo-reach-tbody');
      if (tbody) {
        tbody.innerHTML = calyces.map(c => `
          <tr style="border-bottom: 1px solid var(--border-color);">
            <td style="padding: 6px 8px; font-weight: 700; color: var(--accent-cyan);">${c.calyx_group} (${c.calyx_id})</td>
            <td style="padding: 6px 8px;">${c.access_mode}</td>
            <td style="padding: 6px 8px;">${c.ipa_deg ? c.ipa_deg.toFixed(1) + '°' : '--'}</td>
            <td style="padding: 6px 8px;">${c.required_deflection_deg.toFixed(1)}°</td>
            <td style="padding: 6px 8px;">${c.max_deflection_deg.toFixed(1)}°</td>
            <td style="padding: 6px 8px; font-weight: 600; color: ${c.deflection_clearance_deg > 0 ? '#10b981' : '#ef4444'};">
              ${c.deflection_clearance_deg > 0 ? '+' : ''}${c.deflection_clearance_deg.toFixed(1)}°
            </td>
            <td style="padding: 6px 8px;">
              <span class="version-pill" style="background: ${c.accessible ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)'}; color: ${c.accessible ? '#10b981' : '#ef4444'};">
                ${c.accessible ? 'ACCESSIBLE' : 'RESTRICTED'}
              </span>
            </td>
          </tr>
        `).join('');
      }

      const advEl = document.getElementById('endo-reach-advisory');
      if (advEl && data.strategic_advisory) {
        advEl.innerText = `Strategic Advisory: ${data.strategic_advisory}`;
      }
    }

    function renderEndoStoneCoverage(data) {
      const covPct = data.geometric_coverage_estimate_percent ?? 100;
      document.getElementById('endo-stone-cov-pct').innerText = `${covPct.toFixed(1)}%`;
      document.getElementById('endo-stone-cov-bar').style.width = `${Math.min(100, covPct)}%`;
      document.getElementById('endo-accessible-vol').innerText = `${data.total_accessible_volume_mm3 ?? 0} mm³`;
      document.getElementById('endo-total-vol').innerText = `${data.total_stone_volume_mm3 ?? 0} mm³`;

      const tbody = document.getElementById('endo-stone-tbody');
      if (tbody) {
        const stones = data.stones || [];
        tbody.innerHTML = stones.map(s => `
          <tr style="border-bottom: 1px solid var(--border-color);">
            <td style="padding: 6px 8px; font-family: monospace; font-weight: 600;">${s.stone_id}</td>
            <td style="padding: 6px 8px; color: var(--accent-cyan); font-weight: 600;">${s.calyx_id}</td>
            <td style="padding: 6px 8px;">${s.total_volume_mm3}</td>
            <td style="padding: 6px 8px; font-weight: 700; color: #10b981;">${(s.coverage_fraction * 100).toFixed(0)}%</td>
            <td style="padding: 6px 8px;">
              <span class="version-pill" style="background: ${s.access_class === 'FULLY_ACCESSIBLE' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)'}; color: ${s.access_class === 'FULLY_ACCESSIBLE' ? '#10b981' : '#f59e0b'};">
                ${s.access_class}
              </span>
            </td>
            <td style="padding: 6px 8px; color: var(--text-secondary);">${s.access_mode || 'Flexible Laser Lithotripsy'}</td>
          </tr>
        `).join('');
      }
    }

    function renderEndoCaliberProfiles(data) {
      const minFeret = data.target_calyx_min_feret_mm ?? 6.2;
      document.getElementById('endo-min-feret-display').innerText = `${minFeret.toFixed(2)} mm`;

      const container = document.getElementById('endo-caliber-cards-container');
      if (!container) return;

      const profiles = data.profiles || {};
      const cardsHtml = Object.entries(profiles).map(([pk, p]) => {
        const isCompatible = p.infundibular_clearance_status === 'COMPATIBLE' || p.infundibular_clearance_status === 'AMPLE_CLEARANCE';
        return `
          <div style="background: #0b0e14; border: 1px solid ${isCompatible ? '#10b981' : '#f59e0b'}; border-radius: 6px; padding: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-size: 13px; font-weight: 700; color: ${isCompatible ? '#10b981' : '#f59e0b'};">${p.caliber_class} (${p.sheath_french} Fr)</span>
              <span class="version-pill" style="background: ${isCompatible ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)'}; color: ${isCompatible ? '#10b981' : '#f59e0b'};">
                ${p.infundibular_clearance_status}
              </span>
            </div>
            <div style="font-size: 11px; margin-bottom: 4px;">Sheath Outer Diameter: <strong>${p.sheath_outer_diameter_mm} mm</strong> (Min Feret: ${p.minimum_lumen_feret_required_mm} mm)</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 6px;">Lithotripsy: <strong>${p.primary_lithotripsy_modality}</strong> | ${p.evacuation_mechanism}</div>
            <div style="font-size: 10.5px; color: #94a3b8; border-top: 1px solid #1e293b; padding-top: 6px; line-height: 1.35;">
              ${p.relative_operative_tradeoffs}
            </div>
          </div>
        `;
      }).join('');
      container.innerHTML = cardsHtml;
    }

    function onEndoSliderChange(frameIdx) {
      const idx = parseInt(frameIdx, 10);
      if (!currentEndoKeyframes || !currentEndoKeyframes[idx]) return;
      const kf = currentEndoKeyframes[idx];

      document.getElementById('endo-kf-frame-label').innerText = `Frame ${idx} / ${currentEndoKeyframes.length - 1}`;
      document.getElementById('endo-kf-arc').innerText = `${kf.arc_length_s.toFixed(1)} mm`;
      document.getElementById('endo-kf-calyx').innerText = kf.current_calyx_id || kf.current_calyx_group || 'LP';
      document.getElementById('endo-kf-deflection').innerText = `${kf.active_deflection_deg.toFixed(1)}°`;
      document.getElementById('endo-kf-feret').innerText = kf.min_feret_diameter_mm ? `${kf.min_feret_diameter_mm.toFixed(1)} mm` : '-- mm';

      const pos = kf.camera_position_lps || [0, 0, 0];
      const fwd = kf.camera_forward_vector || [0, 0, 1];
      document.getElementById('endo-kf-cam-pos').innerText = `[${pos[0]}, ${pos[1]}, ${pos[2]}]`;
      document.getElementById('endo-kf-cam-fwd').innerText = `[${fwd[0]}, ${fwd[1]}, ${fwd[2]}]`;
    }

    async function loadPhantomModalData() {
      const container = document.getElementById('phantom-catalog-container');
      if (!container) return;
      try {
        const caseId = currentCaseId || 'demo-case-001';
        const res = await fetch(`/api/cases/${caseId}/endoscopy/reference-phantoms`);
        if (!res.ok) {
          container.innerText = 'Unable to load reference phantom registry.';
          return;
        }
        const data = await res.json();
        const phantoms = data.reference_phantoms || [];
        if (phantoms.length === 0) {
          container.innerText = 'No certified phantoms registered.';
          return;
        }
        container.innerHTML = phantoms.map(p => `
          <div style="background: #0b0e14; border: 1px solid var(--border-color); border-radius: 6px; padding: 10px; margin-top: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <strong style="color: var(--accent-cyan); font-size: 12px;">${p.phantom_id}</strong>
              <span class="version-pill" style="color: #10b981; background: rgba(16, 185, 129, 0.15);">${p.material}</span>
            </div>
            <div style="color: var(--text-secondary); margin-bottom: 6px;">${p.description}</div>
            <div style="display: flex; gap: 14px; color: var(--text-secondary); font-size: 10.5px;">
              <span>Refractive Index: <strong style="color: #fff;">${p.refractive_index}</strong></span>
              <span>Optical Fiducials: <strong style="color: #fff;">${p.fiducials_count}</strong></span>
              <span>Pelvis Volume: <strong style="color: #fff;">${p.pelvis_volume_mm3} mm³</strong></span>
            </div>
          </div>
        `).join('');
      } catch (err) {
        container.innerText = 'Error loading phantom registry: ' + err.message;
      }
    }

    // Interlock U4: C-Arm Technologist Communication Card & Verbal Readback
    async function openVerbalProtocolCard() {
      if (!currentCaseId) {
        alert('Please load or create an active case first.');
        return;
      }
      try {
        const res = await fetch(`/api/usability/cases/${currentCaseId}/verbal-card?carm_model=philips_zenition_70`);
        if (!res.ok) {
          alert('Could not generate verbal communication card.');
          return;
        }
        const card = await res.json();
        document.getElementById('vp-carm-model').innerText = `Hardware Profile: ${card.carm_model}`;
        document.getElementById('vp-be-angles').innerText = `Primary ${card.bullseye_angles.primary_deg}°, Secondary ${card.bullseye_angles.secondary_deg}°`;
        document.getElementById('vp-dv-angles').innerText = `Primary ${card.depth_angles.primary_deg}°, Secondary ${card.depth_angles.secondary_deg}°`;
        document.getElementById('vp-tube-hint').innerText = card.tube_direction_hint;

        document.getElementById('vp-script-step1').innerText = card.bullseye_verbal_script.directive;
        document.getElementById('vp-script-step2').innerText = card.bullseye_verbal_script.readback;
        document.getElementById('vp-script-step3').innerText = card.bullseye_verbal_script.confirmation;
        document.getElementById('vp-script-step4').innerText = card.bullseye_verbal_script.verification;

        document.getElementById('vp-test-primary').value = card.bullseye_angles.primary_deg;
        document.getElementById('vp-test-secondary').value = card.bullseye_angles.secondary_deg;

        const valBox = document.getElementById('vp-validation-result');
        valBox.style.display = 'none';

        document.getElementById('modal-verbal-protocol').style.display = 'flex';
      } catch (err) {
        alert('Error loading verbal protocol card: ' + err.message);
      }
    }

    // C-Arm Angle Entry Transposition Error Detector
    async function validateCarmAngleEntry() {
      const beText = document.getElementById('vp-be-angles').innerText;
      // Extract intended numbers from primary/secondary
      const primEntered = parseFloat(document.getElementById('vp-test-primary').value);
      const secEntered = parseFloat(document.getElementById('vp-test-secondary').value);

      // Parse intended from card
      const matches = beText.match(/Primary\s+([-\d.]+).*Secondary\s+([-\d.]+)/);
      if (!matches) return;
      const intendedPrim = parseFloat(matches[1]);
      const intendedSec = parseFloat(matches[2]);

      try {
        const res = await fetch('/api/usability/carm-entry-validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            intended_primary_deg: intendedPrim,
            intended_secondary_deg: intendedSec,
            entered_primary_deg: primEntered,
            entered_secondary_deg: secEntered,
            tolerance_deg: 1.0
          })
        });

        if (!res.ok) return;
        const data = await res.json();
        const valBox = document.getElementById('vp-validation-result');
        valBox.style.display = 'block';

        if (data.is_correct) {
          valBox.style.background = 'rgba(0, 229, 163, 0.15)';
          valBox.style.border = '1px solid #00e5a3';
          valBox.style.color = '#00e5a3';
          valBox.innerText = `Gantry Angle Validated: Matches intended plan within 1.0° (Total Angular Error: ${data.total_angular_error_deg}°).`;
        } else {
          valBox.style.background = 'rgba(225, 29, 72, 0.2)';
          valBox.style.border = '1px solid #e11d48';
          valBox.style.color = '#ff4d6d';
          valBox.innerText = `${data.error_description} (Type: ${data.transposition_error_type}, Total Angular Error: ${data.total_angular_error_deg}°).`;
        }
      } catch (err) {
        console.error('Validation error:', err);
      }
    }

    // ==========================================
    // Milestone M14.5: Comparison Matrix & 1-Page Summary Card Subsystem
    // ==========================================

    function formatMetricValue(m) {
      if (!m) return '--';
      if (m.status === 'NOT_EVALUABLE') {
        return `<span style="color: var(--text-muted); font-style: italic; font-size: 10px;">NOT_EVALUABLE (${m.reason || 'Unobserved'})</span>`;
      }
      const valStr = (m.value !== null && m.value !== undefined) ? m.value : '--';
      let extra = '';
      if (m.status === 'UNCERTAIN') {
        extra += ` <span class="version-pill" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; font-size: 9px;">UNCERTAIN</span>`;
      }
      if (m.confidence === 'LOW') {
        extra += ` <span class="version-pill" style="background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 9px;">LOW CONF</span>`;
      }
      return `<strong>${valStr} ${m.unit || ''}</strong>${extra}`;
    }

    async function openComparisonMatrix() {
      if (!currentCaseId) {
        alert('Please load or select a case first.');
        return;
      }
      const modal = document.getElementById('modal-comparison-matrix');
      modal.style.display = 'flex';
      const loading = document.getElementById('matrix-loading');
      const content = document.getElementById('matrix-content');
      loading.style.display = 'block';
      content.style.display = 'none';

      try {
        const res = await fetch(`/api/cases/${currentCaseId}/candidates/comparison-matrix`);
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Could not fetch candidate comparison matrix');
        }
        const data = await res.json();
        renderComparisonMatrix(data);
        loading.style.display = 'none';
        content.style.display = 'block';
      } catch (err) {
        loading.innerHTML = `
          <div style="color: var(--accent-red); padding: 24px; text-align: center;">
            <div style="font-size: 16px; font-weight: 700; margin-bottom: 6px;">Comparison Matrix Unavailable</div>
            <div style="font-size: 12px; color: var(--text-secondary);">${err.message}</div>
          </div>
        `;
      }
    }

    function renderComparisonMatrix(matrix) {
      document.getElementById('matrix-case-id').textContent = matrix.case_id;
      document.getElementById('matrix-modality').textContent = matrix.imaging_modality;
      document.getElementById('matrix-position').textContent = matrix.patient_position_assumed;
      document.getElementById('matrix-stone-vol').textContent = `${matrix.total_stone_volume_mm3?.value ?? '--'} ${matrix.total_stone_volume_mm3?.unit || 'mm³'}`;
      document.getElementById('matrix-provenance-hash').textContent = (matrix.provenance_hash || '').substring(0, 16) + '...';
      if (matrix.disclaimer) {
        document.getElementById('matrix-disclaimer-text').textContent = matrix.disclaimer;
      }

      const table = document.getElementById('comparison-matrix-table');
      table.innerHTML = '';

      const candidates = matrix.candidates || [];
      if (candidates.length === 0) {
        table.innerHTML = '<tr><td style="padding: 20px; text-align: center; color: var(--text-secondary);">No candidate tracts evaluated for this case.</td></tr>';
        return;
      }

      const activeId = matrix.active_candidate_id || selectedCandidateId;

      // Build Table Structure: Header row + Parameter rows
      const thead = document.createElement('thead');
      const trHead = document.createElement('tr');
      const thParam = document.createElement('th');
      thParam.style.width = '200px';
      thParam.textContent = 'Clinical Parameter / Tract';
      trHead.appendChild(thParam);

      candidates.forEach((c, idx) => {
        const letter = String.fromCharCode(65 + (idx % 26));
        const isActive = (c.candidate_id === activeId);
        const th = document.createElement('th');
        th.className = `matrix-candidate-col ${isActive ? 'matrix-active-col' : ''}`;
        th.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-size: 13px; font-weight: 800; color: var(--text-primary);">Candidate ${letter}</span>
            ${isActive ? '<span class="version-pill" style="background: rgba(0, 229, 163, 0.15); color: #00e5a3; font-weight: 700; font-size: 9px;">ACTIVE PLAN</span>' : ''}
          </div>
          <div style="font-size: 10px; color: var(--text-secondary); font-family: var(--font-mono);">${c.candidate_id}</div>
          <button class="btn btn-sm ${isActive ? 'btn-success' : 'btn-primary'}" style="width: 100%; margin-top: 6px; font-size: 10px;" onclick="selectTractFromMatrix('${c.candidate_id}')">
            ${isActive ? 'Selected' : 'Select This Tract'}
          </button>
        `;
        trHead.appendChild(th);
      });
      thead.appendChild(trHead);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');

      function addMatrixRow(title, getterFn) {
        const tr = document.createElement('tr');
        const tdTitle = document.createElement('td');
        tdTitle.className = 'matrix-row-header';
        tdTitle.innerHTML = title;
        tr.appendChild(tdTitle);

        candidates.forEach(c => {
          const td = document.createElement('td');
          const isActive = (c.candidate_id === activeId);
          if (isActive) td.className = 'matrix-active-col';
          td.innerHTML = getterFn(c, isActive);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      }

      addMatrixRow('Target Calyx', c => `<strong>${c.target_calyx_name}</strong> <span style="font-size: 10px; color: var(--text-secondary);">(${c.target_calyx_id})</span>`);
      addMatrixRow('Working Tract Depth', c => formatMetricValue(c.tract_length_mm));
      addMatrixRow('Puncture Angles', c => `Coronal: ${formatMetricValue(c.puncture_angle_coronal_deg)}<br>Sagittal: ${formatMetricValue(c.puncture_angle_sagittal_deg)}`);
      addMatrixRow('Rib Intercostal Relation', c => `<strong>${c.rib_relation}</strong>`);
      addMatrixRow('Pleural Reflection Clearance', c => {
        const val = c.pleural_clearance?.value;
        const color = (val !== null && val < 10) ? 'color: var(--accent-red); font-weight: 700;' : '';
        return `<span style="${color}">${formatMetricValue(c.pleural_clearance)}</span>`;
      });
      addMatrixRow('Retrorenal Colon Margin', c => {
        const val = c.colon_clearance?.value;
        const color = (val !== null && val < 15) ? 'color: var(--accent-amber); font-weight: 700;' : '';
        return `<span style="${color}">${formatMetricValue(c.colon_clearance)}</span>`;
      });
      addMatrixRow('Major Vascular Margin', c => formatMetricValue(c.vascular_clearance));
      addMatrixRow('Rigid Scope Reach', c => `${formatMetricValue(c.rigid_accessible_stone_percent)} <span style="font-size: 10px; color: var(--text-secondary);">(${c.rigid_accessible_stone_volume_mm3?.value ?? '--'} mm³)</span>`);
      addMatrixRow('Flexible Scope Reach', c => `${formatMetricValue(c.flexible_accessible_stone_percent)} <span style="font-size: 10px; color: var(--text-secondary);">(${c.flexible_accessible_stone_volume_mm3?.value ?? '--'} mm³)</span>`);
      addMatrixRow('Inaccessible Volume', c => formatMetricValue(c.inaccessible_stone_volume_mm3));
      addMatrixRow('Sheath Caliber (EAU)', c => `<div style="font-size: 11px; line-height: 1.35;">${c.caliber_suitability_considerations}</div>`);
      addMatrixRow('Irrigation Pressure Risk', c => `<div style="font-size: 11px; line-height: 1.35;">${c.irrigation_pressure_risk}</div>`);
      addMatrixRow('Uncertainty Flags', c => {
        if (!c.uncertainty_flags || c.uncertainty_flags.length === 0) {
          return '<span style="color: #10b981; font-size: 11px;">No anatomical flags</span>';
        }
        return c.uncertainty_flags.map(f => `<span class="version-pill" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; font-size: 9px; display: inline-block; margin-bottom: 2px;">${f}</span>`).join(' ');
      });
      addMatrixRow('Clinical Trade-Off Summary', c => `<div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4;">${c.clinical_tradeoff_summary}</div>`);

      table.appendChild(tbody);
    }

    function selectTractFromMatrix(candidateId) {
      selectTrajectory(candidateId);
      document.getElementById('modal-comparison-matrix').style.display = 'none';
    }

    async function openSummaryCard() {
      if (!currentCaseId) {
        alert('Please load or select a case first.');
        return;
      }
      const modal = document.getElementById('modal-summary-card');
      modal.style.display = 'flex';

      // 1. Header Metadata
      document.getElementById('card-case-id').textContent = currentCaseId;
      const targetSide = (currentVerifiedLaterality || (currentCaseMeta && currentCaseMeta.target_side) || 'left').toUpperCase();
      document.getElementById('card-side').textContent = targetSide;
      document.getElementById('card-modality').textContent = currentCaseMeta?.modality || 'NCCT (Preop CT)';
      document.getElementById('card-date').textContent = new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC';

      // 2. Active Candidate
      const activeCand = currentCandidates.find(c => c.candidate_id === selectedCandidateId) || currentCandidates[0];
      if (activeCand) {
        document.getElementById('card-cand-id').textContent = activeCand.candidate_id;
        document.getElementById('card-rib-badge').textContent = activeCand.access_rib_classification || 'SUBCOSTAL';
        document.getElementById('card-target-calyx').textContent = activeCand.target_calyx || activeCand.target_calyx_name || '--';
        document.getElementById('card-depth').textContent = (activeCand.tract_length_mm ? activeCand.tract_length_mm.toFixed(1) : '--') + ' mm';
        document.getElementById('card-coronal-angle').textContent = (activeCand.puncture_angle_coronal_deg !== undefined ? activeCand.puncture_angle_coronal_deg.toFixed(1) : (activeCand.carm_primary_angle_deg || '--')) + '°';
        document.getElementById('card-sagittal-angle').textContent = (activeCand.puncture_angle_sagittal_deg !== undefined ? activeCand.puncture_angle_sagittal_deg.toFixed(1) : (activeCand.carm_secondary_angle_deg || '--')) + '°';
      }

      // 3. Section 2 Table: Evaluated Candidate Tracts Comparison
      const tbody = document.getElementById('card-comparison-tbody');
      tbody.innerHTML = '';
      try {
        const res = await fetch(`/api/cases/${currentCaseId}/candidates/comparison-matrix`);
        if (res.ok) {
          const matrix = await res.json();
          document.getElementById('card-hash').textContent = matrix.provenance_hash || '--';
          (matrix.candidates || []).forEach(c => {
            const tr = document.createElement('tr');
            const isActive = (c.candidate_id === (matrix.active_candidate_id || selectedCandidateId));
            if (isActive) tr.style.background = '#f0fdf4';
            tr.innerHTML = `
              <td style="padding: 4px 6px; border: 1px solid #cbd5e1; font-weight: ${isActive ? '800' : '500'};">${c.candidate_id} ${isActive ? '⭐' : ''}</td>
              <td style="padding: 4px 6px; border: 1px solid #cbd5e1;">${c.target_calyx_name}</td>
              <td style="padding: 4px 6px; border: 1px solid #cbd5e1;">${c.tract_length_mm?.value ?? '--'} mm</td>
              <td style="padding: 4px 6px; border: 1px solid #cbd5e1; color: ${(c.colon_clearance?.value < 15) ? '#b45309' : '#0f172a'};">${c.colon_clearance?.value ?? '--'} mm</td>
              <td style="padding: 4px 6px; border: 1px solid #cbd5e1; color: ${(c.pleural_clearance?.value < 10) ? '#e11d48' : '#0f172a'};">${c.pleural_clearance?.value ?? '--'} mm</td>
              <td style="padding: 4px 6px; border: 1px solid #cbd5e1; font-weight: 600;">${c.rigid_accessible_stone_percent?.value ?? '--'}%</td>
              <td style="padding: 4px 6px; border: 1px solid #cbd5e1; font-size: 9.5px; color: #475569;">${c.clinical_tradeoff_summary}</td>
            `;
            tbody.appendChild(tr);
          });
        }
      } catch (err) {
        console.warn('Could not populate summary card matrix table:', err);
      }

      // 4. Section 3: Keyframe CT Previews & Calculus Burden Profile
      const axialImg = document.getElementById('card-axial-img');
      const coronalImg = document.getElementById('card-coronal-img');
      const axialSlice = (typeof mprViewer !== 'undefined' && mprViewer) ? mprViewer.currentSliceIndex : 40;
      const coronalSlice = (typeof mprViewer !== 'undefined' && mprViewer?.maxSlices?.CORONAL) ? Math.floor(mprViewer.maxSlices.CORONAL / 2) : 48;
      const ww = (typeof mprViewer !== 'undefined' && mprViewer) ? mprViewer.windowWidth : 400;
      const wl = (typeof mprViewer !== 'undefined' && mprViewer) ? mprViewer.windowLevel : 40;
      
      const ts = Date.now();
      axialImg.onerror = () => {
        axialImg.onerror = null;
        axialImg.src = `/api/cases/${currentCaseId}/mpr/slice?orientation=AXIAL&slice_index=${axialSlice}&window_width=${ww}&window_level=${wl}`;
      };
      coronalImg.onerror = () => {
        coronalImg.onerror = null;
        coronalImg.src = `/api/cases/${currentCaseId}/mpr/slice?orientation=CORONAL&slice_index=${coronalSlice}&window_width=${ww}&window_level=${wl}`;
      };
      axialImg.src = `/api/cases/${currentCaseId}/keyframes/axial_keyframe.png?t=${ts}`;
      coronalImg.src = `/api/cases/${currentCaseId}/keyframes/coronal_keyframe.png?t=${ts}`;

      document.getElementById('card-stone-volume').textContent = document.getElementById('info-stone-vol')?.textContent || '-- mm³';
      document.getElementById('card-stone-feret').textContent = document.getElementById('info-stone-feret')?.textContent || '-- mm';
      document.getElementById('card-stone-hu').textContent = document.getElementById('info-stone-hu')?.textContent || '-- HU';
      document.getElementById('card-guys-grade').textContent = document.getElementById('info-guys-grade')?.textContent || '--';

      document.getElementById('card-carm-be').textContent = document.getElementById('vp-be-angles')?.textContent || '--';
      document.getElementById('card-carm-dv').textContent = document.getElementById('vp-dv-angles')?.textContent || '--';
    }

    function printSummaryCard() {
      window.print();
    }

    // =========================================================================
    // Milestone M14.5 / Horizon 2: Formative Usability Pilot Walkthrough Logic
    // =========================================================================
    const SUS_QUESTIONS = [
      "1. I think that I would like to use this system frequently.",
      "2. I found the system unnecessarily complex.",
      "3. I thought the system was easy to use.",
      "4. I think that I would need the support of a technical person to be able to use this system.",
      "5. I found the various functions in this system were well integrated.",
      "6. I thought there was too much inconsistency in this system.",
      "7. I would imagine that most people would learn to use this system very quickly.",
      "8. I found the system very cumbersome to use.",
      "9. I felt very confident using the system.",
      "10. I needed to learn a lot of things before I could get going with this system."
    ];
    const DEFAULT_SUS_RESPONSES = [5, 1, 5, 2, 5, 1, 5, 1, 5, 2];

    let studyTimerInterval = null;
    let studyTimerStartTime = null;
    let studyTimerElapsed = 0;
    let taskStartTimeIso = null;
    let taskEndTimeIso = null;
    let currentReportJson = null;

    function initSusItems() {
      const container = document.getElementById('study-sus-items-container');
      if (!container || container.children.length > 0) return;
      SUS_QUESTIONS.forEach((q, idx) => {
        const defVal = DEFAULT_SUS_RESPONSES[idx];
        const row = document.createElement('div');
        row.style.cssText = 'padding: 4px 6px; background: #0b0e14; border-radius: 4px; border: 1px solid #1e293b; display: flex; justify-content: space-between; align-items: center;';
        
        let radios = '';
        for (let r = 1; r <= 5; r++) {
          radios += `
            <label style="margin-left: 6px; font-size: 10px; cursor: pointer; color: ${r === defVal ? '#c084fc' : '#94a3b8'};">
              <input type="radio" name="sus-q-${idx}" value="${r}" ${r === defVal ? 'checked' : ''} onchange="updateSusScores()" style="margin-right: 2px; accent-color: #a855f7;">${r}
            </label>
          `;
        }
        row.innerHTML = `
          <span style="font-size: 10.5px; color: var(--text-primary); flex: 1; padding-right: 8px;">${q}</span>
          <div style="display: flex; align-items: center; flex-shrink: 0;">${radios}</div>
        `;
        container.appendChild(row);
      });
    }

    function updateTlxScores() {
      const m = parseFloat(document.getElementById('slider-tlx-mental')?.value || '20');
      const p = parseFloat(document.getElementById('slider-tlx-physical')?.value || '15');
      const t = parseFloat(document.getElementById('slider-tlx-temporal')?.value || '15');
      const perf = parseFloat(document.getElementById('slider-tlx-performance')?.value || '10');
      const e = parseFloat(document.getElementById('slider-tlx-effort')?.value || '25');
      const f = parseFloat(document.getElementById('slider-tlx-frustration')?.value || '20');

      if (document.getElementById('val-tlx-mental')) document.getElementById('val-tlx-mental').textContent = m;
      if (document.getElementById('val-tlx-physical')) document.getElementById('val-tlx-physical').textContent = p;
      if (document.getElementById('val-tlx-temporal')) document.getElementById('val-tlx-temporal').textContent = t;
      if (document.getElementById('val-tlx-performance')) document.getElementById('val-tlx-performance').textContent = perf;
      if (document.getElementById('val-tlx-effort')) document.getElementById('val-tlx-effort').textContent = e;
      if (document.getElementById('val-tlx-frustration')) document.getElementById('val-tlx-frustration').textContent = f;

      const rawTlx = (m + p + t + perf + e + f) / 6.0;
      const badge = document.getElementById('study-tlx-composite-badge');
      if (badge) {
        let level = 'LOW';
        if (rawTlx > 50) level = 'HIGH';
        else if (rawTlx > 30) level = 'MODERATE';
        badge.textContent = `Raw TLX: ${rawTlx.toFixed(1)} (${level})`;
      }
    }

    function updateSusScores() {
      let scoreSum = 0;
      for (let i = 0; i < 10; i++) {
        const val = parseInt(document.querySelector(`input[name="sus-q-${i}"]:checked`)?.value || '3');
        if (i % 2 === 0) {
          scoreSum += (val - 1);
        } else {
          scoreSum += (5 - val);
        }
      }
      const susScore = scoreSum * 2.5;
      let adjective = 'ACCEPTABLE';
      if (susScore >= 85) adjective = 'EXCELLENT';
      else if (susScore >= 80) adjective = 'HIGH_USABILITY';
      else if (susScore >= 68) adjective = 'ACCEPTABLE';
      else if (susScore >= 51) adjective = 'MARGINAL';
      else adjective = 'UNACCEPTABLE';

      const badge = document.getElementById('study-sus-score-badge');
      if (badge) {
        badge.textContent = `SUS: ${susScore.toFixed(1)} (${adjective})`;
      }
    }

    function startStudyTimer() {
      if (studyTimerInterval) return;
      if (!taskStartTimeIso) taskStartTimeIso = new Date().toISOString();
      studyTimerStartTime = Date.now() - studyTimerElapsed;
      studyTimerInterval = setInterval(() => {
        studyTimerElapsed = Date.now() - studyTimerStartTime;
        const totalSec = studyTimerElapsed / 1000;
        const mins = Math.floor(totalSec / 60);
        const secs = (totalSec % 60).toFixed(1);
        const disp = document.getElementById('study-timer-display');
        if (disp) {
          disp.textContent = `${String(mins).padStart(2, '0')}:${secs < 10 ? '0' : ''}${secs}`;
        }
      }, 100);
    }

    function pauseStudyTimer() {
      if (studyTimerInterval) {
        clearInterval(studyTimerInterval);
        studyTimerInterval = null;
        taskEndTimeIso = new Date().toISOString();
      }
    }

    function resetStudyTimer() {
      pauseStudyTimer();
      studyTimerElapsed = 0;
      taskStartTimeIso = null;
      taskEndTimeIso = null;
      const disp = document.getElementById('study-timer-display');
      if (disp) disp.textContent = '00:00.0';
    }

    async function loadStudySessionsList() {
      try {
        const res = await fetch('/api/usability/sessions');
        if (!res.ok) return;
        const sessions = await res.json();
        const sel = document.getElementById('study-session-select');
        if (!sel) return;
        sel.innerHTML = '';
        if (sessions.length === 0) {
          sel.innerHTML = '<option value="SESS_PILOT_M14_5">SESS_PILOT_M14_5 (Auto)</option>';
          return;
        }
        sessions.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.session_id;
          opt.textContent = `${s.session_id} (${s.trial_count} trials)`;
          sel.appendChild(opt);
        });
        onSessionSelectChange(sel.value);
      } catch (err) {
        console.warn('Could not load usability sessions:', err);
      }
    }

    async function onSessionSelectChange(sessionId) {
      if (!sessionId) return;
      try {
        const res = await fetch(`/api/usability/sessions/${sessionId}`);
        if (res.ok) {
          const data = await res.json();
          const countEl = document.getElementById('study-trials-count');
          if (countEl) countEl.textContent = data.trial_count || (data.trials ? data.trials.length : 0);
        }
      } catch (e) {
        // Fallback
      }
    }

    async function createNewStudySession() {
      const name = prompt('Enter new Usability Session ID:', `SESS_${new Date().toISOString().slice(0,10).replace(/-/g,'')}_SURGEON`);
      if (!name) return;
      try {
        const res = await fetch('/api/usability/sessions/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: name, investigator_id: 'Lead_Investigator' })
        });
        if (res.ok) {
          alert(`Created Usability Session: ${name}`);
          await loadStudySessionsList();
          document.getElementById('study-session-select').value = name;
          onSessionSelectChange(name);
        }
      } catch (err) {
        alert('Error creating session: ' + err.message);
      }
    }

    function onConditionChange(cond) {
      const isAcuc = (cond === 'ACUCALYX_WORKBENCH');
      const susPanel = document.getElementById('study-sus-panel');
      if (susPanel) {
        susPanel.style.opacity = isAcuc ? '1.0' : '0.4';
        susPanel.style.pointerEvents = isAcuc ? 'auto' : 'none';
      }
    }

    async function openUsabilityStudyModal() {
      const modal = document.getElementById('modal-usability-study');
      if (!modal) return;
      modal.style.display = 'flex';
      initSusItems();
      updateTlxScores();
      updateSusScores();
      await loadStudySessionsList();

      // Prepopulate candidate and calyx from cockpit
      if (selectedCandidateId) {
        const candInput = document.getElementById('study-cand-id');
        if (candInput) candInput.value = selectedCandidateId;
        const cand = currentCandidates.find(c => c.candidate_id === selectedCandidateId);
        if (cand && document.getElementById('study-calyx-name')) {
          document.getElementById('study-calyx-name').value = cand.target_calyx || cand.target_calyx_name || 'POSTERIOR_LOWER';
        }
      }

      // Prepopulate scenario if loaded
      if (currentCaseMeta?.scenario_id && document.getElementById('study-scenario-select')) {
        document.getElementById('study-scenario-select').value = currentCaseMeta.scenario_id;
      }
    }

    function closeUsabilityStudyModal() {
      const modal = document.getElementById('modal-usability-study');
      if (modal) modal.style.display = 'none';
    }

    async function submitStudyTrial() {
      const sessionId = document.getElementById('study-session-select')?.value || 'SESS_PILOT_M14_5';
      const participantId = document.getElementById('study-participant-id')?.value.trim() || 'SURGEON_01';
      const participantRole = document.getElementById('study-participant-role')?.value || 'ATTENDING_ENDOUROLOGIST';
      const experienceYears = parseInt(document.getElementById('study-experience-years')?.value) || 10;
      const scenarioId = document.getElementById('study-scenario-select')?.value || 'SCENARIO_01_LOWER_POLE';
      const condition = document.getElementById('study-condition-select')?.value || 'ACUCALYX_WORKBENCH';

      if (!sessionId || !participantId) {
        alert('Please specify Session ID and Participant ID.');
        return;
      }

      pauseStudyTimer();
      const durationSec = Math.max(1.0, studyTimerElapsed / 1000);
      const nowIso = new Date().toISOString();
      const startTime = taskStartTimeIso || new Date(Date.now() - studyTimerElapsed).toISOString();
      const endTime = taskEndTimeIso || nowIso;

      const candId = document.getElementById('study-cand-id')?.value.trim() || 'CAND_01';
      const calyxName = document.getElementById('study-calyx-name')?.value.trim() || 'POSTERIOR_LOWER';
      const acceptProposal = document.getElementById('study-accept-proposal')?.checked ?? true;
      const clinicianOverride = document.getElementById('study-clinician-override')?.checked ?? false;
      const overrideRationale = document.getElementById('study-override-rationale')?.value.trim();

      // Observed critical errors
      const errCheckboxes = document.querySelectorAll('.study-crit-err:checked');
      const criticalErrors = Array.from(errCheckboxes).map(cb => cb.value);

      // NASA-TLX
      const nasaTlx = {
        mental_demand: parseFloat(document.getElementById('slider-tlx-mental')?.value || '20'),
        physical_demand: parseFloat(document.getElementById('slider-tlx-physical')?.value || '15'),
        temporal_demand: parseFloat(document.getElementById('slider-tlx-temporal')?.value || '15'),
        performance: parseFloat(document.getElementById('slider-tlx-performance')?.value || '10'),
        effort: parseFloat(document.getElementById('slider-tlx-effort')?.value || '25'),
        frustration: parseFloat(document.getElementById('slider-tlx-frustration')?.value || '20')
      };

      // SUS responses (AcuCalyx condition)
      let susResponses = null;
      if (condition === 'ACUCALYX_WORKBENCH') {
        susResponses = [];
        for (let i = 0; i < 10; i++) {
          const val = parseInt(document.querySelector(`input[name="sus-q-${i}"]:checked`)?.value || '3');
          susResponses.push(val);
        }
      }

      const payload = {
        participant_id: participantId,
        participant_role: participantRole,
        experience_years: experienceYears,
        scenario_id: scenarioId,
        condition: condition,
        task_start_time: startTime,
        task_end_time: endTime,
        task_duration_seconds: durationSec,
        selected_candidate_id: candId,
        selected_calyx_name: calyxName,
        accepted_automated_proposal: acceptProposal,
        clinician_override_applied: clinicianOverride,
        override_rationale: overrideRationale || null,
        critical_errors_observed: criticalErrors,
        nasa_tlx: nasaTlx,
        sus_responses: susResponses
      };

      try {
        const res = await fetch(`/api/usability/sessions/${sessionId}/trials`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Could not record trial');
        }
        const data = await res.json();
        window.showToast(`Trial recorded: ${data.trial_id}`, 'success');
        document.getElementById('study-trials-count').textContent = data.trials_in_session;
        resetStudyTimer();
      } catch (err) {
        alert('Error submitting trial: ' + err.message);
      }
    }

    async function openUsabilityReportModal() {
      const sessionId = document.getElementById('study-session-select')?.value || 'SESS_PILOT_M14_5';
      try {
        const res = await fetch(`/api/usability/sessions/${sessionId}/report`);
        if (!res.ok) {
          const err = await res.json();
          alert(`No trials found for session '${sessionId}' yet. Please record at least one trial first.`);
          return;
        }
        const rep = await res.json();
        currentReportJson = rep;
        renderUsabilityReport(rep);
        document.getElementById('modal-usability-report').style.display = 'flex';
      } catch (err) {
        alert('Error loading report: ' + err.message);
      }
    }

    function renderUsabilityReport(rep) {
      const container = document.getElementById('usability-report-content');
      document.getElementById('rep-session-badge').textContent = `SESSION: ${rep.session_id}`;

      const timeRed = rep.task_duration_seconds?.reduction_percent ?? 0;
      const meanBase = rep.task_duration_seconds?.mean_baseline ?? 0;
      const meanAcuc = rep.task_duration_seconds?.mean_acucalyx ?? 0;

      const susScore = rep.sus_analysis ? rep.sus_analysis.mean_sus?.toFixed(1) : 'N/A';
      const susPct80 = rep.sus_analysis ? (rep.sus_analysis.proportion_meeting_80_benchmark * 100).toFixed(0) + '%' : 'N/A';

      const errElim = rep.critical_errors_observed?.error_elimination_rate_pct ?? 100;
      const acceptPct = rep.acceptance_metrics?.acceptance_rate_pct ?? 0;
      const workload = rep.workload_analysis;

      container.innerHTML = `
        <!-- Top 4 Summary Metric Cards -->
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;">
          <div style="background: #0b0e14; border: 1px solid #10b981; border-radius: 6px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Task Duration Delta</div>
            <div style="font-size: 22px; font-weight: 800; color: #10b981; margin: 4px 0;">-${timeRed}%</div>
            <div style="font-size: 10px; color: var(--text-secondary);">Baseline: ${meanBase}s → AcuCalyx: ${meanAcuc}s</div>
          </div>
          <div style="background: #0b0e14; border: 1px solid #38bdf8; border-radius: 6px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Cognitive Workload</div>
            <div style="font-size: 22px; font-weight: 800; color: #38bdf8; margin: 4px 0;">
              ${workload ? `-${Math.abs(workload.mean_difference).toFixed(1)}` : 'N/A'}
            </div>
            <div style="font-size: 10px; color: var(--text-secondary);">
              ${workload ? `p=${workload.p_value?.toFixed(3)}, d=${workload.cohens_d?.toFixed(2)}` : 'Paired TLX reduction'}
            </div>
          </div>
          <div style="background: #0b0e14; border: 1px solid #a855f7; border-radius: 6px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">System Usability (SUS)</div>
            <div style="font-size: 22px; font-weight: 800; color: #c084fc; margin: 4px 0;">${susScore}</div>
            <div style="font-size: 10px; color: var(--text-secondary);">${susPct80} ≥ 80 benchmark</div>
          </div>
          <div style="background: #0b0e14; border: 1px solid #f59e0b; border-radius: 6px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-secondary); text-transform: uppercase;">Safety & Acceptance</div>
            <div style="font-size: 22px; font-weight: 800; color: #f59e0b; margin: 4px 0;">${errElim}% / ${acceptPct}%</div>
            <div style="font-size: 10px; color: var(--text-secondary);">Error Elimination / Tract Accept</div>
          </div>
        </div>

        <!-- Trial Breakdown Details -->
        <div style="background: var(--bg-surface-elevated, #131b2e); border: 1px solid var(--border-color); border-radius: 6px; padding: 14px;">
          <div style="font-size: 12px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px;">IEC 62366-1 Formative Trial Breakdown</div>
          <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.6;">
            <div><strong>Total Evaluated Trials:</strong> ${rep.total_trials} (Baseline: ${rep.baseline_trial_count}, AcuCalyx: ${rep.acucalyx_trial_count})</div>
            <div><strong>Investigator:</strong> ${rep.investigator_id}</div>
            <div><strong>Critical Use Errors Observed:</strong> Baseline: ${rep.critical_errors_observed?.baseline_total ?? 0} | AcuCalyx: ${rep.critical_errors_observed?.acucalyx_total ?? 0}</div>
            <div><strong>Automated Proposal Acceptance:</strong> ${rep.acceptance_metrics?.accepted_count ?? 0} accepted, ${rep.acceptance_metrics?.override_count ?? 0} overrides (${acceptPct}% acceptance)</div>
          </div>
        </div>
      `;
    }

    function downloadUsabilityReportJson() {
      if (!currentReportJson) return;
      const blob = new Blob([JSON.stringify(currentReportJson, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `AcuCalyx_${currentReportJson.session_id || 'Usability'}_Report.json`;
      a.click();
      URL.revokeObjectURL(url);
    }

    async function openDiscoveryGuideModal() {
      const modal = document.getElementById('modal-discovery-guide');
      const container = document.getElementById('discovery-guide-content');
      container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-secondary);">⏳ Loading discovery protocol schema...</div>';
      modal.style.display = 'flex';
      try {
        const res = await fetch('/api/usability/discovery/interview-guide');
        if (!res.ok) throw new Error('Could not load interview guide');
        const guide = await res.json();
        renderDiscoveryGuide(guide);
      } catch (err) {
        container.innerHTML = `<div style="color: #ef4444; padding: 20px;">Error loading guide: ${err.message}</div>`;
      }
    }

    function renderDiscoveryGuide(guide) {
      const container = document.getElementById('discovery-guide-content');
      let html = `<div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 14px;">Version: <strong>${guide.version}</strong> • Objective: <strong>${guide.objective}</strong></div>`;
      (guide.sections || []).forEach(sec => {
        html += `
          <div style="background: var(--bg-surface-elevated, #131b2e); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; margin-bottom: 12px;">
            <div style="font-size: 13px; font-weight: 700; color: #a5b4fc; margin-bottom: 6px;">${sec.title}</div>
            ${sec.description ? `<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">${sec.description}</div>` : ''}
        `;
        if (sec.questions) {
          sec.questions.forEach(q => {
            html += `
              <div style="margin-top: 8px; padding-left: 8px; border-left: 2px solid #6366f1;">
                <div style="font-size: 11.5px; font-weight: 600; color: var(--text-primary);">${q.text}</div>
                <div style="font-size: 10.5px; color: var(--text-secondary); margin-top: 2px;">Options: ${q.options ? q.options.join(' • ') : 'Open response'}</div>
              </div>
            `;
          });
        }
        if (sec.dimensions) {
          sec.dimensions.forEach(d => {
            html += `
              <div style="margin-top: 8px; padding-left: 8px; border-left: 2px solid #10b981;">
                <div style="font-size: 11.5px; font-weight: 600; color: #38bdf8;">${d.label}</div>
                <div style="font-size: 10.5px; color: var(--text-secondary);">${d.description}</div>
              </div>
            `;
          });
        }
        html += `</div>`;
      });
      container.innerHTML = html;
    }

    // =========================================================================
    // Milestone M15-V / Horizon 3: CTU Multi-Reader & Validation Gate Logic
    // =========================================================================
    let currentValidationReportJson = null;

    async function openValidationGateModal() {
      const modal = document.getElementById('modal-validation-gate');
      if (!modal) return;
      modal.style.display = 'flex';
      await loadCtuCohort();
      await fetchLatestValidationReport();
    }

    function closeValidationGateModal() {
      const modal = document.getElementById('modal-validation-gate');
      if (modal) modal.style.display = 'none';
    }

    async function loadCtuCohort() {
      const tbody = document.getElementById('ctu-cohort-table-body');
      if (!tbody) return;
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 20px; color: var(--text-secondary);">⏳ Loading CTU cohort cases...</td></tr>';
      try {
        const res = await fetch('/api/validation/ctu/cohort');
        if (!res.ok) throw new Error('Could not load cohort');
        const cohort = await res.json();
        tbody.innerHTML = '';
        cohort.forEach(c => {
          const tr = document.createElement('tr');
          tr.style.cssText = 'border-bottom: 1px solid #1e293b;';
          const isNonOp = c.opacification_quality === 'NON_OPACIFIED';
          const opColor = isNonOp ? '#ef4444' : (c.opacification_quality === 'SUBOPTIMAL' ? '#f59e0b' : '#10b981');
          const diceText = c.consensus_summary ? `${(c.consensus_summary.mean_pairwise_dice * 100).toFixed(1)}%` : 'N/A';
          const ambVol = c.consensus_summary ? `${c.consensus_summary.ambiguity_volume_mm3.toFixed(1)} mm³` : 'N/A';
          const calyxCount = c.consensus_summary ? `${c.consensus_summary.calyx_count} calyces` : '--';
          const statusBadge = isNonOp 
            ? '<span class="state-badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 10px;">REJECTED_NON_OP</span>'
            : '<span class="state-badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 10px;">EVALUABLE</span>';

          const tdCase = document.createElement('td');
          tdCase.style.cssText = 'padding: 8px; font-weight: 700; color: var(--text-primary);';
          tdCase.textContent = c.case_id;
          tr.appendChild(tdCase);

          const tdOp = document.createElement('td');
          tdOp.style.cssText = `padding: 8px; color: ${opColor}; font-weight: 600;`;
          tdOp.textContent = c.opacification_quality;
          tr.appendChild(tdOp);

          const tdReaders = document.createElement('td');
          tdReaders.style.padding = '8px';
          tdReaders.textContent = `${c.reader_count} readers`;
          tr.appendChild(tdReaders);

          const tdDice = document.createElement('td');
          tdDice.style.cssText = 'padding: 8px; font-weight: 600;';
          tdDice.textContent = diceText;
          tr.appendChild(tdDice);

          const tdAmb = document.createElement('td');
          tdAmb.style.cssText = 'padding: 8px; color: #fbbf24;';
          tdAmb.textContent = ambVol;
          tr.appendChild(tdAmb);

          const tdCalyx = document.createElement('td');
          tdCalyx.style.padding = '8px';
          tdCalyx.textContent = calyxCount;
          tr.appendChild(tdCalyx);

          const tdStatus = document.createElement('td');
          tdStatus.style.padding = '8px';
          const badgeSpan = document.createElement('span');
          badgeSpan.className = 'state-badge';
          if (isNonOp) {
            badgeSpan.style.cssText = 'background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 10px;';
            badgeSpan.textContent = 'REJECTED_NON_OP';
          } else {
            badgeSpan.style.cssText = 'background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 10px;';
            badgeSpan.textContent = 'EVALUABLE';
          }
          tdStatus.appendChild(badgeSpan);
          tr.appendChild(tdStatus);

          const tdAction = document.createElement('td');
          tdAction.style.cssText = 'padding: 8px; text-align: right;';
          const btn = document.createElement('button');
          btn.className = 'btn btn-sm';
          btn.style.cssText = 'padding: 2px 8px; font-size: 10.5px;';
          btn.textContent = 'Inspect';
          const currentCaseId = c.case_id;
          btn.addEventListener('click', () => inspectCtuCase(currentCaseId));
          tdAction.appendChild(btn);
          tr.appendChild(tdAction);

          tbody.appendChild(tr);
        });
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" style="color: #ef4444; padding: 14px;">Error: ${err.message}</td></tr>`;
      }
    }

    async function inspectCtuCase(caseId) {
      const panel = document.getElementById('ctu-drilldown-panel');
      const title = document.getElementById('drilldown-case-id');
      const content = document.getElementById('drilldown-content');
      title.textContent = caseId;
      content.innerHTML = '⏳ Loading multi-reader consensus and landmark dispersion metrics...';
      panel.style.display = 'block';

      try {
        const res = await fetch(`/api/validation/ctu/cohort/${caseId}`);
        if (!res.ok) throw new Error('Case not found');
        const data = await res.json();
        
        let readersHtml = '<div style="margin-bottom: 10px;"><strong>Expert Readers:</strong> ';
        (data.readers || []).forEach(r => {
          readersHtml += `<span class="version-pill" style="margin-right: 6px; font-size: 10px;">${r.reader_id} (${r.experience_years}y exp, conf: ${r.confidence_score})</span>`;
        });
        readersHtml += '</div>';

        let calyxTable = '';
        if (data.consensus && data.consensus.calyx_consensus) {
          calyxTable = `
            <div style="font-weight: 700; color: #38bdf8; margin: 8px 0 4px 0;">Calyx Landmark Consensus & Spatial Dispersion:</div>
            <table style="width: 100%; border-collapse: collapse; font-size: 10.5px; border: 1px solid #1e293b;">
              <tr style="background: #1e293b; color: #94a3b8;">
                <th style="padding: 4px 6px;">Calyx Target</th>
                <th style="padding: 4px 6px;">Concordance</th>
                <th style="padding: 4px 6px;">Consensus Centroid [L, P, S]</th>
                <th style="padding: 4px 6px;">Dispersion Radius (≤5mm)</th>
                <th style="padding: 4px 6px;">Status</th>
              </tr>
          `;
          for (const [cName, cMet] of Object.entries(data.consensus.calyx_consensus)) {
            const isWarn = cMet.is_high_disagreement;
            calyxTable += `
              <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 4px 6px; font-weight: 600;">${cName}</td>
                <td style="padding: 4px 6px;">${(cMet.concordance_fraction * 100).toFixed(0)}% (${cMet.num_readers} readers)</td>
                <td style="padding: 4px 6px; font-family: var(--font-mono);">${cMet.consensus_centroid_lps.join(', ')}</td>
                <td style="padding: 4px 6px; color: ${isWarn ? '#ef4444' : '#10b981'}; font-weight: 700;">${cMet.dispersion_radius_mm} mm</td>
                <td style="padding: 4px 6px;">${isWarn ? 'HIGH DISPERSION' : 'CONCORDANT'}</td>
              </tr>
            `;
          }
          calyxTable += '</table>';
        }

        let infundibulumHtml = '';
        if (data.consensus && data.consensus.infundibular_diameters_consensus) {
          infundibulumHtml = '<div style="margin-top: 8px;"><strong>Consensus Infundibulum Calipers:</strong> ';
          for (const [cName, stats] of Object.entries(data.consensus.infundibular_diameters_consensus)) {
            infundibulumHtml += `<span style="margin-right: 12px; color: #cbd5e1;">${cName}: <strong>${stats.mean_mm} ± ${stats.std_mm} mm</strong></span>`;
          }
          infundibulumHtml += '</div>';
        }

        content.innerHTML = readersHtml + calyxTable + infundibulumHtml;
      } catch (err) {
        content.innerHTML = `<span style="color: #ef4444;">Error inspecting case: ${err.message}</span>`;
      }
    }

    async function fetchLatestValidationReport() {
      try {
        const res = await fetch('/api/validation/ctu/benchmark/report');
        if (!res.ok) return;
        const rep = await res.json();
        currentValidationReportJson = rep;
        renderValidationReport(rep);
      } catch (err) {
        console.warn('Could not fetch validation report:', err);
      }
    }

    async function runValidationBenchmark() {
      try {
        const res = await fetch('/api/validation/ctu/benchmark/run?calyx_tolerance_mm=4.0&centerline_mae_threshold_mm=1.2', {
          method: 'POST'
        });
        if (!res.ok) throw new Error('Benchmark run failed');
        const rep = await res.json();
        currentValidationReportJson = rep;
        renderValidationReport(rep);
        window.showToast(`M15-V Benchmark Completed: ${rep.executive_decision}`, 'success');
        await loadCtuCohort();
      } catch (err) {
        alert('Benchmark execution error: ' + err.message);
      }
    }

    function renderValidationReport(rep) {
      const badge = document.getElementById('gate-decision-badge');
      const summary = document.getElementById('gate-summary-text');
      const sens = document.getElementById('gate-calyx-sens');
      const mae = document.getElementById('gate-centerline-mae');
      const h95 = document.getElementById('gate-centerline-h95');
      const rej = document.getElementById('gate-rejected-cases');

      if (badge) {
        badge.textContent = rep.executive_decision;
        badge.style.background = rep.all_cases_passed ? '#10b981' : '#ef4444';
      }
      if (summary) summary.textContent = rep.summary_findings;
      if (sens) sens.textContent = `${(rep.mean_calyx_sensitivity * 100).toFixed(1)}%`;
      if (mae) mae.textContent = `${rep.mean_centerline_mae_mm.toFixed(2)} mm`;
      if (h95) h95.textContent = `${rep.mean_centerline_h95_mm.toFixed(2)} mm`;
      if (rej) rej.textContent = `${rep.rejected_non_opacified_cases} Gated`;
    }

    function downloadValidationReportJson() {
      if (!currentValidationReportJson) return;
      const blob = new Blob([JSON.stringify(currentValidationReportJson, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `AcuCalyx_M15_Validation_Gate_Report.json`;
      a.click();
      URL.revokeObjectURL(url);
    }

    function toggleIngestDrawer() {
      const body = document.getElementById('ingest-drawer-body');
      const icon = document.getElementById('ingest-drawer-icon');
      if (body) {
        const isHidden = body.style.display === 'none';
        body.style.display = isHidden ? 'block' : 'none';
        if (icon) icon.textContent = isHidden ? '▲' : '▼';
      }
    }

    async function submitCtuIngest() {
      const caseId = document.getElementById('ingest-case-id')?.value.trim();
      const seriesUid = document.getElementById('ingest-series-uid')?.value.trim();
      const opQuality = document.getElementById('ingest-opacification')?.value;
      const scanner = document.getElementById('ingest-scanner')?.value.trim();

      if (!caseId || !seriesUid) {
        alert('Please specify Case ID and Series UID.');
        return;
      }

      try {
        const res = await fetch('/api/validation/ctu/ingest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_id: caseId,
            dicom_series_uid: seriesUid,
            opacification_quality: opQuality,
            scanner_model: scanner
          })
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Ingest failed');
        }
        const data = await res.json();
        window.showToast(`CTU Case Ingested: ${data.case_id} (${data.status})`, 'success');
        await loadCtuCohort();
        toggleIngestDrawer();
      } catch (err) {
        alert('Ingest error: ' + err.message);
      }
    }

    window.openComparisonMatrix = openComparisonMatrix;
    window.selectTractFromMatrix = selectTractFromMatrix;
    window.renderComparisonMatrix = renderComparisonMatrix;
    window.openSummaryCard = openSummaryCard;
    window.printSummaryCard = printSummaryCard;
    window.openUsabilityStudyModal = openUsabilityStudyModal;
    window.closeUsabilityStudyModal = closeUsabilityStudyModal;
    window.startStudyTimer = startStudyTimer;
    window.pauseStudyTimer = pauseStudyTimer;
    window.resetStudyTimer = resetStudyTimer;
    window.updateTlxScores = updateTlxScores;
    window.updateSusScores = updateSusScores;
    window.submitStudyTrial = submitStudyTrial;
    window.openUsabilityReportModal = openUsabilityReportModal;
    window.openDiscoveryGuideModal = openDiscoveryGuideModal;
    window.downloadUsabilityReportJson = downloadUsabilityReportJson;
    window.onConditionChange = onConditionChange;
    window.onSessionSelectChange = onSessionSelectChange;
    window.createNewStudySession = createNewStudySession;
    window.openValidationGateModal = openValidationGateModal;
    window.closeValidationGateModal = closeValidationGateModal;
    window.loadCtuCohort = loadCtuCohort;
    window.inspectCtuCase = inspectCtuCase;
    window.runValidationBenchmark = runValidationBenchmark;
    window.downloadValidationReportJson = downloadValidationReportJson;
    window.toggleIngestDrawer = toggleIngestDrawer;
    window.submitCtuIngest = submitCtuIngest;

    // Interactive Viewport, Navigation, & Subsystem Window Exports
    window.switchKeyframeTab = switchKeyframeTab;
    window.openKeyframeLightbox = openKeyframeLightbox;
    window.openPdfModal = openPdfModal;
    window.switchRehearsalTab = switchRehearsalTab;
    window.submitPositionConfirmation = submitPositionConfirmation;
    window.switchEndoTab = switchEndoTab;
    window.loadEndoscopyData = loadEndoscopyData;
    window.loadSelectedScenario = loadSelectedScenario;
    window.updateUltrasoundViews = updateUltrasoundViews;
    window.updatePoseTransformPreview = updatePoseTransformPreview;
    window.onEndoSliderChange = onEndoSliderChange;

    // Core Workflow Exports for Multi-View Routing and Workstation Synchronization
    window.cockpitSelectCase = selectCase;
    window.loadCaseArtifacts = loadCaseArtifacts;
    window.runPlanning = runPlanning;
    window.downloadPDF = downloadPDF;


    let scalpelDrawActive = false;
    let isDrawingStroke = false;
    let strokeStart = { x: 0, y: 0 };
    let strokeCurrent = { x: 0, y: 0 };

    function initScalpelDrawOverlay() {
      const canvas = document.getElementById('scalpel-draw-overlay');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');

      function resizeOverlay() {
        const container = document.getElementById('three-container');
        if (!container) return;
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
      }
      window.addEventListener('resize', resizeOverlay);
      resizeOverlay();

      canvas.addEventListener('pointerdown', (e) => {
        if (!scalpelDrawActive) return;
        isDrawingStroke = true;
        const rect = canvas.getBoundingClientRect();
        strokeStart = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        strokeCurrent = { ...strokeStart };
        if (viewer3d && viewer3d.controls) {
          viewer3d.controls.enabled = false;
        }
        canvas.setPointerCapture(e.pointerId);
      });

      canvas.addEventListener('pointermove', (e) => {
        if (!isDrawingStroke) return;
        const rect = canvas.getBoundingClientRect();
        strokeCurrent = { x: e.clientX - rect.left, y: e.clientY - rect.top };

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const dx = strokeCurrent.x - strokeStart.x;
        const dy = strokeCurrent.y - strokeStart.y;
        const dist = Math.hypot(dx, dy);
        const angleDeg = Math.round((Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360);

        // 1. Neon Outer Glow
        ctx.beginPath();
        ctx.moveTo(strokeStart.x, strokeStart.y);
        ctx.lineTo(strokeCurrent.x, strokeCurrent.y);
        ctx.strokeStyle = 'rgba(0, 210, 255, 0.4)';
        ctx.lineWidth = 8;
        ctx.lineCap = 'round';
        ctx.stroke();

        // 2. Core Scalpel Cut Line
        ctx.beginPath();
        ctx.moveTo(strokeStart.x, strokeStart.y);
        ctx.lineTo(strokeCurrent.x, strokeCurrent.y);
        ctx.strokeStyle = '#ec4899';
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // 3. Start Anchor Bead
        ctx.beginPath();
        ctx.arc(strokeStart.x, strokeStart.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#00d2ff';
        ctx.fill();

        // 4. Scalpel Tip
        ctx.beginPath();
        ctx.arc(strokeCurrent.x, strokeCurrent.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#ec4899';
        ctx.lineWidth = 2;
        ctx.fill();
        ctx.stroke();

        // 5. Floating Real-Time Angle / Length HUD
        if (dist > 20) {
          const mx = (strokeStart.x + strokeCurrent.x) / 2;
          const my = (strokeStart.y + strokeCurrent.y) / 2 - 14;
          const text = `Incision: ${angleDeg}° (${Math.round(dist)}px)`;
          ctx.font = 'bold 11px system-ui, sans-serif';
          const tw = ctx.measureText(text).width;
          ctx.fillStyle = 'rgba(10, 15, 26, 0.9)';
          ctx.strokeStyle = '#00d2ff';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(mx - tw / 2 - 6, my - 12, tw + 12, 18, 4);
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = '#00d2ff';
          ctx.fillText(text, mx - tw / 2, my + 1);
        }
      });

      const finishStroke = (e) => {
        if (!isDrawingStroke) return;
        isDrawingStroke = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (viewer3d && viewer3d.controls) {
          viewer3d.controls.enabled = true;
        }
        try {
          canvas.releasePointerCapture(e.pointerId);
        } catch (err) {}

        const dx = strokeCurrent.x - strokeStart.x;
        const dy = strokeCurrent.y - strokeStart.y;
        const dist = Math.hypot(dx, dy);

        if (dist >= 15 && viewer3d) {
          const rect = canvas.getBoundingClientRect();
          viewer3d.sliceFromScreenStroke(
            strokeStart.x + rect.left,
            strokeStart.y + rect.top,
            strokeCurrent.x + rect.left,
            strokeCurrent.y + rect.top
          );

          const hud = document.getElementById('scalpel-hud-guide');
          if (hud) {
            hud.textContent = '✓ Resection Angle Applied!';
            hud.style.borderColor = '#00e5a3';
            hud.style.color = '#00e5a3';
            setTimeout(() => {
              hud.style.display = 'none';
              hud.textContent = '✏️ Draw cut line across kidney with finger, stylus, or mouse';
              hud.style.borderColor = '#00d2ff';
              hud.style.color = '#00d2ff';
            }, 1400);
          }
        }

        toggleScalpelDrawMode(false);
      };

      canvas.addEventListener('pointerup', finishStroke);
      canvas.addEventListener('pointercancel', finishStroke);
    }

    function toggleCameraDropdown(e) {
      if (e) e.stopPropagation();
      const menu = document.getElementById('menu-camera-views');
      if (!menu) return;
      const isClosed = (menu.style.display === 'none' || menu.style.display === '');
      menu.style.display = isClosed ? 'flex' : 'none';
    }

    function selectCameraPreset(preset, label) {
      if (viewer3d) {
        if (preset === 'stone') {
          viewer3d.focusOnStone(false);
        } else {
          viewer3d.setCameraView(preset);
        }
      }
      const labelSpan = document.getElementById('current-camera-view-label');
      if (labelSpan && label) {
        labelSpan.textContent = label;
      }
      document.querySelectorAll('#menu-camera-views .dropdown-item').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.includes(label));
      });
      const menu = document.getElementById('menu-camera-views');
      if (menu) menu.style.display = 'none';
    }

    function onSlicePresetSelect(value) {
      if (value === 'stone') {
        sliceThroughTargetStone();
      } else if (value !== 'custom') {
        applySlicePreset(value);
      }
    }

    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
      const dropdown = document.getElementById('dropdown-camera-views');
      const menu = document.getElementById('menu-camera-views');
      if (menu && dropdown && !dropdown.contains(e.target)) {
        menu.style.display = 'none';
      }
    });

    function toggleScalpelDrawMode(forceState) {
      scalpelDrawActive = (forceState !== undefined) ? !!forceState : !scalpelDrawActive;
      const canvas = document.getElementById('scalpel-draw-overlay');
      const hud = document.getElementById('scalpel-hud-guide');
      const btn = document.getElementById('btn-scalpel-draw-mode');

      if (canvas) {
        canvas.style.display = scalpelDrawActive ? 'block' : 'none';
      }
      if (hud) {
        hud.style.display = scalpelDrawActive ? 'block' : 'none';
      }
      if (btn) {
        btn.classList.toggle('active', scalpelDrawActive);
      }
    }

    function setSlicingMode(mode) {
      if (!viewer3d) return;
      viewer3d.setSlicingParameters({ mode, enabled: true });
    }

    function setPartingSeparation(mm) {
      if (!viewer3d) return;
      viewer3d.setSlicingParameters({ separationMm: mm, mode: 'bivalve', enabled: true });
    }

    function stepSliceYaw(delta) {
      if (!viewer3d) return;
      const current = (viewer3d.slicingState && viewer3d.slicingState.angleYaw !== undefined) ? viewer3d.slicingState.angleYaw : 0;
      const nextYaw = (current + delta + 360) % 360;
      viewer3d.setSlicingParameters({ angleYaw: nextYaw, enabled: true });
    }

    function stepSlicePitch(delta) {
      if (!viewer3d) return;
      const current = (viewer3d.slicingState && viewer3d.slicingState.anglePitch !== undefined) ? viewer3d.slicingState.anglePitch : 0;
      const nextPitch = Math.max(-90, Math.min(90, current + delta));
      viewer3d.setSlicingParameters({ anglePitch: nextPitch, enabled: true });
    }

    function setSliceOffset(offsetMm) {
      if (!viewer3d) return;
      viewer3d.setSlicingParameters({ offsetMm, enabled: true });
    }

    function applySlicePreset(preset) {
      if (!viewer3d) return;
      document.querySelectorAll('.slice-preset-btn').forEach(b => b.classList.remove('active'));

      let params = { enabled: true };
      if (preset === 'brodel') {
        params = { enabled: true, mode: 'bivalve', angleYaw: 30, anglePitch: 0, offsetMm: 0, separationMm: 25 };
        const btn = document.getElementById('btn-preset-brodel');
        if (btn) btn.classList.add('active');
      } else if (preset === 'coronal') {
        params = { enabled: true, mode: 'bivalve', angleYaw: 0, anglePitch: 0, offsetMm: 0, separationMm: 25 };
        const btn = document.getElementById('btn-plane-coronal');
        if (btn) btn.classList.add('active');
      } else if (preset === 'axial') {
        params = { enabled: true, mode: 'bivalve', angleYaw: 0, anglePitch: 90, offsetMm: 0, separationMm: 25 };
        const btn = document.getElementById('btn-plane-axial');
        if (btn) btn.classList.add('active');
      } else if (preset === 'sagittal') {
        params = { enabled: true, mode: 'bivalve', angleYaw: 90, anglePitch: 0, offsetMm: 0, separationMm: 25 };
        const btn = document.getElementById('btn-plane-sagittal');
        if (btn) btn.classList.add('active');
      }
      viewer3d.setSlicingParameters(params);
    }

    function sliceThroughTargetStone() {
      if (!viewer3d) return;
      viewer3d.sliceThroughStone();
      if (viewer3d.slicingState && viewer3d.slicingState.separationMm === 0) {
        viewer3d.setSlicingParameters({ separationMm: 25, mode: 'bivalve' });
      }
    }

    function toggleSliceInvert() {
      if (!viewer3d) return;
      const currentInverted = viewer3d.slicingState ? !!viewer3d.slicingState.inverted : false;
      viewer3d.setSlicingParameters({ inverted: !currentInverted });
      const btn = document.getElementById('btn-slice-invert');
      if (btn) {
        btn.classList.toggle('highlight', !currentInverted);
      }
    }

    function toggleSlicingToolbar(forceState) {
      const bar = document.getElementById('slicing-control-bar');
      if (!bar) return;
      const isHidden = (bar.style.display === 'none' || bar.style.display === '');
      const shouldShow = (forceState !== undefined) ? !!forceState : isHidden;
      bar.style.display = shouldShow ? 'flex' : 'none';
      const toggleBtn = document.getElementById('btn-toggle-slicing');
      if (toggleBtn) {
        toggleBtn.style.background = shouldShow ? 'rgba(236, 72, 153, 0.25)' : 'transparent';
        toggleBtn.style.borderColor = shouldShow ? '#ec4899' : 'rgba(236, 72, 153, 0.4)';
      }
      if (shouldShow && viewer3d && (!viewer3d.slicingState || !viewer3d.slicingState.enabled)) {
        viewer3d.setSlicingParameters({ enabled: true });
      }
    }

    // Auto-sync UI controls when 3D slicing state changes
    window.addEventListener('acucalyx:slicingStateChanged', (e) => {
      const s = e.detail;
      if (!s) return;

      const toggle = document.getElementById('slice-enable-toggle');
      if (toggle) toggle.checked = s.enabled;

      const bivalveBtn = document.getElementById('btn-mode-bivalve');
      const cutawayBtn = document.getElementById('btn-mode-cutaway');
      const partingRow = document.getElementById('row-parting-gap');
      if (bivalveBtn) bivalveBtn.classList.toggle('active', s.mode === 'bivalve');
      if (cutawayBtn) cutawayBtn.classList.toggle('active', s.mode === 'cutaway');
      if (partingRow) partingRow.style.display = (s.mode === 'bivalve') ? 'flex' : 'none';

      const sepSlider = document.getElementById('slice-separation-slider');
      const sepVal = document.getElementById('slice-separation-val');
      if (sepSlider) sepSlider.value = s.separationMm || 0;
      if (sepVal) sepVal.textContent = `${Math.round(s.separationMm || 0)} mm`;

      const yawSlider = document.getElementById('slice-yaw-slider');
      const yawVal = document.getElementById('slice-yaw-val');
      if (yawSlider) yawSlider.value = s.angleYaw || 0;
      if (yawVal) yawVal.textContent = `${Math.round(s.angleYaw || 0)}°`;

      const pitchSlider = document.getElementById('slice-pitch-slider');
      const pitchVal = document.getElementById('slice-pitch-val');
      if (pitchSlider) pitchSlider.value = s.anglePitch || 0;
      if (pitchVal) pitchVal.textContent = `${s.anglePitch >= 0 ? '+' : ''}${Math.round(s.anglePitch || 0)}°`;

      const depthSlider = document.getElementById('slice-depth-slider');
      const depthVal = document.getElementById('slice-depth-val');
      if (depthSlider) depthSlider.value = s.offsetMm || 0;
      if (depthVal) depthVal.textContent = `${s.offsetMm >= 0 ? '+' : ''}${Math.round(s.offsetMm || 0)} mm`;

      const gizmoToggle = document.getElementById('slice-gizmo-toggle');
      if (gizmoToggle) gizmoToggle.checked = !!s.showGizmo;
    });

    // Virtual Scalpel & Resection Exports
    window.toggleCameraDropdown = toggleCameraDropdown;
    window.selectCameraPreset = selectCameraPreset;
    window.onSlicePresetSelect = onSlicePresetSelect;
    window.setSlicingMode = setSlicingMode;
    window.setPartingSeparation = setPartingSeparation;
    window.stepSliceYaw = stepSliceYaw;
    window.stepSlicePitch = stepSlicePitch;
    window.setSliceOffset = setSliceOffset;
    window.applySlicePreset = applySlicePreset;
    window.sliceThroughTargetStone = sliceThroughTargetStone;
    window.toggleScalpelDrawMode = toggleScalpelDrawMode;
    window.toggleSliceInvert = toggleSliceInvert;
    window.toggleSlicingToolbar = toggleSlicingToolbar;

    // Backward Compatibility aliases
    window.setSlicePlane = applySlicePreset;
    window.revealStoneCutaway = sliceThroughTargetStone;
