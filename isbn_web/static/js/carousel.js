// Three.js Carousel for book lots - v2025-10-19T06:00:00Z
// Interactive 3D book carousel with dynamic sizing and auto-centering
//
// Key features:
// - Parallel cover image loading using Promise.all() (~10x faster)
// - Dynamic radius and camera distance based on container dimensions
// - Auto-snap to nearest book when carousel stops spinning
// - Books maintain viewer-facing orientation via counter-rotation
// - Explicit lifecycle management via custom events (carousel-init, carousel-reload)
// - Responsive layout that recalculates on window resize
//
// Store Three.js objects outside Alpine's reactivity to avoid proxy conflicts
const threeState = {
  scene: null,
  camera: null,
  renderer: null,
  bookMeshes: [],
  textureLoader: null,
  rotationOffset: 0,
  velocity: 0,
  isDragging: false,
  lastMouseX: 0,
  animationFrame: null,
  isInitializing: false,
  isInitialized: false,
  eventListeners: [],
  // Cache DOM elements
  canvas: null,
  container: null,
  // Track which carousel instance owns the current state
  ownerInstanceId: null,
  // Store reference to the carousel component
  carouselInstance: null
};

// Expose threeState globally so templates can check initialization status
window.threeState = threeState;

function threeCarousel() {
  return {
    books: [],
    instanceId: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,

    async init() {
      console.log(`[${this.instanceId}] Init started, isInitialized: ${threeState.isInitialized}`);

      // Store reference to this instance
      threeState.carouselInstance = this;

      // Prevent overlapping initialization
      if (threeState.isInitializing) {
        console.log(`[${this.instanceId}] Init already in progress, aborting`);
        return;
      }

      // Mark as initializing and claim ownership
      threeState.isInitializing = true;
      threeState.ownerInstanceId = this.instanceId;
      console.log(`[${this.instanceId}] Starting fresh initialization`);

      // Load books data
      const dataScript = document.getElementById('carousel-books-data');
      if (!dataScript) {
        console.error('No carousel-books-data script found');
        threeState.isInitializing = false;
        return;
      }

      this.books = JSON.parse(dataScript.textContent);
      if (this.books.length === 0) {
        threeState.isInitializing = false;
        return;
      }

      // Wait a moment for HTMX to fully swap the DOM
      await new Promise(resolve => setTimeout(resolve, 10));

      // Cache DOM elements - MUST be done fresh after any destroy()
      // Query for NEW elements that HTMX just loaded
      threeState.canvas = document.getElementById('carousel-canvas');
      threeState.container = document.getElementById('carousel-container');

      console.log(`[${this.instanceId}] Found DOM elements:`, {
        canvas: !!threeState.canvas,
        container: !!threeState.container,
        canvasWidth: threeState.canvas?.width,
        canvasHeight: threeState.canvas?.height
      });

      if (!threeState.canvas || !threeState.container) {
        console.error('Canvas or container not found', {
          canvas: !!threeState.canvas,
          container: !!threeState.container,
          canvasInDOM: !!document.getElementById('carousel-canvas'),
          containerInDOM: !!document.getElementById('carousel-container')
        });
        threeState.isInitializing = false;
        return;
      }

      console.log('Carousel init: DOM elements cached successfully');

      // Setup Three.js scene
      console.log('Calling setupScene()...');
      let sceneReady;
      try {
        sceneReady = this.setupScene();
        console.log('setupScene() returned:', sceneReady);
      } catch (error) {
        console.error('setupScene() threw an error:', error);
        threeState.isInitializing = false;
        return;
      }

      if (!sceneReady) {
        console.error('Failed to setup scene, aborting initialization');
        threeState.isInitializing = false;
        return;
      }
      console.log('Scene setup complete, scene exists:', !!threeState.scene, 'scene obj:', threeState.scene);

      // Create book meshes (parallelized)
      await this.createBooks();

      // Setup event listeners
      this.setupEventListeners();

      // Mark as initialized
      threeState.isInitialized = true;
      threeState.isInitializing = false;

      // Force an immediate render
      if (threeState.renderer && threeState.scene && threeState.camera) {
        threeState.renderer.render(threeState.scene, threeState.camera);
      }

      // Start animation loop
      this.animate();

      // Add initial spin
      const baseVelocity = 0.15;
      const scaleFactor = Math.max(0.3, 1 - (this.books.length / 100));
      threeState.velocity = baseVelocity * scaleFactor;

      // Force resize to ensure correct dimensions
      if (threeState.container && threeState.camera && threeState.renderer) {
        threeState.camera.aspect = threeState.container.clientWidth / threeState.container.clientHeight;
        threeState.camera.updateProjectionMatrix();
        threeState.renderer.setSize(threeState.container.clientWidth, threeState.container.clientHeight);
      }
    },

    setupScene() {
      console.log('setupScene() START', {
        canvas: !!threeState.canvas,
        container: !!threeState.container,
        existingScene: !!threeState.scene,
        existingRenderer: !!threeState.renderer
      });

      // Use cached DOM elements
      const canvas = threeState.canvas;
      const container = threeState.container;

      if (!canvas || !container) {
        console.error('Cannot setup scene: canvas or container is null', {
          canvas: !!canvas,
          container: !!container
        });
        return false;
      }

      // Reset ALL state BEFORE creating scene
      threeState.rotationOffset = 0;
      threeState.velocity = 0;
      threeState.isDragging = false;
      threeState.lastMouseX = 0;

      // Dispose of old renderer completely BEFORE creating new scene
      if (threeState.renderer) {
        try {
          threeState.renderer.renderLists.dispose();
          threeState.renderer.dispose();
          // Force context loss to fully clean up WebGL
          const gl = threeState.renderer.getContext();
          if (gl && gl.getExtension('WEBGL_lose_context')) {
            gl.getExtension('WEBGL_lose_context').loseContext();
          }
        } catch (e) {
          console.warn('Error disposing renderer:', e);
        }
        threeState.renderer = null;
      }

      // Create completely new scene
      threeState.scene = new THREE.Scene();
      threeState.scene.background = new THREE.Color(0xf9fafb);
      threeState.scene.rotation.set(0, 0, 0);

      // Create completely new camera with default settings
      const aspect = container.clientWidth / container.clientHeight;
      threeState.camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 1000);
      threeState.camera.position.set(0, 0, 400);
      threeState.camera.rotation.set(0, 0, 0);
      threeState.camera.lookAt(0, 0, 0);

      // Create completely new renderer with fresh canvas reference
      threeState.renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: true
      });
      threeState.renderer.setSize(container.clientWidth, container.clientHeight);
      threeState.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      threeState.renderer.shadowMap.enabled = true;

      // Add lights to new scene
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      threeState.scene.add(ambientLight);

      const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
      directionalLight.position.set(10, 10, 10);
      directionalLight.castShadow = true;
      threeState.scene.add(directionalLight);

      const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
      fillLight.position.set(-10, 0, -10);
      threeState.scene.add(fillLight);

      // Create new texture loader
      threeState.textureLoader = new THREE.TextureLoader();

      console.log('setupScene() END - scene created successfully:', {
        scene: !!threeState.scene,
        camera: !!threeState.camera,
        renderer: !!threeState.renderer
      });

      return true;
    },

    createBookGeometry(aspectRatio = 0.7, scale = 1.0) {
      const baseHeight = 60; // Height of the book cover
      const height = baseHeight * scale;
      const width = height * aspectRatio; // Width based on aspect ratio
      const depth = 3 * scale; // Book thickness (spine depth) - much smaller than width/height

      // BoxGeometry(width, height, depth) where:
      // width = cover width (x-axis)
      // height = cover height (y-axis)
      // depth = spine thickness (z-axis)
      const geometry = new THREE.BoxGeometry(width, height, depth);
      return geometry;
    },

    async createBooks() {
      const numBooks = this.books.length;
      if (numBooks === 0) return;

      // Safety check - ensure scene exists
      if (!threeState.scene) {
        console.error('Cannot create books: scene is null!', {
          scene: !!threeState.scene,
          camera: !!threeState.camera,
          renderer: !!threeState.renderer
        });
        return;
      }

      // Get actual container dimensions
      const container = threeState.container;
      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight;

      // Book dimensions (approximate - will be refined per book based on cover aspect ratio)
      const avgBookHeight = 60; // Base height
      const avgBookWidth = avgBookHeight * 0.7; // Approximate width based on typical aspect ratio
      const bookDepth = 3; // Spine thickness

      // Calculate optimal radius based on container width
      // Goal: diameter + 2 book widths should fit within container width
      const maxUsableWidth = containerWidth * 0.85; // Use 85% of width for comfortable margins
      const maxRadius = (maxUsableWidth - (2 * avgBookWidth)) / 2;

      // Calculate minimum radius needed for book spacing with generous gaps
      const minGap = 15; // Generous gap between books for better spacing
      const requiredCircumference = numBooks * (avgBookWidth + minGap);
      const minRadiusForSpacing = requiredCircumference / (2 * Math.PI);

      // For smaller lots, prefer to use more of the available space
      // Use 60% of max radius as absolute minimum for visual appeal
      const minRadiusForAppearance = maxRadius * 0.6;
      const minRadius = Math.max(minRadiusForSpacing, minRadiusForAppearance);

      // Use the calculated radius, capped at maxRadius
      const radius = Math.min(minRadius, maxRadius);

      // Calculate book scale based on how much space we have
      // If we need to shrink the radius to fit, scale books down proportionally
      let bookScale = 1.0;
      if (minRadius > maxRadius) {
        bookScale = Math.max(0.5, maxRadius / minRadius);
      }

      // Calculate optimal camera distance based on container height
      // Goal: the closest book (at radius distance) should nearly fill the height
      // Using perspective projection: screenHeight ≈ (objectHeight / distance) * fov_factor
      const fov = 50; // Camera FOV from setupScene
      const fovRadians = (fov * Math.PI) / 180;
      const targetBookHeight = avgBookHeight * bookScale;

      // We want the book to take up about 70% of the container height
      const targetScreenHeight = containerHeight * 0.7;

      // Calculate camera distance to achieve this
      // tan(fov/2) = (screenHeight/2) / distance
      // Rearranging: distance = (objectHeight / targetScreenHeight) * (containerHeight / (2 * tan(fov/2)))
      const fovFactor = containerHeight / (2 * Math.tan(fovRadians / 2));
      const optimalDistance = (targetBookHeight / targetScreenHeight) * fovFactor + radius;

      // Set camera position with calculated distance
      const cameraDistance = Math.max(optimalDistance, radius + 100); // Ensure minimum distance
      threeState.camera.position.set(0, 0, cameraDistance);
      threeState.camera.rotation.set(0, 0, 0);
      threeState.camera.lookAt(0, 0, 0);

      console.log('Carousel dimensions:', {
        containerWidth,
        containerHeight,
        maxRadius: maxRadius.toFixed(0),
        minRadiusForSpacing: minRadiusForSpacing.toFixed(0),
        minRadiusForAppearance: minRadiusForAppearance.toFixed(0),
        finalRadius: radius.toFixed(0),
        bookScale: bookScale.toFixed(2),
        cameraDistance: cameraDistance.toFixed(0),
        numBooks
      });

      // Reset scene rotation to ensure carousel starts at correct position
      threeState.scene.rotation.set(0, 0, 0);

      // Clear previous meshes
      threeState.bookMeshes.forEach(mesh => {
        if (mesh.geometry) mesh.geometry.dispose();
        if (Array.isArray(mesh.material)) {
          mesh.material.forEach(mat => mat.dispose());
        } else if (mesh.material) {
          mesh.material.dispose();
        }
        threeState.scene.remove(mesh);
      });
      threeState.bookMeshes = [];

      // Load all book materials in parallel for better performance
      const materialPromises = this.books.map(book =>
        book && book.isbn ? this.createBookMaterials(book) : Promise.resolve(null)
      );
      const materialsResults = await Promise.all(materialPromises);

      // Create meshes with loaded materials
      for (let i = 0; i < numBooks; i++) {
        const book = this.books[i];
        const result = materialsResults[i];

        if (!book || !book.isbn || !result) continue;

        const angle = (i / numBooks) * Math.PI * 2;
        const aspectRatio = result.aspectRatio;
        const materials = result.materials;

        // Create book geometry with actual cover dimensions
        const geometry = this.createBookGeometry(aspectRatio, bookScale);

        // Create mesh
        const mesh = new THREE.Mesh(geometry, materials);

        // Position on circle
        const x = Math.sin(angle) * radius;
        const z = Math.cos(angle) * radius;
        mesh.position.set(x, 0, z);

        // Initial rotation - will be updated dynamically in animate()
        mesh.rotation.y = angle + Math.PI / 2;

        // Store book data and base angle for rotation calculations
        mesh.userData = { book, index: i, baseAngle: angle };

        threeState.bookMeshes.push(mesh);
        threeState.scene.add(mesh);
      }
    },

    async createBookMaterials(book) {
      const coverUrl = `/api/covers/${book.isbn}?size=M`;

      // Create placeholder materials
      const sideMaterial = new THREE.MeshStandardMaterial({
        color: 0x333333,
        roughness: 0.7,
        metalness: 0.1
      });

      const pageMaterial = new THREE.MeshStandardMaterial({
        color: 0xf5f5f5,
        roughness: 0.8,
        metalness: 0.0
      });

      const spineMaterial = new THREE.MeshStandardMaterial({
        color: 0x2563eb,
        roughness: 0.6,
        metalness: 0.2
      });

      // Try to load cover texture and get dimensions
      try {
        const result = await new Promise((resolve, reject) => {
          threeState.textureLoader.load(
            coverUrl,
            (texture) => {
              texture.minFilter = THREE.LinearFilter;
              texture.magFilter = THREE.LinearFilter;

              // Get actual cover image dimensions
              const img = texture.image;
              const aspectRatio = img.width / img.height;

              resolve({ texture, aspectRatio });
            },
            undefined,
            () => {
              // On error, use fallback
              resolve(null);
            }
          );
        });

        if (result && result.texture) {
          const frontMaterial = new THREE.MeshStandardMaterial({
            map: result.texture,
            roughness: 0.5,
            metalness: 0.1
          });

          const backMaterial = new THREE.MeshStandardMaterial({
            color: 0x4f46e5,
            roughness: 0.6,
            metalness: 0.1
          });

          // Order: right, left, top, bottom, front, back
          return {
            materials: [
              pageMaterial,      // right (pages)
              spineMaterial,     // left (spine)
              sideMaterial,      // top
              sideMaterial,      // bottom
              frontMaterial,     // front (cover)
              backMaterial       // back
            ],
            aspectRatio: result.aspectRatio
          };
        }
      } catch (e) {
        console.log('Error loading cover for', book.isbn, e);
      }

      // Fallback materials with default aspect ratio
      const defaultCover = new THREE.MeshStandardMaterial({
        color: 0x2563eb,
        roughness: 0.5,
        metalness: 0.1
      });

      return {
        materials: [
          pageMaterial,
          spineMaterial,
          sideMaterial,
          sideMaterial,
          defaultCover,
          defaultCover
        ],
        aspectRatio: 0.65 // Default book cover aspect ratio (typical paperback)
      };
    },

    setupEventListeners() {
      const canvas = threeState.canvas;
      const container = threeState.container;

      // Remove any existing event listeners first
      this.removeEventListeners();

      // Mouse drag handlers
      const mouseDownHandler = (e) => {
        threeState.isDragging = true;
        threeState.lastMouseX = e.clientX;
        threeState.velocity = 0;
      };

      const mouseMoveHandler = (e) => {
        if (threeState.isDragging) {
          const deltaX = e.clientX - threeState.lastMouseX;
          threeState.rotationOffset += deltaX * 0.01;
          threeState.velocity = deltaX * 0.001;
          threeState.lastMouseX = e.clientX;
        }
      };

      const mouseUpHandler = () => {
        threeState.isDragging = false;
      };

      const mouseLeaveHandler = () => {
        threeState.isDragging = false;
      };

      // Mouse wheel handler
      const wheelHandler = (e) => {
        e.preventDefault();
        const delta = e.deltaY * 0.001;
        threeState.velocity += delta * 0.1;
      };

      // Window resize handler - recalculates carousel layout for new dimensions
      const resizeHandler = async () => {
        if (!threeState.camera || !threeState.renderer || !threeState.carouselInstance) return;

        // Update renderer size and camera aspect
        threeState.camera.aspect = container.clientWidth / container.clientHeight;
        threeState.camera.updateProjectionMatrix();
        threeState.renderer.setSize(container.clientWidth, container.clientHeight);

        // Recreate books with new dimensions if we have books loaded
        if (threeState.carouselInstance.books && threeState.carouselInstance.books.length > 0) {
          await threeState.carouselInstance.createBooks();
        }
      };

      // Add event listeners
      canvas.addEventListener('mousedown', mouseDownHandler);
      canvas.addEventListener('mousemove', mouseMoveHandler);
      canvas.addEventListener('mouseup', mouseUpHandler);
      canvas.addEventListener('mouseleave', mouseLeaveHandler);
      canvas.addEventListener('wheel', wheelHandler, { passive: false });
      window.addEventListener('resize', resizeHandler);

      // Store references for cleanup
      threeState.eventListeners = [
        { element: canvas, event: 'mousedown', handler: mouseDownHandler },
        { element: canvas, event: 'mousemove', handler: mouseMoveHandler },
        { element: canvas, event: 'mouseup', handler: mouseUpHandler },
        { element: canvas, event: 'mouseleave', handler: mouseLeaveHandler },
        { element: canvas, event: 'wheel', handler: wheelHandler },
        { element: window, event: 'resize', handler: resizeHandler }
      ];
    },

    removeEventListeners() {
      threeState.eventListeners.forEach(({ element, event, handler }) => {
        element.removeEventListener(event, handler);
      });
      threeState.eventListeners = [];
    },

    rotate(direction) {
      const anglePerBook = (Math.PI * 2) / this.books.length;
      threeState.velocity += direction * anglePerBook * 0.5;
    },

    animate() {
      // Safety check - don't animate if not initialized or if critical objects are missing
      if (!threeState.isInitialized || !threeState.scene || !threeState.renderer || !threeState.camera) {
        // Don't log every frame - only log once when stopping
        if (threeState.animationFrame) {
          console.log('Stopping animation - missing required objects');
        }
        return;
      }

      threeState.animationFrame = requestAnimationFrame(() => this.animate());

      // Apply velocity with friction
      if (!threeState.isDragging) {
        threeState.rotationOffset += threeState.velocity;
        threeState.velocity *= 0.95; // Friction

        // When velocity is very low, snap to nearest book
        if (Math.abs(threeState.velocity) < 0.001 && this.books.length > 0) {
          const anglePerBook = (Math.PI * 2) / this.books.length;

          // Calculate which book should be centered (at angle 0, facing camera)
          // Current rotation offset tells us how much we've rotated
          const currentRotation = threeState.rotationOffset % (Math.PI * 2);

          // Find the nearest book position
          const nearestBookIndex = Math.round(currentRotation / anglePerBook);
          const targetRotation = nearestBookIndex * anglePerBook;

          // Smoothly interpolate to target rotation
          const diff = targetRotation - threeState.rotationOffset;
          if (Math.abs(diff) > 0.001) {
            threeState.rotationOffset += diff * 0.1; // Smooth snap
          } else {
            threeState.rotationOffset = targetRotation;
            threeState.velocity = 0;
          }
        }
      }

      // Update scene rotation
      if (threeState.scene) {
        threeState.scene.rotation.y = threeState.rotationOffset;
      }

      // Update individual book rotations - rotate only in the front 90° arc
      if (threeState.bookMeshes.length > 0) {
        // Debug: log one book's info
        let debuggedOne = false;

        threeState.bookMeshes.forEach((mesh, i) => {
          // Calculate book's angle in the carousel
          const bookBaseAngle = (i / this.books.length) * Math.PI * 2;

          // Calculate book's current world angle (considering scene rotation)
          // In Three.js with camera at z+, books at z+ are facing camera
          let worldAngle = bookBaseAngle - threeState.rotationOffset;

          // Normalize to 0 to 2PI (0 = back, PI = front facing camera)
          worldAngle = ((worldAngle % (Math.PI * 2)) + (Math.PI * 2)) % (Math.PI * 2);

          // Cover always pointing toward viewer
          //
          // Key insight: Books are in a rotating scene (scene.rotation.y = rotationOffset)
          // To keep covers facing camera, books must counter-rotate with the scene
          //
          // When scene rotates by rotationOffset, we need to rotate books by -rotationOffset
          // to maintain their orientation relative to the camera

          // Counter-rotate to maintain viewer-facing orientation
          // Remove the +π since that was showing backs instead of covers
          mesh.rotation.y = -threeState.rotationOffset;
        });
      }

      // Render (we already checked these exist at the start of animate)
      threeState.renderer.render(threeState.scene, threeState.camera);
    },

    destroy() {
      console.log(`[${this.instanceId}] Destroy called, owner: ${threeState.ownerInstanceId}`);

      // Only destroy if this instance owns the current state
      if (threeState.ownerInstanceId && threeState.ownerInstanceId !== this.instanceId) {
        console.log(`[${this.instanceId}] Not destroying - owned by ${threeState.ownerInstanceId}`);
        return;
      }

      console.log(`[${this.instanceId}] Proceeding with destroy`);

      // Cancel animation
      if (threeState.animationFrame) {
        cancelAnimationFrame(threeState.animationFrame);
        threeState.animationFrame = null;
      }

      // Remove event listeners
      this.removeEventListeners();

      // Clean up Three.js resources
      threeState.bookMeshes.forEach(mesh => {
        if (mesh.geometry) mesh.geometry.dispose();
        if (Array.isArray(mesh.material)) {
          mesh.material.forEach(mat => {
            if (mat.map) mat.map.dispose();
            mat.dispose();
          });
        } else if (mesh.material) {
          if (mesh.material.map) mesh.material.map.dispose();
          mesh.material.dispose();
        }
        if (threeState.scene) {
          threeState.scene.remove(mesh);
        }
      });
      threeState.bookMeshes = [];

      // Clear scene including lights
      if (threeState.scene) {
        // Dispose of all children (including lights)
        const children = [...threeState.scene.children];
        children.forEach(child => {
          if (child.dispose) child.dispose();
          threeState.scene.remove(child);
        });
        threeState.scene = null;
      }

      // Reset renderer with forced context loss
      if (threeState.renderer) {
        try {
          const gl = threeState.renderer.getContext();
          if (gl && gl.getExtension('WEBGL_lose_context')) {
            gl.getExtension('WEBGL_lose_context').loseContext();
          }
          threeState.renderer.renderLists.dispose();
          threeState.renderer.dispose();
        } catch (e) {
          console.warn('Error during renderer cleanup:', e);
        }
        threeState.renderer = null;
      }

      // Clear camera reference
      threeState.camera = null;

      // Clear DOM cache
      threeState.canvas = null;
      threeState.container = null;

      // Reset all state variables
      threeState.rotationOffset = 0;
      threeState.velocity = 0;
      threeState.isDragging = false;
      threeState.lastMouseX = 0;
      threeState.isInitializing = false;
      threeState.isInitialized = false;
      threeState.ownerInstanceId = null;
      threeState.carouselInstance = null;

      console.log(`[${this.instanceId}] Destroy complete`);
    }
  };
}

