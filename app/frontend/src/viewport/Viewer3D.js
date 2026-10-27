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
          child.castShadow = true;
          child.receiveShadow = true;

          // Anatomical Physical Materials per Substructure
          if (organKey === 'stones') {
            // Natural calcified crystalline stone: pale ivory, high roughness, zero artificial emissive flare
            child.material = new THREE.MeshStandardMaterial({
              color: 0xfef3c7,
              roughness: 0.85,
              metalness: 0.02,
              emissive: 0x000000,
              emissiveIntensity: 0.0,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 20; // Renders clearly in pelvis/calyx
          } else if (organKey === 'kidney') {
            // Warm pinkish-tan renal parenchyma cortex with subtle wet tissue clearcoat
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0xc87a74,
              roughness: 0.42,
              metalness: 0.02,
              clearcoat: 0.25,
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
            // Fibrous renal capsule: deep mahogany with glossy outer protective sheath
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0x7f1d1d,
              roughness: 0.48,
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
            // Striated medullary pyramids: rich crimson/maroon
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0x881337,
              roughness: 0.52,
              metalness: 0.02,
              clearcoat: 0.15,
              clearcoatRoughness: 0.40,
              transparent: true,
              opacity: defaultOpacity,
              clippingPlanes: this.clippingPlanes,
              clipShadows: true,
              side: THREE.DoubleSide
            });
            child.renderOrder = 2;
          } else if (organKey === 'collecting_system') {
            // Opalescent mucosal calyces, pelvis, and ureter
            child.material = new THREE.MeshPhysicalMaterial({
              color: 0xe2d5c3,
              roughness: 0.28,
              metalness: 0.05,
              clearcoat: 0.30,
              clearcoatRoughness: 0.20,
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
              color: 0x854d0e,
              roughness: 0.65,
              metalness: 0.02,
              transparent: true,
              opacity: 0.28,
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

      this.meshes[organKey] = model;
      this.scene.add(model);
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

    // Color code based on clinical classification
    let colorHex = 0x22c55e; // Green: Optimal
    if (candidate.clinical_classification === 'SUBOPTIMAL') colorHex = 0xeab308; // Yellow
    if (candidate.clinical_classification === 'REJECTED') colorHex = 0xef4444; // Red

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

  focusOnStone() {
    if (this.meshes['stones'] && this.controls) {
      const stoneMesh = this.meshes['stones'];
      const box = new THREE.Box3().setFromObject(stoneMesh);
      const center = box.getCenter(new THREE.Vector3());
      this.controls.target.copy(center);
      this.camera.position.set(center.x, center.y - 75.0, center.z + 20.0);
      this.controls.update();
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
   * Hardware-accelerated GPU clipping cutaway plane control.
   * axis: 'coronal' | 'axial' | 'sagittal'
   * offsetMm: distance in physical mm
   * enabled: boolean
   */
  setCutaway(axis, offsetMm, enabled) {
    if (!this.clippingPlanes) this.clippingPlanes = [];

    let targetPlane = null;
    if (axis === 'coronal') {
      this.coronalClip.constant = offsetMm !== undefined ? offsetMm : 14.0;
      targetPlane = this.coronalClip;
    } else if (axis === 'axial') {
      this.axialClip.constant = offsetMm !== undefined ? offsetMm : 50.0;
      targetPlane = this.axialClip;
    } else if (axis === 'sagittal') {
      this.sagittalClip.constant = offsetMm !== undefined ? offsetMm : 17.0;
      targetPlane = this.sagittalClip;
    }

    if (targetPlane) {
      const idx = this.clippingPlanes.indexOf(targetPlane);
      if (enabled && idx === -1) {
        this.clippingPlanes.push(targetPlane);
      } else if (!enabled && idx !== -1) {
        this.clippingPlanes.splice(idx, 1);
      }
    }

    // Update clippingPlanes across all active mesh materials
    Object.values(this.meshes).forEach((obj) => {
      obj.traverse((child) => {
        if (child.isMesh && child.material) {
          child.material.clippingPlanes = this.clippingPlanes;
          child.material.clipShadows = true;
          child.material.needsUpdate = true;
        }
      });
    });
  }

  setLayerVisibility(organKey, visible) {
    if (this.meshes[organKey]) {
      this.meshes[organKey].visible = visible;
    }
  }

  setLayerOpacity(organKey, opacity) {
    if (this.meshes[organKey]) {
      this.meshes[organKey].traverse((child) => {
        if (child.isMesh && child.material) {
          child.material.opacity = opacity;
          child.material.transparent = opacity < 1.0;
        }
      });
    }
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
