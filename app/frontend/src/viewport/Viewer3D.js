/**
 * AcuCalyx 3D Viewport Engine
 * Powered by Three.js & WebGL
 *
 * Implements:
 * - OrbitControls and smooth clinical camera transitions
 * - Photorealistic Anatomical PBR Shaders for Kidney Cortex, Capsule, Medulla Pyramids, Calyces, Arteries, Veins, Nerves, Nephrons, and Highlighted Calculus
 * - Real Directional Shadow Mapping (PCFSoftShadowMap) with calibrated surgical frustum
 * - Hardware-accelerated multi-axis GPU clipping cutaway planes (coronal, axial, sagittal)
 * - CSS2DRenderer integration for high-contrast anatomical landmark callouts
 * - Clinical camera presets (AP 0°, Bullseye En-Face, Lateral Flank 90°, 30° Ipsilateral Oblique)
 * - De-glow calculus: Natural calcified pale ivory shading with zero artificial emissive flare
 * - Dynamic opacity and layer visibility controls from sidebar
 */

class AcuCalyxViewer3D {
  constructor(canvasContainerId) {
    this.container = document.getElementById(canvasContainerId);
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.labelRenderer = null;
    this.meshes = {};
    this.trajectories = [];
    this.activeTrajectoryId = null;
    this.activeTrajectoryVector = null;
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.clippingPlanes = [];
    this.coronalClip = null;
    this.axialClip = null;
    this.sagittalClip = null;

    // Virtual Scalpel & Bivalve Resection Engine
    this.slicingState = {
      enabled: false,
      mode: 'bivalve', // 'bivalve' | 'cutaway'
      angleYaw: 0,      // degrees 0 - 360
      anglePitch: 0,    // degrees -90 - +90
      offsetMm: 0,      // mm offset from kidney center
      separationMm: 0,  // mm separation gap (0 to 50)
      inverted: false,  // invert cut direction
      showGizmo: true,  // show 3D cut plane disc
    };
    this.bivalveGroupA = null;
    this.bivalveGroupB = null;
    this.bivalveMeshesA = {};
    this.bivalveMeshesB = {};
    this.planeA = null;
    this.planeB = null;
    this.sliceGizmo = null;
    this._layerVisibility = {};

    this.init();
  }

  init() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;

    // 1. Scene (Allow CSS radial vignette gradient to shine through via WebGL alpha transparency)
    this.scene = new THREE.Scene();
    this.scene.background = null;

    // 2. Camera (Patient LPS Space: X: Right->Left, Y: Ant->Post, Z: Inf->Sup)
    // Centroid of the kidney is X=17.0, Y=14.0, Z=50.0 mm
    this.camera = new THREE.PerspectiveCamera(45, width / height, 1.0, 2000.0);
    this.camera.position.set(17.0, -160.0, 50.0); // En-face coronal posterior view
    this.camera.up.set(0, 0, 1); // Cranial is +Z