// Global function to reload carousel with new books (called by HTMX after swap)
window.reloadCarousel = async function() {
  console.log('reloadCarousel() called');

  // If not initialized, just call init on the current instance
  if (!threeState.isInitialized || !threeState.carouselInstance) {
    console.log('Carousel not initialized yet, waiting for Alpine init...');
    // Wait a moment for Alpine to initialize the component
    await new Promise(resolve => setTimeout(resolve, 100));
    if (threeState.carouselInstance) {
      await threeState.carouselInstance.init();
    }
    return;
  }

  // Load new books data
  const dataScript = document.getElementById('carousel-books-data');
  if (!dataScript) {
    console.error('No carousel-books-data script found');
    return;
  }

  const newBooks = JSON.parse(dataScript.textContent);
  console.log(`Reloading carousel with ${newBooks.length} new books`);

  // Update the books in the carousel instance
  if (threeState.carouselInstance) {
    threeState.carouselInstance.books = newBooks;

    // Recreate the books with new data
    if (newBooks.length > 0) {
      await threeState.carouselInstance.createBooks();

      // Reset rotation for new lot
      threeState.rotationOffset = 0;
      const baseVelocity = 0.15;
      const scaleFactor = Math.max(0.3, 1 - (newBooks.length / 100));
      threeState.velocity = baseVelocity * scaleFactor;
    }
  }
};
