/**
 * AcuCalyx 3D Viewport Engine
 * Powered by Three.js & WebGL
 *
 * Implements:
 * - OrbitControls and smooth camera transitions
 * - Photorealistic Anatomical PBR Shaders for Kidney Cortex, Capsule, Medulla Pyramids, Calyces, Arteries, Veins, Nerves, Nephrons, and Highlighted Calculus
 * - Proper renderOrder depth sorting for clean semi-translucent parenchymal viewing
 * - Pulsing radiant PointLight illuminating target stone and surrounding calyx
 * - PCNL Needle Trajectory selection via Raycasting
 * - Bull's-eye, Progression, and Close-up Stone camera view alignments
 * - Dynamic opacity and layer visibility controls from sidebar
 */

class AcuCalyxViewer3D {
  constructor(canvasContainerId) {
    this.container = document.getElementById(canvasContainerId);
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.meshes = {};
    this.trajectories = [];
    this.activeTrajectoryId = null;
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.stoneLight = null;

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
    this.camera.position.set(17.0, -140.0, 50.0); // Coronal en-face cutaway view facing open anatomy
    this.camera.up.set(0, 0, 1); // Cranial is +Z

    // 3. Renderer with alpha: true for seamless clinical studio blending
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    this.renderer.outputEncoding = THREE.sRGBEncoding;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;
    this.container.appendChild(this.renderer.domElement);

    // 4. Orbit Controls
    if (typeof THREE.OrbitControls !== 'undefined') {
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.target.set(17.0, 14.0, 50.0); // Exact organ centroid
      this.controls.update();
    }

    // 5. Lighting: Multi-point anatomical studio rig
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    this.scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.95);
    dirLight1.position.set(80, 180, 120);
    this.scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.85);
    dirLight2.position.set(-80, -140, 60);
    this.scene.add(dirLight2);

    const dirLight3 = new THREE.DirectionalLight(0xffecd2, 0.50);
    dirLight3.position.set(0, 150, -40);
    this.scene.add(dirLight3);

    // 6. Dedicated Pulsing Stone PointLight (Radiant surgical highlight)
    this.stoneLight = new THREE.PointLight(0xfbbf24, 1.6, 90.0);
    this.stoneLight.position.set(21.5, 13.5, 37.5);
    this.scene.add(this.stoneLight);

    // 7. Subtle Studio Ground Reference Shadow (Replaces harsh wireframe grid)
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

    // 8. Event Listeners
    window.addEventListener('resize', () => this.onWindowResize());
    this.renderer.domElement.addEventListener('pointerdown', (e) => this.onPointerDown(e));

    // Animation Loop
    this.animate();
  }

  animate(time = 0) {
    requestAnimationFrame((t) => this.animate(t));
    if (this.controls) this.controls.update();

    // Pulse stone radiant illumination
    if (this.stoneLight) {
      this.stoneLight.intensity = 0.80 + 0.35 * Math.sin(time * 0.003);
    }

    this.renderer.render(this.scene, this.camera);
  }

  onWindowResize() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  focusOnStone() {
    if (!this.controls) return;
    const stonePos = new THREE.Vector3(21.5, 13.5, 37.5);
    this.camera.position.set(21.5, -45.0, 39.0);
    this.controls.target.copy(stonePos);
    this.controls.update();
  }

  clearScene() {
    for (const key in this.meshes) {
      this.scene.remove(this.meshes[key]);
    }
    this.meshes = {};
    this.clearTrajectories();
  }

  clearTrajectories() {
    this.trajectories.forEach((t) => this.scene.remove(t.object));
    this.trajectories = [];
  }

  /**
   * Loads a GLB mesh from API endpoint with calibrated anatomical PBR materials
   * and clean depth sorting (renderOrder) so internal structures are always visible
   * through the translucent cortex without clipping or z-fighting.
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
          // Essential: compute vertex normals so WebGL PBR diffuse/specular lighting illuminates the geometry
          if (child.geometry) {
            child.geometry.computeVertexNormals();
          }
          child.castShadow = true;
          child.receiveShadow = true;

          // Anatomical PBR Shaders per Substructure
          if (organKey === 'stones') {
            // Highly differentiated crystalline calculus: bright calcified ivory with radiant amber-gold facet glow
            child.material = new THREE.MeshStandardMaterial({
              color: 0xffffff,
              roughness: 0.16,
              metalness: 0.15,
              emissive: 0xf59e0b,
              emissiveIntensity: 0.95,
              side: THREE.DoubleSide
            });
            child.renderOrder = 20; // Renders crystal-clear over surrounding calyx
          } else if (organKey === 'kidney') {
            // Down-shadowed, semi-translucent renal cortex cutaway
            child.material = new THREE.MeshStandardMaterial({
              color: 0xc47e85,
              roughness: 0.65,
              metalness: 0.04,
              transparent: true,
              opacity: defaultOpacity,
              depthWrite: false, // Prevents occluding internal structures
              side: THREE.DoubleSide
            });
            child.renderOrder = 10;
          } else if (organKey === 'renal_capsule') {
            // Dark mahogany protective fibrous capsule
            child.material = new THREE.MeshStandardMaterial({
              color: 0x6e241c,
              roughness: 0.50,
              metalness: 0.08,
              transparent: true,
              opacity: defaultOpacity,
              depthWrite: false,
              side: THREE.DoubleSide
            });
            child.renderOrder = 11;
          } else if (organKey === 'medulla_pyramids') {
            // Striated medullary pyramids (crimson/maroon)
            child.material = new THREE.MeshStandardMaterial({
              color: 0x881337,
              roughness: 0.55,
              metalness: 0.05,
              transparent: true,
              opacity: defaultOpacity,
              side: THREE.DoubleSide
            });
            child.renderOrder = 2;
          } else if (organKey === 'collecting_system') {
            // Warm mucosal opalescent cream / flesh calyces, pelvis, and ureter
            child.material = new THREE.MeshStandardMaterial({
              color: 0xd6bc97,
              roughness: 0.40,
              metalness: 0.08,
              transparent: true,
              opacity: defaultOpacity,
              depthWrite: false, // Allows stone to be viewed inside without clipping
              side: THREE.DoubleSide
            });
            child.renderOrder = 3;
          } else if (organKey === 'renal_arteries') {
            // Segmental, interlobar and arcuate arteries (bright scarlet red)
            child.material = new THREE.MeshStandardMaterial({
              color: 0xef4444,
              roughness: 0.30,
              metalness: 0.15,
              transparent: true,
              opacity: defaultOpacity,
              side: THREE.DoubleSide
            });
            child.renderOrder = 4;
          } else if (organKey === 'renal_veins') {
            // Renal venous drainage (cobalt royal blue)
            child.material = new THREE.MeshStandardMaterial({
              color: 0x2563eb,
              roughness: 0.30,
              metalness: 0.15,
              transparent: true,
              opacity: defaultOpacity,
              side: THREE.DoubleSide
            });
            child.renderOrder = 4;
          } else if (organKey === 'renal_nerves') {
            // Sympathetic and sensory autonomic nerve plexus (golden yellow)
            child.material = new THREE.MeshStandardMaterial({
              color: 0xfacc15,
              roughness: 0.25,
              metalness: 0.10,
              emissive: 0xca8a04,
              emissiveIntensity: 0.45,
              transparent: true,
              opacity: defaultOpacity,
              side: THREE.DoubleSide
            });
            child.renderOrder = 4;
          } else if (organKey === 'nephrons' || organKey === 'nephron_unit') {
            // Nephron micro-loops & tubules (amber)
            child.material = new THREE.MeshStandardMaterial({
              color: 0xf59e0b,
              roughness: 0.30,
              metalness: 0.10,
              emissive: 0xd97706,
              emissiveIntensity: 0.35,
              transparent: true,
              opacity: defaultOpacity,
              side: THREE.DoubleSide
            });
            child.renderOrder = 4;
          } else if (organKey === 'ribs') {
            child.material = new THREE.MeshStandardMaterial({
              color: 0xf1f5f9,
              roughness: 0.70,
              transparent: true,
              opacity: defaultOpacity,
              side: THREE.DoubleSide
            });
            child.renderOrder = 1;
          } else if (organKey === 'colon') {
            child.material = new THREE.MeshStandardMaterial({
              color: 0xf97316,
              roughness: 0.60,
              transparent: true,
              opacity: defaultOpacity,
              side: THREE.DoubleSide
            });
            child.renderOrder = 1;
          } else {
            child.material.transparent = defaultOpacity < 1.0;
            child.material.opacity = defaultOpacity;
            child.material.side = THREE.DoubleSide;
            child.material.roughness = 0.4;
            child.material.metalness = 0.1;
          }
        }
      });

      if (this.meshes[organKey]) {
        this.scene.remove(this.meshes[organKey]);
      }
      this.meshes[organKey] = model;
      this.scene.add(model);
      console.log(`Loaded anatomical mesh: ${organKey}`);
    } catch (err) {
      console.warn(`Could not load mesh ${organKey} (${url}):`, err);
    }
  }

  /**
   * Adds a candidate needle trajectory line with entry and target spheres
   */
  addTrajectory(candidate, isPreferred = false) {
    const start = new THREE.Vector3(...candidate.entry_point_lps);
    const end = new THREE.Vector3(...candidate.target_point_lps);

    const colorHex = isPreferred ? 0x00e5a3 : (candidate.safety_badge === 'REJECTED' ? 0xef4444 : 0xf59e0b);

    const group = new THREE.Group();
    group.userData = { candidateId: candidate.candidate_id };

    // 1. Needle Line / Cylinder
    const dir = new THREE.Vector3().subVectors(end, start);
    const length = dir.length();
    const cylGeo = new THREE.CylinderGeometry(0.9, 0.9, length, 16);
    const cylMat = new THREE.MeshStandardMaterial({
      color: colorHex,
      roughness: 0.3,
      metalness: 0.8
    });
    const cylinder = new THREE.Mesh(cylGeo, cylMat);
    cylinder.renderOrder = 6;

    cylinder.position.copy(new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5));
    cylinder.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
    group.add(cylinder);

    // 2. Skin Entry Marker (Cyan ring)
    const entryGeo = new THREE.SphereGeometry(2.0, 16, 16);
    const entryMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
    const entryMesh = new THREE.Mesh(entryGeo, entryMat);
    entryMesh.position.copy(start);
    entryMesh.renderOrder = 6;
    group.add(entryMesh);

    // 3. Calyx Papilla Target Marker (Target sphere)
    const targetGeo = new THREE.SphereGeometry(2.2, 16, 16);
    const targetMat = new THREE.MeshBasicMaterial({ color: 0xe11d48 });
    const targetMesh = new THREE.Mesh(targetGeo, targetMat);
    targetMesh.position.copy(end);
    targetMesh.renderOrder = 6;
    group.add(targetMesh);

    this.scene.add(group);
    this.trajectories.push({
      candidateId: candidate.candidate_id,
      object: group,
      candidate: candidate
    });
  }

  setActiveTrajectory(candidateId) {
    this.activeTrajectoryId = candidateId;
    this.trajectories.forEach((t) => {
      const isActive = t.candidateId === candidateId;
      t.object.traverse((child) => {
        if (child.isMesh && child.material) {
          if (isActive) {
            child.scale.set(1.4, 1.0, 1.4);
            if (child.material.emissive) child.material.emissive = new THREE.Color(0x00d2ff);
          } else {
            child.scale.set(1.0, 1.0, 1.0);
            if (child.material.emissive) child.material.emissive = new THREE.Color(0x000000);
          }
        }
      });
    });
  }

  onPointerDown(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const clickableTrajectories = this.trajectories.map((t) => t.object);
    const trajIntersects = this.raycaster.intersectObjects(clickableTrajectories, true);

    if (trajIntersects.length > 0) {
      let topObj = trajIntersects[0].object;
      while (topObj.parent && !topObj.userData.candidateId) {
        topObj = topObj.parent;
      }
      if (topObj.userData.candidateId) {
        const id = topObj.userData.candidateId;
        window.dispatchEvent(new CustomEvent('acucalyx:trajectory-selected', { detail: { candidateId: id } }));
      }
    }

    // Milestone M11: Bidirectional 3D <-> 2D Physical LPS Coordinate Synchronization
    const allTargetObjects = Object.values(this.meshes).concat(clickableTrajectories);
    const allIntersects = this.raycaster.intersectObjects(allTargetObjects, true);
    if (allIntersects.length > 0) {
      const hit = allIntersects[0];
      const pt = hit.point;
      if (window.mprViewer && typeof window.mprViewer.syncToLPS === 'function') {
        window.mprViewer.syncToLPS(pt.x, pt.y, pt.z);
      }
    }
  }

  setCameraView(viewPreset) {
    if (!this.controls) return;

    switch (viewPreset) {
      case 'posterior':
        this.camera.position.set(17.0, -140.0, 50.0);
        this.controls.target.set(17.0, 14.0, 50.0);
        break;
      case 'lateral':
        this.camera.position.set(140.0, 14.0, 50.0);
        this.controls.target.set(17.0, 14.0, 50.0);
        break;
      case 'bullseye':
        if (this.activeTrajectoryId) {
          const t = this.trajectories.find((x) => x.candidateId === this.activeTrajectoryId);
          if (t) {
            const start = new THREE.Vector3(...t.candidate.entry_point_lps);
            const end = new THREE.Vector3(...t.candidate.target_point_lps);
            const dir = new THREE.Vector3().subVectors(end, start).normalize();
            this.camera.position.copy(start.clone().sub(dir.clone().multiplyScalar(100)));
            this.controls.target.copy(end);
          }
        }
        break;
      case 'progression':
        if (this.activeTrajectoryId) {
          const t = this.trajectories.find((x) => x.candidateId === this.activeTrajectoryId);
          if (t) {
            const start = new THREE.Vector3(...t.candidate.entry_point_lps);
            const end = new THREE.Vector3(...t.candidate.target_point_lps);
            const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
            const dir = new THREE.Vector3().subVectors(end, start).normalize();
            const ortho = new THREE.Vector3(-dir.y, dir.x, 0).normalize();
            this.camera.position.copy(mid.clone().add(ortho.clone().multiplyScalar(120)));
            this.controls.target.copy(mid);
          }
        }
        break;
      case 'stone':
        this.focusOnStone();
        break;
    }
    this.controls.update();
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
      this.scene.background = null; // Let CSS radial gradient shine through
      if (this.studioShadow) {
        this.studioShadow.visible = true;
        this.studioShadow.material.opacity = 0.35;
      }
    }
  }
}

window.AcuCalyxViewer3D = AcuCalyxViewer3D;
