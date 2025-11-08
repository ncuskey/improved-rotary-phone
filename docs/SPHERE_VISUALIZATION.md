# Server Activity Sphere Visualization

## Overview

The sphere visualization is a real-time 3D visualization of server activity, displaying API requests, database operations, and scraping activity as animated waves rippling across a rotating sphere of book ISBNs.

## File Location

`isbn_web/templates/sphere.html`

## Architecture

### Core Technologies

- **Three.js (r128)**: 3D rendering engine
- **WebSocket**: Real-time server communication
- **GLSL Shaders**: Custom vertex/fragment shaders for wave effects
- **Fibonacci Sphere**: Even point distribution algorithm

### Components

1. **Point Cloud Sphere** - 6,000 points representing books in the catalog
2. **Wave System** - Rippling effects for different event types
3. **Rotation Controls** - Auto-rotation with interactive orbit controls
4. **Stats Panel** - Real-time metrics display
5. **Legend** - Color-coded event type indicator

## Wave Effects

### Wave Types

Each event type triggers a specific colored wave:

| Event Type | Color | Hex Code |
|-----------|-------|----------|
| Request | Hot Pink | #FF0080 |
| Response | Electric Cyan | #00CCFF |
| Database Read | Green | #00FF4D |
| Database Write | Orange | #FF9900 |
| Web Scraping | Yellow | #FFFF00 |
| ML Inference | Purple | #9933FF |

### Wave Parameters

**Current Settings (Subtle):**

```javascript
CONFIG = {
    WAVE_WIDTH: 0.04,      // Band width across sphere
    WAVE_SPEED: 0.015,     // Travel speed
}

// Vertex Shader
displacement = 0.025;      // Outward "pop" effect

// Fragment Shader
intensity = 0.4;           // Wave intensity multiplier
glow = 0.1;               // Brightness multiplier
```

**Historical Values:**

The wave effects have been progressively reduced for better visual balance:

- Initial: WIDTH=0.15, displacement=0.15, intensity=3.0, glow=0.6
- First reduction: WIDTH=0.08, displacement=0.05, intensity=0.8, glow=0.2
- Current (50% reduction): WIDTH=0.04, displacement=0.025, intensity=0.4, glow=0.1

### Bloom Post-Processing

The bloom effect adds glow to bright points:

```javascript
UnrealBloomPass({
    strength: 0.15,    // Overall bloom intensity
    radius: 0.2,       // Glow spread distance
    threshold: 0.92    // Minimum brightness for bloom
})
```

## WebSocket Events

### Connection

```javascript
ws://localhost:5001/sphere_updates
```

### Event Types

1. **request** - API endpoint accessed
2. **response** - API response sent
3. **db_read** - Database query executed
4. **db_write** - Database write operation
5. **scraping** - Web scraping operation
6. **ml_inference** - ML model prediction

### Event Message Format

```json
{
    "type": "request",
    "endpoint": "/api/books/9780140449136",
    "latitude": 0.523,
    "response_time_ms": 45.2
}
```

## Visual Customization

### Adjusting Wave Intensity

**To make waves more subtle:**
1. Reduce `WAVE_WIDTH` (narrower bands)
2. Reduce vertex shader displacement multiplier
3. Reduce fragment shader intensity and glow

**To make waves more prominent:**
1. Increase `WAVE_WIDTH` (wider bands)
2. Increase displacement multiplier
3. Increase intensity and glow

### Adjusting Bloom

**For less glow:**
- Decrease `strength` (0.1-0.3)
- Decrease `radius` (0.1-0.3)
- Increase `threshold` (0.9-0.95)

**For more glow:**
- Increase `strength` (0.5-1.0)
- Increase `radius` (0.5-1.0)
- Decrease `threshold` (0.7-0.85)

### Changing Colors

Edit the `COLOR_PALETTE` object:

```javascript
const COLOR_PALETTE = {
    idle: { r: 0.20, g: 0.88, b: 0.95 },      // Cyan #34EDF3
    requestWave: { r: 1.0, g: 0.0, b: 0.5 },  // Hot pink
    // ... etc
};
```

## Performance

### Metrics

- **FPS Target**: 60fps
- **Point Count**: 6,000 books
- **WebSocket Updates**: ~10-100/second (varies with traffic)
- **GPU**: Uses hardware acceleration for rendering

### Optimization Tips

1. **Reduce Point Count**: Change `NUM_POINTS: 6000` to lower value
2. **Disable Bloom**: Comment out `bloomPass` for ~30% performance gain
3. **Lower Resolution**: Reduce renderer size for mobile devices
4. **Throttle Updates**: Batch WebSocket events if >200/sec

## Browser Compatibility

- **Chrome/Edge**: Full support (recommended)
- **Firefox**: Full support
- **Safari**: Full support (may need WebGL2 fallback)
- **Mobile**: Works but may have performance issues

## Controls

### Interactive Controls

- **Mouse Drag**: Rotate sphere
- **Mouse Wheel**: Zoom in/out
- **Right Click + Drag**: Pan camera

### Button Controls

- **⏸ PAUSE ROTATION**: Toggle auto-rotation
- **⟲ RESET VIEW**: Return to default camera position
- **⚡ TEST WAVES**: Trigger sample waves for testing

## Development

### Testing Wave Effects

Use the "TEST WAVES" button to preview all wave types:

```javascript
function testWaves() {
    // Triggers sample waves from north pole in sequence
    const waveTypes = ['request', 'response', 'db_read', 'db_write', 'scraping', 'ml'];
    waveTypes.forEach((type, i) => {
        setTimeout(() => {
            triggerWave(type, 1.57); // latitude = 90° (north pole)
        }, i * 500);
    });
}
```

### Adding New Wave Types

1. Add color to `COLOR_PALETTE`
2. Add legend entry in HTML
3. Handle in `processMessage()` switch statement
4. Update server to emit new event type

## Code Map

**Key Functions:**

- `createSphere()`: Initializes 6,000-point Fibonacci sphere
- `createPostProcessing()`: Sets up bloom effects
- `processMessage(data)`: Handles WebSocket events
- `triggerWave(type, latitude)`: Creates wave at latitude
- `animate()`: Main render loop (60fps)
- `updateWaves()`: Updates wave positions each frame

**Shader Code:**

- `vertexShader`: Displaces points outward during waves
- `fragmentShader`: Applies glow and color effects

## Related Files

- `isbn_web/api/routes/monitor.py`: WebSocket event emitter
- `isbn_web/app.py`: Flask server with Socket.IO integration
- `isbn_web/templates/index.html`: Main dashboard with sphere embed

## Troubleshooting

### Waves Too Intense

Reduce parameters in `sphere.html:321-394`:
- `WAVE_WIDTH`: Make narrower
- Displacement multiplier: Reduce outward pop
- `intensity` and `glow`: Reduce brightness

### Performance Issues

1. Check FPS counter (top-right)
2. Reduce `NUM_POINTS` to 3000 or 4000
3. Disable bloom post-processing
4. Close other GPU-intensive applications

### WebSocket Not Connecting

1. Verify Flask server running on port 5001
2. Check browser console for errors
3. Ensure Socket.IO version matches server
4. Check for CORS issues with WebSocket

## Future Enhancements

1. **Adaptive Quality**: Auto-reduce effects on slow devices
2. **Clustered Points**: Group books by genre/price range
3. **Heat Mapping**: Color points by request frequency
4. **Time Scrubbing**: Replay past activity
5. **VR Support**: WebXR integration for immersive viewing
