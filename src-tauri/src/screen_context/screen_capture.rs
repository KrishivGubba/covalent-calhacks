use core_foundation::base::{CFRelease, CFTypeRef};
use core_foundation::data;
use core_graphics::display::{
    CGDisplayBounds, CGDisplayCreateImage, CGDisplayCreateImageForRect, CGDisplayPixelsHigh,
    CGDisplayPixelsWide, CGGetActiveDisplayList, CGMainDisplayID, CGRect, CGSize,
};
use core_graphics::geometry::{CGPoint, CGRect as CoreCGRect};
use core_graphics::image::CGImage;
use core_graphics::window::{
    CGWindowID, CGWindowListCreateDescriptionFromArray,
    CGWindowListCreateImage, kCGNullWindowID, kCGWindowImageDefault,
    kCGWindowListOptionOnScreenOnly,
};
use foreign_types::ForeignType;
use image::{DynamicImage, ImageBuffer, Rgb};
use lru::LruCache;
use parking_lot::Mutex;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::num::NonZeroUsize;
use std::sync::Arc;
use std::time::{Duration, Instant};
use thiserror::Error;
use anyhow::Result;

#[derive(Error, Debug)]
pub enum ScreenCaptureError {
    #[error("Display not found")]
    DisplayNotFound,
    
    #[error("Invalid region: {0}")]
    InvalidRegion(String),
    
    #[error("Core Graphics error: {0}")]
    CoreGraphicsError(String),
    
