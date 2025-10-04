# Mobile Optimization Plan

## Current Issues

### 1. Viewport and Layout Issues
- Fixed `h-screen` and `h-1/2` heights don't work well on mobile browsers with dynamic viewport
- Split-screen layout may be cramped on small screens
- Fixed book card dimensions (`w-64 h-80`) too large for mobile

### 2. 3D Carousel Issues
- Mouse wheel events don't work on touch devices
- No touch gesture support for navigation
- 3D transforms may cause performance issues on mobile GPUs
- Fixed positioning may not work well with mobile viewport changes

### 3. Touch Interaction Issues
- Small click targets may be hard to tap accurately
- No swipe gestures for carousel navigation
- Hover states don't work on touch devices

### 4. Performance Issues
- Complex 3D transforms may be slow on mobile devices
- Large images may cause memory issues
- Multiple simultaneous animations may lag

## Optimization Solutions

### 1. Responsive Design Improvements

#### Viewport Fixes
- Replace fixed heights with flexible units
- Use `min-h-screen` instead of `h-screen`
- Implement proper mobile viewport handling
- Add safe area support for notched devices

#### Layout Responsiveness
- Stack layout vertically on mobile instead of split-screen
- Make carousel full-screen on mobile
- Optimize grid layouts for small screens
- Add proper spacing and padding for touch

### 2. Touch-First Carousel

#### Touch Gestures
- Add swipe left/right for navigation
- Implement touch-friendly button sizes (44px minimum)
- Add pull-to-refresh functionality
- Support pinch-to-zoom for book details

#### Mobile Navigation
- Larger navigation buttons
- Touch-friendly progress dots
- Gesture indicators and hints
- Simplified navigation for one-handed use

### 3. Performance Optimizations

#### 3D Transform Optimization
- Reduce transform complexity on mobile
- Use `transform3d` for hardware acceleration
- Implement reduced motion preferences
- Add performance monitoring

#### Image Optimization
- Lazy loading for book covers
- WebP format support with fallbacks
- Responsive image sizing
- Progressive loading indicators

### 4. Mobile-Specific Features

#### Progressive Web App (PWA)
- [x] Web app manifest (`site.webmanifest`) and favicon set live under `static/images`
- [ ] Implement service worker for offline support
- [ ] Add app icons and splash screens
- [ ] Enable installation prompts

#### Mobile UX Enhancements
- Add haptic feedback for interactions
- Implement pull-to-refresh
- Add loading states and skeletons
- Optimize for one-handed use

## Implementation Priority

### Phase 1: Critical Fixes (High Priority)
1. Fix viewport and height issues
2. Add touch gesture support
3. Optimize carousel for mobile
4. Improve button sizes and touch targets

### Phase 2: Performance (Medium Priority)
1. Optimize 3D transforms
2. Implement image lazy loading
3. Add performance monitoring
4. Reduce animation complexity

### Phase 3: Enhancement (Low Priority)
1. Add PWA features
2. Implement haptic feedback
3. Add gesture indicators
4. Progressive loading features

## Testing Strategy

### Device Testing
- iPhone (Safari)
- Android (Chrome)
- iPad (Safari)
- Various screen sizes and orientations

### Performance Testing
- Lighthouse audits
- Core Web Vitals monitoring
- Battery usage testing
- Network condition simulation

### Accessibility Testing
- Screen reader compatibility
- Keyboard navigation
- Reduced motion preferences
- High contrast mode support