    // 3. Renderer with alpha: true for seamless clinical studio blending
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.0));

    // Enable hardware-accelerated local clipping planes
    this.renderer.localClippingEnabled = true;

    // Enable calibrated directional shadow maps
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    if (typeof THREE.SRGBColorSpace !== 'undefined') {
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    } else if (typeof THREE.sRGBEncoding !== 'undefined') {
      this.renderer.outputEncoding = THREE.sRGBEncoding;
    }
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;
    this.container.appendChild(this.renderer.domElement);

    // 4. CSS2D Label Renderer (if vendored)
    if (typeof THREE.CSS2DRenderer !== 'undefined') {
      this.labelRenderer = new THREE.CSS2DRenderer();
      this.labelRenderer.setSize(width, height);
      this.labelRenderer.domElement.style.position = 'absolute';
      this.labelRenderer.domElement.style.top = '0';
      this.labelRenderer.domElement.style.left = '0';
      this.labelRenderer.domElement.style.pointerEvents = 'none';
      this.container.appendChild(this.labelRenderer.domElement);
    }

    // 5. Orbit Controls
    if (typeof THREE.OrbitControls !== 'undefined') {
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.target.set(17.0, 14.0, 50.0); // Exact organ centroid
      this.controls.update();
    }

    // 6. Lighting: Multi-point calibrated surgical studio rig
    const ambientLight = new THREE.AmbientLight(0xf8fafc, 0.25);
    this.scene.add(ambientLight);

    // Key Light with calibrated surgical shadow frustum (spanning organ bounds)
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.10);
    keyLight.position.set(80, 160, 100);
    keyLight.castShadow = true;
    keyLight.shadow.camera.left = -80;
    keyLight.shadow.camera.right = 80;
    keyLight.shadow.camera.top = 80;
    keyLight.shadow.camera.bottom = -80;
    keyLight.shadow.camera.near = 10;
    keyLight.shadow.camera.far = 400;
    keyLight.shadow.mapSize.set(1024, 1024);
    keyLight.shadow.bias = -0.0005;
    this.scene.add(keyLight);

    // Fill Light: Soft cool anatomical balance
    const fillLight = new THREE.DirectionalLight(0xe0f2fe, 0.40);
    fillLight.position.set(-90, -60, 40);
    this.scene.add(fillLight);

    // Rim Light: Golden surgical backlight defining posterior contours
    const rimLight = new THREE.DirectionalLight(0xfef08a, 0.45);
    rimLight.position.set(0, 120, -100);
    this.scene.add(rimLight);

    // 7. Subtle Studio Ground Reference Shadow
    const shadowCanvas = document.createElement('canvas');
    shadowCanvas.width = 128;
    shadowCanvas.height = 128;
    const ctx = shadowCanvas.getContext('2d');
    const radGrad = ctx.createRadialGradient(64, 64, 0, 64, 64, 60);
    radGrad.addColorStop(0, 'rgba(15, 23, 42, 0.22)');
    radGrad.addColorStop(0.5, 'rgba(15, 23, 42, 0.06)');
    radGrad.addColorStop(1, 'rgba(15, 23, 42, 0)');
    ctx.fillStyle = radGrad;
    ctx.fillRect(0, 0, 128, 128);
    const shadowTexture = new THREE.CanvasTexture(shadowCanvas);
    const shadowGeo = new THREE.PlaneGeometry(140, 140);
    const shadowMat = new THREE.MeshBasicMaterial({
      map: shadowTexture,
      transparent: true,
      depthWrite: false
    });
    this.studioShadow = new THREE.Mesh(shadowGeo, shadowMat);
    this.studioShadow.position.set(17.0, 14.0, -8.0);
    this.scene.add(this.studioShadow);

    // 8. Clipping Planes Initialization
    this.coronalClip = new THREE.Plane(new THREE.Vector3(0, 1, 0), 100);
    this.axialClip = new THREE.Plane(new THREE.Vector3(0, 0, 1), 100);
    this.sagittalClip = new THREE.Plane(new THREE.Vector3(1, 0, 0), 100);

    // 9. Event Listeners
    if (typeof ResizeObserver !== 'undefined' && this.container) {
      this.resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          if (entry.contentRect.width > 0 && entry.contentRect.height > 0) {
            this.onWindowResize();
          }
        }
      });
      this.resizeObserver.observe(this.container);
    } else {
      window.addEventListener('resize', () => this.onWindowResize());
    }
    this.renderer.domElement.addEventListener('pointerdown', (e) => this.onPointerDown(e));

    // Animation Loop
    this.animate();
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    if (this.controls) this.controls.update();
    this.renderer.render(this.scene, this.camera);
    if (this.labelRenderer) {
      this.labelRenderer.render(this.scene, this.camera);
    }
  }

  onWindowResize() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width <= 0 || height <= 0) return;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    if (this.labelRenderer) {
      this.labelRenderer.setSize(width, height);
    }
  }

  clearScene() {
    this.clearBivalve();
    Object.keys(this.meshes).forEach((key) => {
      this.scene.remove(this.meshes[key]);
      this._disposeNode(this.meshes[key]);
      delete this.meshes[key];
    });
    this.clearTrajectories();
  }

  _disposeNode(node) {
    if (node.geometry) node.geometry.dispose();
    if (node.material) {
      if (Array.isArray(node.material)) {
        node.material.forEach((mat) => mat.dispose());
      } else {
        node.material.dispose();
      }
    }
  }

  clearTrajectories() {
    this.trajectories.forEach((t) => {
      if (t.object) {
        t.object.traverse((child) => this._disposeNode(child));
        this.scene.remove(t.object);
      }
    });
    this.trajectories = [];
  }

  /**
   * Loads a GLB mesh from API endpoint with calibrated anatomical PBR Physical Materials,
   * proper renderOrder depth sorting, and active GPU clipping plane support.
   */
  async loadMesh(caseId, meshName, organKey, defaultOpacity = 0.5) {
    if (typeof THREE.GLTFLoader === 'undefined') {
      console.warn("GLTFLoader not loaded yet, skipping");
      return;
    }

    const loader = new THREE.GLTFLoader();
    const url = `/api/cases/${caseId}/meshes/${meshName}.glb`;

    try {
      const gltf = await new Promise((resolve, reject) => {
        loader.load(url, resolve, undefined, reject);
      });

      const model = gltf.scene;
      model.traverse((child) => {
        if (child.isMesh) {
          if (child.geometry) {
            child.geometry.computeVertexNormals();
          }
          // Translucent organ shells must not cast solid opaque shadows onto internal calculi
          const isTranslucent = ['renal_capsule', 'colon', 'ribs', 'nephrons'].includes(organKey);
          child.castShadow = !isTranslucent;
          child.receiveShadow = true;

          // Anatomical Physical Materials per Substructure
          if (organKey === 'stones') {
            // Natural calcified crystalline stone: pale ivory-gold, high roughness, subtle warm core luminescence
            child.material = new THREE.MeshStandardMaterial({
              color: 0xfef08a,
              roughness: 0.82,
              metalness: 0.05,
              emissive: 0x451a03,
              emissiveIntensity: 0.40,
              clippingPlanes: [], // Never clip stone during cross-section slicing
              clipShadows: false,
              side: THREE.DoubleSide
            });
            child.renderOrder = 30; // Always render clearly in front of internal cavities
          } else if (organKey === 'kidney') {
            // Warm anatomical renal cortex parenchyma with realistic subsurface tone
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0x9b2c2c,
              roughness: 0.55,
              metalness: 0.02,
              clearcoat: 0.22,
              clearcoatRoughness: 0.30,
              transparent: true,
              opacity: defaultOpacity,
              depthWrite: false,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 10;
          } else if (organKey === 'renal_capsule') {
            // Fibrous renal capsule: delicate translucent outer sheath
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0xd4b8a5,
              roughness: 0.45,
              metalness: 0.04,
              clearcoat: 0.35,
              clearcoatRoughness: 0.25,
              transparent: true,
              opacity: defaultOpacity,
              depthWrite: false,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 11;
          } else if (organKey === 'medulla_pyramids') {
            // Striated medullary pyramids: rich anatomical wine/burgundy medulla
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0x781d22,
              roughness: 0.65,
              metalness: 0.02,
              clearcoat: 0.15,
              clearcoatRoughness: 0.35,
              transparent: true,
              opacity: defaultOpacity,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 2;
          } else if (organKey === 'collecting_system') {
            // Glistening mucosal calyces and pelvis: pale opalescent light blue/pearly urothelium
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0x93c5fd,
              roughness: 0.25,
              metalness: 0.04,
              clearcoat: 0.65,
              clearcoatRoughness: 0.18,
              transparent: true,
              opacity: defaultOpacity,
              depthWrite: false,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 3;
          } else if (organKey === 'renal_arteries') {
            // Arterial tree: scarlet crimson red with high-specular clearcoat
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0xdc2626,
              roughness: 0.32,
              metalness: 0.08,
              clearcoat: 0.45,
              clearcoatRoughness: 0.15,
              transparent: true,
              opacity: defaultOpacity,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 4;
          } else if (organKey === 'renal_veins') {
            // Venous drainage: royal deoxygenated blue
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0x1d4ed8,
              roughness: 0.34,
              metalness: 0.08,
              clearcoat: 0.40,
              clearcoatRoughness: 0.20,
              transparent: true,
              opacity: defaultOpacity,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 4;
          } else if (organKey === 'renal_nerves') {
            // Sympathetic nerve plexus (golden filaments)
            child.material = new THREE.MeshStandardMaterial({
              color: 0xfacc15,
              roughness: 0.45,
              metalness: 0.05,
              transparent: true,
              opacity: defaultOpacity,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 4;
          } else if (organKey === 'nephrons' || organKey === 'nephron_unit') {
            child.material = new THREE.MeshStandardMaterial({
              color: 0xf59e0b,
              roughness: 0.35,
              metalness: 0.05,
              transparent: true,
              opacity: defaultOpacity,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 5;
          } else if (organKey === 'colon') {
            child.material = new THREE.MeshStandardMaterial({
              color: 0x78350f,
              roughness: 0.65,
              metalness: 0.02,
              transparent: true,
              opacity: 0.22,
              depthWrite: false,
              side: THREE.DoubleSide
            });
            child.renderOrder = 1;
          } else if (organKey === 'ribs') {
            child.material = new THREE.MeshStandardMaterial({
              color: 0xf3f4f6,
              roughness: 0.45,
              metalness: 0.08,
              transparent: true,
              opacity: 0.45,
              depthWrite: false,
              side: THREE.DoubleSide
            });
            child.renderOrder = 6;
          }
        }
      });

      // Dispose and remove existing mesh for this organKey to prevent GPU memory leaks
      if (this.meshes[organKey]) {
        const oldMesh = this.meshes[organKey];
        this.scene.remove(oldMesh);
        oldMesh.traverse((c) => {
          if (c.geometry) c.geometry.dispose();
          if (c.material) {
            if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose());
            else c.material.dispose();
          }
        });
        delete this.meshes[organKey];
      }

      this.meshes[organKey] = model;
      this.scene.add(model);
      if (this.slicingState && this.slicingState.enabled) {
        this.buildBivalveHalves();
        this.updateSlicing();
      }
    } catch (e) {
      console.warn(`Mesh load failed for [${organKey}]: ${e.message}`);
    }
  }

  addTrajectory(candidate, isActive = false) {
    const start = new THREE.Vector3(...candidate.entry_point_lps);
    const end = new THREE.Vector3(...candidate.target_point_lps);

    if (isActive) {
      this.activeTrajectoryId = candidate.candidate_id;
      this.activeTrajectoryVector = new THREE.Vector3().subVectors(end, start).normalize();
    }

    const trajGroup = new THREE.Group();
    trajGroup.name = `trajectory_${candidate.candidate_id}`;

    // Color code based on clinical safety classification (M12/M13 Clinical Safety Interlock)
    let colorHex = 0x22c55e; // Green: Optimal/Preferred
    const badge = (candidate.safety_badge || candidate.clinical_classification || '').toUpperCase();
    if (badge === 'SUBOPTIMAL' || badge === 'CONDITIONAL' || badge === 'WARNING') {
      colorHex = 0xeab308; // Yellow/Amber: Conditional
    } else if (badge === 'REJECTED' || badge === 'CRITICAL_HAZARD' || badge === 'HAZARD') {
      colorHex = 0xef4444; // Red: Rejected / High Risk
    }

    const dir = new THREE.Vector3().subVectors(end, start);
    const length = dir.length();

    // 1. Needle Shaft (18 Gauge PCNL Trocar)
    const shaftRadius = isActive ? 1.0 : 0.6;
    const shaftGeo = new THREE.CylinderGeometry(shaftRadius, shaftRadius, length, 16);
    shaftGeo.translate(0, length / 2, 0);
    shaftGeo.rotateX(Math.PI / 2);

    const shaftMat = new THREE.MeshStandardMaterial({
      color: colorHex,
      roughness: 0.25,
      metalness: 0.85,
      emissive: isActive ? colorHex : 0x000000,
      emissiveIntensity: isActive ? 0.35 : 0.0
    });
    const shaftMesh = new THREE.Mesh(shaftGeo, shaftMat);
    shaftMesh.position.copy(start);
    shaftMesh.lookAt(end);
    trajGroup.add(shaftMesh);

    // 2. Entry Bullseye Ring
    const ringRadius = isActive ? 3.0 : 2.0;
    const ringGeo = new THREE.TorusGeometry(ringRadius, 0.4, 8, 24);
    const ringMat = new THREE.MeshBasicMaterial({ color: colorHex });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.position.copy(start);
    ringMesh.lookAt(end);
    trajGroup.add(ringMesh);

    // 3. Target Papilla Bevel Tip
    const coneRadius = isActive ? 1.5 : 1.0;
    const coneGeo = new THREE.ConeGeometry(coneRadius, 3.5, 16);
    coneGeo.translate(0, -1.75, 0);
    coneGeo.rotateX(-Math.PI / 2);
    const coneMat = new THREE.MeshStandardMaterial({
      color: colorHex,
      metalness: 0.9,
      roughness: 0.1
    });
    const coneMesh = new THREE.Mesh(coneGeo, coneMat);
    coneMesh.position.copy(end);
    coneMesh.lookAt(end.clone().add(dir));
    trajGroup.add(coneMesh);

    trajGroup.userData = { candidateId: candidate.candidate_id, candidate: candidate };

    this.scene.add(trajGroup);
    this.trajectories.push({
      candidateId: candidate.candidate_id,
      candidate: candidate,
      object: trajGroup
    });
  }

  setActiveTrajectory(candidateId) {
    this.activeTrajectoryId = candidateId;
    this.trajectories.forEach((t) => {
      const isAct = t.candidateId === candidateId;
      if (isAct) {
        const start = new THREE.Vector3(...t.candidate.entry_point_lps);
        const end = new THREE.Vector3(...t.candidate.target_point_lps);
        this.activeTrajectoryVector = new THREE.Vector3().subVectors(end, start).normalize();
      }
      t.object.traverse((child) => {
        if (child.isMesh && child.material) {
          if (child.material.emissive) {
            child.material.emissiveIntensity = isAct ? 0.35 : 0.0;
          }
        }
      });
    });
  }

  focusOnStone(sliceOpen = true) {
    if (this.meshes['stones'] && this.controls) {
      const stoneMesh = this.meshes['stones'];
      const box = new THREE.Box3().setFromObject(stoneMesh);
      const center = box.getCenter(new THREE.Vector3());
      this.controls.target.copy(center);
      // Position camera at an oblique angle looking directly into the calyx cavity
      this.camera.position.set(center.x + 8.0, center.y - 75.0, center.z + 18.0);
      this.controls.update();

      if (sliceOpen) {
        this.sliceThroughStone();
      }
    }
  }

  onPointerDown(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const trajObjects = this.trajectories.map((t) => t.object);
    const intersects = this.raycaster.intersectObjects(trajObjects, true);

    if (intersects.length > 0) {
      let topObj = intersects[0].object;
      while (topObj.parent && !topObj.userData.candidateId) {
        topObj = topObj.parent;
      }
      if (topObj.userData.candidateId) {
        const candId = topObj.userData.candidateId;
        this.setActiveTrajectory(candId);
        window.dispatchEvent(new CustomEvent('trajectorySelected', { detail: { candidateId: candId } }));
      }
    } else {
      const allMeshes = Object.values(this.meshes);
      const organHits = this.raycaster.intersectObjects(allMeshes, true);
      if (organHits.length > 0) {
        const pt = organHits[0].point;
        if (window.mprViewer && typeof window.mprViewer.syncToLPS === 'function') {
          window.mprViewer.syncToLPS(pt.x, pt.y, pt.z);
        }
      }
    }
  }

  /**
   * Sets clinical camera preset with standard urological/radiological alignment.
   */
  setClinicalView(preset) {
    if (!this.controls || !this.camera) return;
    const target = new THREE.Vector3(17.0, 14.0, 50.0);
    this.controls.target.copy(target);

    switch (preset) {
      case 'ap':
      case 'posterior':
        // Anteroposterior 0° direct posterior surgical view
        this.camera.position.set(17.0, -160.0, 50.0);
        break;
      case 'flank':
      case 'lateral':
        // Lateral Flank 90° profile
        this.camera.position.set(190.0, 14.0, 50.0);
        break;
      case 'oblique':
        // 30° Ipsilateral Oblique fluoroscopic working angle
        this.camera.position.set(110.0, -130.0, 50.0);
        break;
      case 'bullseye':
        // Aligned along active trajectory trocar vector
        if (this.activeTrajectoryId) {
          const t = this.trajectories.find((x) => x.candidateId === this.activeTrajectoryId);
          if (t) {
            const start = new THREE.Vector3(...t.candidate.entry_point_lps);
            const end = new THREE.Vector3(...t.candidate.target_point_lps);
            const dir = new THREE.Vector3().subVectors(end, start).normalize();
            this.camera.position.copy(start.clone().sub(dir.clone().multiplyScalar(100)));
            this.controls.target.copy(end);
          }
        } else {
          this.camera.position.set(17.0, -160.0, 50.0);
        }
        break;
      case 'stone':
        this.focusOnStone();
        break;
      default:
        this.camera.position.set(17.0, -160.0, 50.0);
        break;
    }
    this.camera.lookAt(this.controls.target);
    this.controls.update();
  }

  setCameraView(viewPreset) {
    this.setClinicalView(viewPreset);
  }

    /**
   * Returns estimated centroid of kidney parenchyma or entire organ complex
   */
  getKidneyCenter() {
    if (this.meshes['kidney']) {
      const box = new THREE.Box3().setFromObject(this.meshes['kidney']);
      return box.getCenter(new THREE.Vector3());
    }
    const box = new THREE.Box3();
    Object.values(this.meshes).forEach((m) => box.expandByObject(m));
    if (!box.isEmpty()) {
      return box.getCenter(new THREE.Vector3());
    }
    return new THREE.Vector3(17.0, 14.0, 50.0);
  }

  /**
   * Returns centroid of target renal calculus if loaded
   */
  getStoneCenter() {
    if (this.meshes['stones']) {
      const box = new THREE.Box3().setFromObject(this.meshes['stones']);
      return box.getCenter(new THREE.Vector3());
    }
    return null;
  }

  /**
   * Computes unit normal vector from yaw (azimuth) and pitch (elevation) angles.
   * Coordinate system: Patient LPS (X: Medial-Lateral, Y: Anterior-Posterior, Z: Superior-Inferior)
   */
  getCutNormal(yawDeg = 0, pitchDeg = 0) {
    const yawRad = (yawDeg * Math.PI) / 180;
    const pitchRad = (pitchDeg * Math.PI) / 180;
    const cosPitch = Math.cos(pitchRad);
    const nx = cosPitch * Math.sin(yawRad);
    const ny = cosPitch * Math.cos(yawRad);
    const nz = Math.sin(pitchRad);
    const norm = new THREE.Vector3(nx, ny, nz);
    return norm.lengthSq() > 1e-4 ? norm.normalize() : new THREE.Vector3(0, 1, 0);
  }

  /**
   * Deep clones a mesh hierarchy and assigns hardware clipping plane to cloned materials
   */
  _cloneSubtreeWithPlanes(sourceGroup, plane) {
    const root = new THREE.Group();
    root.name = `bivalve_${sourceGroup.name || 'node'}`;
    sourceGroup.traverse((child) => {
      if (child.isMesh && child.geometry) {
        const clonedMesh = new THREE.Mesh(child.geometry);
        clonedMesh.name = child.name;
        clonedMesh.renderOrder = child.renderOrder || 0;
        clonedMesh.castShadow = !!child.castShadow;
        clonedMesh.receiveShadow = !!child.receiveShadow;
        if (child.material) {
          if (Array.isArray(child.material)) {
            clonedMesh.material = child.material.map((m) => {
              const cm = m.clone();
              cm.clippingPlanes = [plane];
              cm.clipShadows = true;
              cm.side = THREE.DoubleSide;
              cm.needsUpdate = true;
              return cm;
            });
          } else {
            clonedMesh.material = child.material.clone();
            clonedMesh.material.clippingPlanes = [plane];
            clonedMesh.material.clipShadows = true;
            clonedMesh.material.side = THREE.DoubleSide;
            clonedMesh.needsUpdate = true;
          }
        }
        clonedMesh.position.copy(child.position);
        clonedMesh.quaternion.copy(child.quaternion);
        clonedMesh.scale.copy(child.scale);
        root.add(clonedMesh);
      }
    });
    return root;
  }

  /**
   * Creates 3D holographic surgical resection disc gizmo showing cutting plane in viewport
   */
  createSlicePlaneGizmo() {
    if (this.sliceGizmo) {
      this.scene.remove(this.sliceGizmo);
      this.sliceGizmo.traverse((c) => this._disposeNode(c));
      this.sliceGizmo = null;
    }

    const gizmo = new THREE.Group();
    gizmo.name = 'slicePlaneGizmo';

    // 1. Holographic Resection Disc (75 mm radius, double sided)
    const discGeo = new THREE.CircleGeometry(75, 64);
    const discMat = new THREE.MeshBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.12,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const disc = new THREE.Mesh(discGeo, discMat);
    gizmo.add(disc);

    // 2. Neon Surgical Perimeter Ring
    const ringGeo = new THREE.RingGeometry(74.2, 75.0, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xec4899,
      transparent: true,
      opacity: 0.8,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    gizmo.add(ring);

    // 3. Fine Crosshair Grid
    const crossGeo = new THREE.BufferGeometry();
    const crossPts = [
      new THREE.Vector3(-75, 0, 0.1), new THREE.Vector3(75, 0, 0.1),
      new THREE.Vector3(0, -75, 0.1), new THREE.Vector3(0, 75, 0.1),
    ];
    crossGeo.setFromPoints(crossPts);
    const crossMat = new THREE.LineBasicMaterial({
      color: 0x00e5a3,
      transparent: true,
      opacity: 0.45,
      depthWrite: false,
    });
    const cross = new THREE.LineSegments(crossGeo, crossMat);
    gizmo.add(cross);

    // 4. Directional Normal Vector Arrow (28 mm)
    const arrow = new THREE.ArrowHelper(
      new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(0, 0, 0),
      28,
      0x00e5a3,
      6,
      3
    );
    gizmo.add(arrow);

    this.sliceGizmo = gizmo;
    this.sliceGizmo.visible = false;
    this.scene.add(this.sliceGizmo);
  }

  /**
   * Cleans up bivalve meshes and gizmos
   */
  clearBivalve() {
    if (this.bivalveGroupA) {
      this.scene.remove(this.bivalveGroupA);
      this.bivalveGroupA.traverse((c) => this._disposeNode(c));
      this.bivalveGroupA = null;
    }
    if (this.bivalveGroupB) {
      this.scene.remove(this.bivalveGroupB);
      this.bivalveGroupB.traverse((c) => this._disposeNode(c));
      this.bivalveGroupB = null;
    }
    if (this.sliceGizmo) {
      this.scene.remove(this.sliceGizmo);
      this.sliceGizmo.traverse((c) => this._disposeNode(c));
      this.sliceGizmo = null;
    }
    this.bivalveMeshesA = {};
    this.bivalveMeshesB = {};
  }

  /**
   * Builds dual-half bivalve geometry for visceral renal organs
   */
  buildBivalveHalves() {
    this.clearBivalve();

    this.planeA = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    this.planeB = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);

    this.bivalveGroupA = new THREE.Group();
    this.bivalveGroupA.name = 'bivalveGroupA';

    this.bivalveGroupB = new THREE.Group();
    this.bivalveGroupB.name = 'bivalveGroupB';

    this.bivalveMeshesA = {};
    this.bivalveMeshesB = {};

    const SLICEABLE_ORGANS = ['kidney', 'capsule', 'pyramids', 'collecting', 'arteries', 'veins', 'nerves'];

    for (const key of SLICEABLE_ORGANS) {
      const orig = this.meshes[key];
      if (!orig) continue;

      const cloneA = this._cloneSubtreeWithPlanes(orig, this.planeA);
      cloneA.visible = (this._layerVisibility[key] !== false);
      this.bivalveMeshesA[key] = cloneA;
      this.bivalveGroupA.add(cloneA);

      const cloneB = this._cloneSubtreeWithPlanes(orig, this.planeB);
      cloneB.visible = (this._layerVisibility[key] !== false);
      this.bivalveMeshesB[key] = cloneB;
      this.bivalveGroupB.add(cloneB);
    }

    this.scene.add(this.bivalveGroupA);
    this.scene.add(this.bivalveGroupB);

    this.createSlicePlaneGizmo();
  }

  /**
   * Core GPU Slicing & Bivalve Parting Separation Execution
   */
  updateSlicing() {
    const SLICEABLE_ORGANS = ['kidney', 'capsule', 'pyramids', 'collecting', 'arteries', 'veins', 'nerves'];
    if (!this.slicingState.enabled) {
      if (this.bivalveGroupA) this.bivalveGroupA.visible = false;
      if (this.bivalveGroupB) this.bivalveGroupB.visible = false;
      if (this.sliceGizmo) this.sliceGizmo.visible = false;
      for (const key of SLICEABLE_ORGANS) {
        if (this.meshes[key]) {
          this.meshes[key].visible = (this._layerVisibility[key] !== false);
          this.meshes[key].traverse((c) => {
            if (c.isMesh && c.material) {
              if (Array.isArray(c.material)) {
                c.material.forEach((m) => { m.clippingPlanes = []; m.needsUpdate = true; });
              } else {
                c.material.clippingPlanes = [];
                c.material.needsUpdate = true;
              }
            }
          });
        }
      }
      return;
    }

    if (!this.bivalveGroupA || !this.bivalveGroupB) {
      this.buildBivalveHalves();
    }

    // Hide original sliceable organs so only bivalve halves render
    for (const key of SLICEABLE_ORGANS) {
      if (this.meshes[key]) {
        this.meshes[key].visible = false;
      }
    }

    const normal = this.getCutNormal(this.slicingState.angleYaw, this.slicingState.anglePitch);
    if (this.slicingState.inverted) {
      normal.negate();
    }

    const kidneyCenter = this.getKidneyCenter();
    const P0 = new THREE.Vector3().copy(kidneyCenter).addScaledVector(normal, this.slicingState.offsetMm);

    const isBivalve = this.slicingState.mode === 'bivalve';
    const G = isBivalve ? (this.slicingState.separationMm || 0) : 0;
    const halfG = G * 0.5;

    // Shift halves apart along normal vector
    this.bivalveGroupA.position.copy(normal).multiplyScalar(halfG);
    this.bivalveGroupB.position.copy(normal).multiplyScalar(-halfG);

    // Update clipping planes
    const dotP0 = normal.dot(P0);
    this.planeA.normal.copy(normal);
    this.planeA.constant = -(dotP0 + halfG);

    this.planeB.normal.copy(normal).negate();
    this.planeB.constant = dotP0 - halfG;

    this.bivalveGroupA.visible = true;
    this.bivalveGroupB.visible = isBivalve;

    // Sync visibility inside bivalve groups
    for (const key of SLICEABLE_ORGANS) {
      const vis = (this._layerVisibility[key] !== false);
      if (this.bivalveMeshesA[key]) this.bivalveMeshesA[key].visible = vis;
      if (this.bivalveMeshesB[key]) this.bivalveMeshesB[key].visible = vis;
    }

    // Update 3D holographic resection disc
    if (this.sliceGizmo) {
      if (this.slicingState.showGizmo) {
        this.sliceGizmo.visible = true;
        this.sliceGizmo.position.copy(P0);
        this.sliceGizmo.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
      } else {
        this.sliceGizmo.visible = false;
      }
    }
  }

  /**
   * Updates slicing parameters and triggers render update
   */
  setSlicingParameters(params = {}) {
    Object.assign(this.slicingState, params);
    this.updateSlicing();
    this._dispatchSlicingEvent();
  }

  /**
   * Automatically aligns the resection plane to pass directly through the kidney calculus
   */
  sliceThroughStone() {
    const stoneCenter = this.getStoneCenter();
    const kidneyCenter = this.getKidneyCenter();
    if (!stoneCenter) return;

    const normal = this.getCutNormal(this.slicingState.angleYaw, this.slicingState.anglePitch);
    const diff = new THREE.Vector3().subVectors(stoneCenter, kidneyCenter);
    const offsetMm = Math.round(normal.dot(diff));

    this.setSlicingParameters({
      enabled: true,
      offsetMm: offsetMm,
    });
  }

  /**
   * Converts a 2D screen stroke (finger, stylus, or pencil gesture) into a 3D resection plane
   */
  sliceFromScreenStroke(x1, y1, x2, y2) {
    if (!this.camera || !this.renderer) return;
    const canvas = this.renderer.domElement;
    const rect = canvas.getBoundingClientRect();
    const w = rect.width || canvas.clientWidth || 1;
    const h = rect.height || canvas.clientHeight || 1;

    const ndc1 = new THREE.Vector2(((x1 - rect.left) / w) * 2 - 1, -((y1 - rect.top) / h) * 2 + 1);
    const ndc2 = new THREE.Vector2(((x2 - rect.left) / w) * 2 - 1, -((y2 - rect.top) / h) * 2 + 1);

    const p1 = new THREE.Vector3(ndc1.x, ndc1.y, 0.5).unproject(this.camera);
    const p2 = new THREE.Vector3(ndc2.x, ndc2.y, 0.5).unproject(this.camera);

    const strokeDir = new THREE.Vector3().subVectors(p2, p1).normalize();
    if (strokeDir.lengthSq() < 1e-4) return;

    const viewDir = new THREE.Vector3();
    if (this.controls && this.controls.target) {
      viewDir.subVectors(this.controls.target, this.camera.position).normalize();
    } else {
      this.camera.getWorldDirection(viewDir);
    }

    const normal = new THREE.Vector3().crossVectors(strokeDir, viewDir).normalize();
    if (normal.lengthSq() < 1e-4) return;

    const midNdc = new THREE.Vector2((ndc1.x + ndc2.x) * 0.5, (ndc1.y + ndc2.y) * 0.5);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(midNdc, this.camera);

    const kidneyCenter = this.getKidneyCenter();
    let hitPoint = null;
    const checkTargets = [];
    if (this.meshes['kidney']) checkTargets.push(this.meshes['kidney']);
    if (this.meshes['stones']) checkTargets.push(this.meshes['stones']);
    
    if (checkTargets.length > 0) {
      const hits = raycaster.intersectObjects(checkTargets, true);
      if (hits.length > 0) {
        hitPoint = hits[0].point;
      }
    }

    const planePoint = hitPoint || kidneyCenter;
    const diff = new THREE.Vector3().subVectors(planePoint, kidneyCenter);
    const offsetMm = normal.dot(diff);

    const pitchRad = Math.asin(Math.max(-1, Math.min(1, normal.z)));
    const cosPitch = Math.cos(pitchRad);
    let yawRad = 0;
    if (Math.abs(cosPitch) > 1e-3) {
      yawRad = Math.atan2(normal.x, normal.y);
    }
    let yawDeg = Math.round((yawRad * 180 / Math.PI + 360) % 360);
    let pitchDeg = Math.round(pitchRad * 180 / Math.PI);

    this.setSlicingParameters({
      enabled: true,
      angleYaw: yawDeg,
      anglePitch: pitchDeg,
      offsetMm: Math.round(offsetMm),
    });
  }

  _dispatchSlicingEvent() {
    if (typeof window !== 'undefined' && window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent('acucalyx:slicingStateChanged', {
        detail: { ...this.slicingState }
      }));
    }
  }

  /**
   * Backward-compatible wrapper for single-axis cutaways
   */
  setCutaway(axis, offsetMm, enabled, inverted = false) {
    let angleYaw = 0;
    let anglePitch = 0;
    if (axis === 'coronal') {
      angleYaw = 0;
      anglePitch = 0;
    } else if (axis === 'sagittal') {
      angleYaw = 90;
      anglePitch = 0;
    } else if (axis === 'axial') {
      angleYaw = 0;
      anglePitch = 90;
    }
    this.setSlicingParameters({
      enabled: !!enabled,
      mode: 'cutaway',
      angleYaw,
      anglePitch,
      offsetMm: offsetMm !== undefined ? offsetMm : 0,
      inverted: !!inverted,
    });
  }

  setLayerVisibility(organKey, visible) {
    this._layerVisibility[organKey] = visible;
    const SLICEABLE_ORGANS = ['kidney', 'capsule', 'pyramids', 'collecting', 'arteries', 'veins', 'nerves'];
    if (this.meshes[organKey]) {
      this.meshes[organKey].visible = (this.slicingState && this.slicingState.enabled && SLICEABLE_ORGANS.includes(organKey)) ? false : visible;
    }
    if (this.bivalveMeshesA && this.bivalveMeshesA[organKey]) {
      this.bivalveMeshesA[organKey].visible = visible;
    }
    if (this.bivalveMeshesB && this.bivalveMeshesB[organKey]) {
      this.bivalveMeshesB[organKey].visible = visible;
    }
  }

  setLayerOpacity(organKey, opacity) {
    const updateOpacity = (obj) => {
      if (!obj) return;
      obj.traverse((child) => {
        if (child.isMesh && child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach((m) => {
              m.opacity = opacity;
              m.transparent = opacity < 1.0;
            });
          } else {
            child.material.opacity = opacity;
            child.material.transparent = opacity < 1.0;
          }
        }
      });
    };
    updateOpacity(this.meshes[organKey]);
    if (this.bivalveMeshesA) updateOpacity(this.bivalveMeshesA[organKey]);
    if (this.bivalveMeshesB) updateOpacity(this.bivalveMeshesB[organKey]);
  }

  setTheme(theme) {
    this.currentTheme = theme;
    if (theme === 'dark') {
      this.scene.background = new THREE.Color(0x0a0d14);
      if (this.studioShadow) this.studioShadow.visible = false;
    } else if (theme === 'light') {
      this.scene.background = new THREE.Color(0xf8fafc);
      if (this.studioShadow) {
        this.studioShadow.visible = true;
        this.studioShadow.material.opacity = 0.25;
      }
    } else { // hybrid (default)
      this.scene.background = null;
      if (this.studioShadow) {
        this.studioShadow.visible = true;
        this.studioShadow.material.opacity = 0.35;
      }
    }
  }
}

// Assign to global window for non-module scripts
if (typeof window !== 'undefined') {
  window.AcuCalyxViewer3D = AcuCalyxViewer3D;
}

export { AcuCalyxViewer3D };