    #[error("Image conversion error: {0}")]
    ImageConversionError(#[from] image::ImageError),
    
    #[error("Window not found with ID: {0}")]
    WindowNotFound(u32),
    
    #[error("Permission denied - screen recording permission required")]
    PermissionDenied,
    
    #[error("Memory allocation failed")]
    MemoryError,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisplayInfo {
    pub id: u32,
    pub bounds: Region,
    pub scale_factor: f64,
    pub is_main: bool,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Region {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

impl Region {
    pub fn new(x: f32, y: f32, width: f32, height: f32) -> Self {
        Self { x, y, width, height }
    }
    
    pub fn area(&self) -> f32 {
        self.width * self.height
    }
    
    pub fn is_valid(&self) -> bool {
        self.width > 0.0 && self.height > 0.0
    }
    
    pub fn to_cg_rect(&self) -> CoreCGRect {
        CoreCGRect::new(
            &CGPoint::new(self.x as f64, self.y as f64),
            &CGSize::new(self.width as f64, self.height as f64),
        )
    }
}

#[derive(Debug, Clone)]
struct CachedScreenshot {
    image: DynamicImage,
    captured_at: Instant,
    perceptual_hash: u64,
}

impl CachedScreenshot {
    fn is_expired(&self, ttl: Duration) -> bool {
        Instant::now() - self.captured_at > ttl
    }
}

pub struct ScreenCapture {
    cache: Arc<Mutex<LruCache<String, CachedScreenshot>>>,
    cache_ttl: Duration,
    downsample_factor: f32,
    privacy_mode: bool,
}

impl ScreenCapture {
    pub fn new() -> Result<Self> {
        Ok(Self {
            cache: Arc::new(Mutex::new(LruCache::new(
                NonZeroUsize::new(10).unwrap()
            ))),
            cache_ttl: Duration::from_millis(100),
            downsample_factor: 0.5,
            privacy_mode: true,
        })
    }
    
    pub fn with_cache_settings(cache_size: usize, ttl: Duration) -> Result<Self> {
        Ok(Self {
            cache: Arc::new(Mutex::new(LruCache::new(
                NonZeroUsize::new(cache_size).unwrap()
            ))),
            cache_ttl: ttl,
            downsample_factor: 0.5,
            privacy_mode: true,
        })
    }
    
    /// Check if we have screen recording permission
    pub fn check_permission(&self) -> bool {
        unsafe {
            let displays = self.get_display_list().unwrap_or_default();
            if displays.is_empty() {
                return false;
            }
            
            let main_display = displays[0];
            let test_image = CGDisplayCreateImage(main_display);
            
            if test_image.is_null() {
                false
            } else {
                CFRelease(test_image as CFTypeRef);
                true
            }
        }
    }
    
    /// Capture full screen from the main display
    pub fn capture_full_screen(&self) -> Result<DynamicImage> {
        use screenshots::Screen;
        
        // Get all screens
        let screens = Screen::all().map_err(|e| {
            anyhow::anyhow!("Failed to get screens: {}", e)
        })?;
        
        // Get the primary screen
        let primary_screen = screens.into_iter()
            .next()
            .ok_or_else(|| anyhow::anyhow!("No screens found"))?;
        
        // Capture the screen
        let screenshot = primary_screen.capture().map_err(|e| {
            anyhow::anyhow!("Failed to capture screen: {}", e)
        })?;
        
        // Convert to DynamicImage
        let width = screenshot.width();
        let height = screenshot.height();
        
        // Get pixel data - the screenshots crate returns RGBA data  
        let rgba_data = screenshot.rgba();
        
        // Convert RGBA to RGB
        let mut rgb_data = Vec::with_capacity((width * height * 3) as usize);
        for rgba_chunk in rgba_data.chunks(4) {
            if rgba_chunk.len() >= 3 {
                rgb_data.push(rgba_chunk[0]); // R
                rgb_data.push(rgba_chunk[1]); // G  
                rgb_data.push(rgba_chunk[2]); // B
                // Skip alpha channel
            }
        }
        
        let image_buffer = ImageBuffer::<Rgb<u8>, Vec<u8>>::from_raw(
            width, height, rgb_data
        ).ok_or_else(|| ScreenCaptureError::ImageConversionError(
            image::ImageError::Parameter(image::error::ParameterError::from_kind(
                image::error::ParameterErrorKind::DimensionMismatch
            ))
        ))?;
        
        Ok(DynamicImage::ImageRgb8(image_buffer))
    }
    
    /// Capture a specific region of the screen
    pub fn capture_region(&self, x: f32, y: f32, width: f32, height: f32) -> Result<DynamicImage> {
        let region = Region::new(x, y, width, height);
        
        if !region.is_valid() {
            return Err(ScreenCaptureError::InvalidRegion(
                format!("Invalid dimensions: {}x{}", width, height)
            ).into());
        }
        
        // Check cache first
        let cache_key = format!("region_{}_{}_{}_{}", x, y, width, height);
        if let Some(cached) = self.get_from_cache(&cache_key) {
            return Ok(cached.image);
        }
        
        unsafe {
            let main_display = CGMainDisplayID();
            let cg_rect = region.to_cg_rect();
            
            let image_ref = CGDisplayCreateImageForRect(main_display, cg_rect);
            if image_ref.is_null() {
                return Err(ScreenCaptureError::CoreGraphicsError(
                    "Failed to create image for region".to_string()
                ).into());
            }
            
            let cg_image = CGImage::from_ptr(image_ref);
            let result = self.cg_image_to_dynamic_image(cg_image);
            
            // Cache the result
            if let Ok(ref img) = result {
                let hash = self.compute_perceptual_hash(img);
                self.cache_screenshot(cache_key, img.clone(), hash);
            }
            
            result
        }
    }
    
    /// Capture a specific window by its ID
    pub fn capture_window(&self, window_id: u32) -> Result<DynamicImage> {
        unsafe {
            let cg_window_id = window_id as CGWindowID;
            let window_list = vec![cg_window_id];
            
            let image_ref = CGWindowListCreateImage(
                CGRect::new(&CGPoint::new(0.0, 0.0), &CGSize::new(0.0, 0.0)),
                kCGWindowListOptionOnScreenOnly,
                cg_window_id,
                kCGWindowImageDefault,
            );
            
            if image_ref.is_null() {
                return Err(ScreenCaptureError::WindowNotFound(window_id).into());
            }
            
            let cg_image = CGImage::from_ptr(image_ref);
            self.cg_image_to_dynamic_image(cg_image)
        }
    }

    // pub fn remove_inactive(&self) -> Result<()> {
    //     let active_window_id = self.get_active_window_id()?;
    //     let image = self.capture_window(active_window_id)?;
    //     Ok(())
    // }
        
    /// Get information about all available displays
    pub fn get_display_info(&self) -> Vec<DisplayInfo> {
        let mut displays = Vec::new();
        
        unsafe {
            let display_list = match self.get_display_list() {
                Ok(list) => list,
                Err(_) => return displays,
            };
            
            let main_display = CGMainDisplayID();
            
            for &display_id in &display_list {
                let bounds = CGDisplayBounds(display_id);
                let width = CGDisplayPixelsWide(display_id);
                let height = CGDisplayPixelsHigh(display_id);
                
                // Calculate scale factor (for Retina displays)
                let scale_factor = width as f64 / bounds.size.width;
                
                displays.push(DisplayInfo {
                    id: display_id,
                    bounds: Region::new(
                        bounds.origin.x as f32,
                        bounds.origin.y as f32,
                        bounds.size.width as f32,
                        bounds.size.height as f32,
                    ),
                    scale_factor,
                    is_main: display_id == main_display,
                    name: format!("Display {}", display_id),
                });
            }
        }
        
        displays
    }
    
    /// Compare two images and return similarity score (0.0 = different, 1.0 = identical)
    pub fn compare_images(&self, img1: &DynamicImage, img2: &DynamicImage) -> f32 {
        if (img1.width(), img1.height()) != (img2.width(), img2.height()) {
            return 0.0;
        }
        
        let hash1 = self.compute_perceptual_hash(img1);
        let hash2 = self.compute_perceptual_hash(img2);
        
        // Hamming distance for perceptual hash
        let diff_bits = (hash1 ^ hash2).count_ones();
        let max_bits = 64;
        
        1.0 - (diff_bits as f32 / max_bits as f32)
    }
    
    /// Detect changed regions between two images
    pub fn detect_changed_regions(&self, old: &DynamicImage, new: &DynamicImage) -> Vec<Region> {
        if (old.width(), old.height()) != (new.width(), new.height()) {
            return vec![Region::new(0.0, 0.0, new.width() as f32, new.height() as f32)];
        }
        
        let (width, height) = (new.width(), new.height());
        let block_size = 32; // Compare in 32x32 blocks
        let threshold = 10.0; // Minimum difference threshold
        
        let old_rgb = old.to_rgb8();
        let new_rgb = new.to_rgb8();
        
        // Use parallel processing for faster comparison
        let blocks: Vec<_> = (0..height)
            .step_by(block_size as usize)
            .flat_map(|y| {
                (0..width).step_by(block_size as usize).map(move |x| (x, y))
            })
            .collect();
        
        let changed_blocks: Vec<_> = blocks
            .par_iter()
            .filter_map(|&(x, y)| {
                let block_width = block_size.min(width - x);
                let block_height = block_size.min(height - y);
                
                let mut diff_sum = 0.0;
                let mut pixel_count = 0;
                
                for py in y..(y + block_height) {
                    for px in x..(x + block_width) {
                        let old_pixel = old_rgb.get_pixel(px, py);
                        let new_pixel = new_rgb.get_pixel(px, py);
                        
                        let r_diff = (old_pixel[0] as f32 - new_pixel[0] as f32).abs();
                        let g_diff = (old_pixel[1] as f32 - new_pixel[1] as f32).abs();
                        let b_diff = (old_pixel[2] as f32 - new_pixel[2] as f32).abs();
                        
                        diff_sum += (r_diff + g_diff + b_diff) / 3.0;
                        pixel_count += 1;
                    }
                }
                
                let avg_diff = diff_sum / pixel_count as f32;
                if avg_diff > threshold {
                    Some(Region::new(x as f32, y as f32, block_width as f32, block_height as f32))
                } else {
                    None
                }
            })
            .collect();
        
        // Merge adjacent changed blocks
        self.merge_adjacent_regions(changed_blocks)
    }
    
    /// Compute perceptual hash for fast image comparison
    pub fn compute_perceptual_hash(&self, img: &DynamicImage) -> u64 {
        // Resize to 8x8 for perceptual hashing
        let small = img.resize_exact(8, 8, image::imageops::FilterType::Lanczos3);
        let gray = small.to_luma8();
        
        // Calculate average pixel value
        let pixels: Vec<u8> = gray.pixels().map(|p| p.0[0]).collect();
        let avg: f32 = pixels.iter().map(|&p| p as f32).sum::<f32>() / 64.0;
        
        // Create hash based on pixels above/below average
        let mut hash = 0u64;
        for (i, &pixel) in pixels.iter().enumerate() {
            if pixel as f32 > avg {
                hash |= 1 << i;
            }
        }
        
        hash
    }
    
    // Private helper methods
    
    fn capture_display(&self, display_id: u32) -> Result<DynamicImage> {
        unsafe {
            let image_ref = CGDisplayCreateImage(display_id);
            if image_ref.is_null() {
                return Err(ScreenCaptureError::CoreGraphicsError(
                    "Failed to create display image".to_string()
                ).into());
            }
            
            let cg_image = CGImage::from_ptr(image_ref);
            let result = self.cg_image_to_dynamic_image(cg_image);
            
            result
        }
    }
    
    fn cg_image_to_dynamic_image(&self, _cg_image: CGImage) -> Result<DynamicImage> {
        // This method is no longer used since we switched to the screenshots crate
        // for better cross-platform screenshot support
        Err(anyhow::anyhow!("CG Image conversion deprecated - use capture_full_screen instead"))
    }
    
    fn get_display_list(&self) -> Result<Vec<u32>> {
        unsafe {
            let max_displays = 32;
            let mut display_count = 0u32;
            let mut display_list = vec![0u32; max_displays];
            
            let result = CGGetActiveDisplayList(
                max_displays as u32,
                display_list.as_mut_ptr(),
                &mut display_count,
            );
            
            if result != 0 {
                return Err(ScreenCaptureError::CoreGraphicsError(
                    "Failed to get display list".to_string()
                ).into());
            }
            
            display_list.truncate(display_count as usize);
            Ok(display_list)
        }
    }
    
    fn get_active_window_id(&self) -> Result<u32> {
        // This is a simplified implementation
        // In a real app, you'd use more sophisticated window detection
        unsafe {
            let window_list = CGWindowListCreateDescriptionFromArray(kCGNullWindowID as *mut _);
            
            if window_list.is_null() {
                return Err(ScreenCaptureError::CoreGraphicsError(
                    "Failed to get window list".to_string()
                ).into());
            }
            
            // For now, return the first valid window ID
            // In practice, you'd filter for the frontmost window
            let window_id = 1; // Placeholder
            
            Ok(window_id)
        }
    }
    
    fn get_from_cache(&self, key: &str) -> Option<CachedScreenshot> {
        let mut cache = self.cache.lock();
        if let Some(cached) = cache.get(key) {
            if !cached.is_expired(self.cache_ttl) {
                return Some(cached.clone());
            } else {
                cache.pop(key);
            }
        }
        None
    }
    
    fn cache_screenshot(&self, key: String, image: DynamicImage, hash: u64) {
        let mut cache = self.cache.lock();
        cache.put(key, CachedScreenshot {
            image,
            captured_at: Instant::now(),
            perceptual_hash: hash,
        });
    }
    
    fn merge_adjacent_regions(&self, regions: Vec<Region>) -> Vec<Region> {
        if regions.is_empty() {
            return regions;
        }
        
        let mut merged = Vec::new();
        let mut used = vec![false; regions.len()];
        
        for i in 0..regions.len() {
            if used[i] {
                continue;
            }
            
            let mut current = regions[i].clone();
            used[i] = true;
            
            // Try to merge with adjacent regions
            let mut changed = true;
            while changed {
                changed = false;
                for j in 0..regions.len() {
                    if used[j] {
                        continue;
                    }
                    
                    if self.are_regions_adjacent(&current, &regions[j]) {
                        current = self.combine_regions(&current, &regions[j]);
                        used[j] = true;
                        changed = true;
                    }
                }
            }
            
            merged.push(current);
        }
        
        merged
    }
    
    fn are_regions_adjacent(&self, r1: &Region, r2: &Region) -> bool {
        let threshold = 5.0; // pixels
        
        let horizontal_overlap = !(r1.x + r1.width + threshold < r2.x || 
                                   r2.x + r2.width + threshold < r1.x);
        let vertical_overlap = !(r1.y + r1.height + threshold < r2.y || 
                                r2.y + r2.height + threshold < r1.y);
        
        horizontal_overlap && vertical_overlap
    }
    
    fn combine_regions(&self, r1: &Region, r2: &Region) -> Region {
        let min_x = r1.x.min(r2.x);
        let min_y = r1.y.min(r2.y);
        let max_x = (r1.x + r1.width).max(r2.x + r2.width);
        let max_y = (r1.y + r1.height).max(r2.y + r2.height);
        
        Region::new(min_x, min_y, max_x - min_x, max_y - min_y)
    }
}

impl Default for ScreenCapture {
    fn default() -> Self {
        Self::new().expect("Failed to initialize ScreenCapture")
    }
}

// Secure memory management
impl Drop for ScreenCapture {
    fn drop(&mut self) {
        if self.privacy_mode {
            // Clear cache on drop for privacy
            let mut cache = self.cache.lock();
            cache.clear();
        }
    }
}

// Tests
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_region_creation() {
        let region = Region::new(10.0, 20.0, 100.0, 50.0);
        assert_eq!(region.x, 10.0);
        assert_eq!(region.y, 20.0);
        assert_eq!(region.width, 100.0);
        assert_eq!(region.height, 50.0);
        assert_eq!(region.area(), 5000.0);
        assert!(region.is_valid());
    }
    
    #[test]
    fn test_invalid_region() {
        let region = Region::new(0.0, 0.0, 0.0, 0.0);
        assert!(!region.is_valid());
    }
    
    #[test]
    fn test_screen_capture_initialization() {
        let capture = ScreenCapture::new();
        assert!(capture.is_ok());
    }
    
    #[test]
    fn test_perceptual_hash_identical_images() {
        let capture = ScreenCapture::new().unwrap();
        let img = DynamicImage::new_rgb8(100, 100);
        let hash1 = capture.compute_perceptual_hash(&img);
        let hash2 = capture.compute_perceptual_hash(&img);
        assert_eq!(hash1, hash2);
    }
    
    #[test]
    fn test_compare_identical_images() {
        let capture = ScreenCapture::new().unwrap();
        let img = DynamicImage::new_rgb8(100, 100);
        let similarity = capture.compare_images(&img, &img);
        assert!((similarity - 1.0).abs() < f32::EPSILON);
    }
    
    #[test]
    fn test_region_merging() {
        let capture = ScreenCapture::new().unwrap();
        let r1 = Region::new(0.0, 0.0, 10.0, 10.0);
        let r2 = Region::new(8.0, 0.0, 10.0, 10.0); // Adjacent
        
        assert!(capture.are_regions_adjacent(&r1, &r2));
        
        let merged = capture.combine_regions(&r1, &r2);
        assert_eq!(merged.x, 0.0);
        assert_eq!(merged.width, 18.0);
    }
    
    #[tokio::test]
    async fn test_permission_check() {
        let capture = ScreenCapture::new().unwrap();
        // Note: This test might fail in CI/automated environments
        // where screen recording permission isn't granted
        let _has_permission = capture.check_permission();
        // We can't assert true here as it depends on system permissions
    }
}