// Three.js Carousel for book lots - v2025-10-19T02:30:00Z
// Optimized for performance with parallel image loading and minimal logging
//
// Key optimizations:
// - Parallel cover image loading using Promise.all() (~10x faster)
// - DOM element caching to eliminate repeated getElementById() calls
// - Removed verbose logging (kept only critical errors)
// - Proper cleanup between carousel transitions
// - Forced resize after initialization to handle layout timing issues
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
  container: null
};

function threeCarousel() {
  return {
    books: [],

    async init() {
      // Prevent overlapping initialization
      if (threeState.isInitializing) return;

      // Clean up existing scene before reinitializing
      if (threeState.isInitialized) {
        this.destroy();
        // Small delay to ensure cleanup completes
        await new Promise(resolve => setTimeout(resolve, 30));
      }

      // Mark as initializing to prevent duplicate calls
      threeState.isInitializing = true;

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

      // Cache DOM elements
      threeState.canvas = document.getElementById('carousel-canvas');
      threeState.container = document.getElementById('carousel-container');

      if (!threeState.canvas || !threeState.container) {
        console.error('Canvas or container not found');
        threeState.isInitializing = false;
        return;
      }

      // Setup Three.js scene
      this.setupScene();

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
      // Use cached DOM elements
      const canvas = threeState.canvas;
      const container = threeState.container;

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

      // Dynamic scaling - larger for smaller lots
      const baseBookWidth = 45;
      const minGap = 10;
      const requiredCircumference = numBooks * (baseBookWidth + minGap);
      const calculatedRadius = requiredCircumference / (2 * Math.PI);
      const radius = Math.min(Math.max(calculatedRadius, 120), 280);

      // Scale books - keep large for small lots, scale down only for 30+ books
      let bookScale = 1.0;
      if (numBooks > 30) {
        bookScale = Math.max(0.6, 1 - ((numBooks - 30) / 70));
      }

      // Adjust camera position to fit carousel
      const cameraDistance = radius * 1.8 + 100;
      threeState.camera.position.set(0, 0, cameraDistance);
      threeState.camera.rotation.set(0, 0, 0);
      threeState.camera.lookAt(0, 0, 0);

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

        // Rotate so spine faces outward (tangent to circle)
        mesh.rotation.y = angle + Math.PI / 2;

        // Store book data
        mesh.userData = { book, index: i };

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

      // Window resize handler
      const resizeHandler = () => {
        if (!threeState.camera || !threeState.renderer) return;

        threeState.camera.aspect = container.clientWidth / container.clientHeight;
        threeState.camera.updateProjectionMatrix();
        threeState.renderer.setSize(container.clientWidth, container.clientHeight);
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
      // Safety check - don't animate if not initialized or if scene is null
      if (!threeState.isInitialized || !threeState.scene) {
        console.log('Stopping animation - not initialized or scene is null');
        return;
      }

      threeState.animationFrame = requestAnimationFrame(() => this.animate());

      // Apply velocity with friction
      if (!threeState.isDragging) {
        threeState.rotationOffset += threeState.velocity;
        threeState.velocity *= 0.95; // Friction
      }

      // Update scene rotation
      if (threeState.scene) {
        threeState.scene.rotation.y = threeState.rotationOffset;
      }

      // Render
      if (threeState.renderer && threeState.scene && threeState.camera) {
        threeState.renderer.render(threeState.scene, threeState.camera);
      } else {
        console.warn('Cannot render - missing:', {
          renderer: !!threeState.renderer,
          scene: !!threeState.scene,
          camera: !!threeState.camera
        });
      }
    },

    destroy() {
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
    }
  };
}
