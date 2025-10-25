use anyhow::{Context as AnyhowContext, Result};
use image::{DynamicImage, GenericImageView, ImageBuffer};
use imageproc::rect::Rect;
use lru::LruCache;
use parking_lot::Mutex;
use rusty_tesseract::{Args, Image as TessImage};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::num::NonZeroUsize;
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use thiserror::Error;
use tokio::time::timeout;

// Custom error types for better error handling
#[derive(Error, Debug)]
pub enum OCRError {
    #[error("Tesseract not installed or not in PATH")]
    TesseractNotInstalled,
    
    #[error("OCR operation timed out after {0:?}")]
    Timeout(Duration),
    
    #[error("Low confidence result: {confidence}% (threshold: {threshold}%)")]
    LowConfidence { confidence: f32, threshold: f32 },
    
    #[error("Invalid region: {0}")]
    InvalidRegion(String),
    
    #[error("Image processing error: {0}")]
    ImageError(#[from] image::ImageError),
    
    #[error("OCR failed: {0}")]
    ProcessingError(String),
}

// Screen region definition
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct ScreenRegion {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

impl ScreenRegion {
    pub fn new(x: u32, y: u32, width: u32, height: u32) -> Self {
        Self { x, y, width, height }
    }
    
    pub fn area(&self) -> u32 {
        self.width * self.height
    }
    
    pub fn is_valid(&self) -> bool {
        self.width > 0 && self.height > 0
    }
    
    pub fn to_rect(&self) -> Rect {
        Rect::at(self.x as i32, self.y as i32)
            .of_size(self.width, self.height)
    }
}

// OCR result with confidence and metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OCRResult {
    pub text: String,
    pub confidence: f32,
    pub region: ScreenRegion,
    pub language: String,
    pub timestamp: u64,
    pub processing_time_ms: u64,
}

impl OCRResult {
    pub fn is_high_confidence(&self, threshold: f32) -> bool {
        self.confidence >= threshold
    }
}

// Text region detected in image
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Region {
    pub bounds: ScreenRegion,
    pub confidence: f32,
}

// Cached OCR result with TTL
#[derive(Debug, Clone)]
struct CachedResult {
    result: OCRResult,
    expires_at: Instant,
    perceptual_hash: String,
}

impl CachedResult {
    fn is_expired(&self) -> bool {
        Instant::now() > self.expires_at
    }
}

// Main Tesseract OCR engine
pub struct TesseractEngine {
    default_language: String,
    cache: Arc<Mutex<LruCache<String, CachedResult>>>,
    cache_ttl: Duration,
    confidence_threshold: f32,
    timeout_duration: Duration,
    tesseract_available: bool,
    supported_languages: Vec<String>,
}

impl TesseractEngine {
    /// Initialize Tesseract engine with optimal settings for screen capture OCR
    pub fn new() -> Result<Self> {
        // Check if Tesseract is available
        let tesseract_available = Self::check_tesseract_available();
        
        Ok(Self {
            default_language: "eng".to_string(),
            cache: Arc::new(Mutex::new(LruCache::new(
                NonZeroUsize::new(100).unwrap()
            ))),
            cache_ttl: Duration::from_secs(5),
            confidence_threshold: 60.0,
            timeout_duration: Duration::from_secs(2),
            tesseract_available,
            supported_languages: vec!["eng".to_string()],
        })
    }
    
    /// Check if Tesseract is installed and available
    fn check_tesseract_available() -> bool {
        // Try to run a simple tesseract command
        std::process::Command::new("tesseract")
            .arg("--version")
            .output()
            .is_ok()
    }
    
    /// Configure Tesseract for optimal screen text recognition
    pub fn optimize_for_screen_text(&mut self) -> &mut Self {
        // Optimal settings for screen text are already set in process_with_args
        // This method exists for API consistency
        self
    }
    
    /// Set supported languages
    pub fn set_languages(&mut self, languages: Vec<String>) -> &mut Self {
        self.supported_languages = languages;
        self
    }
    
    /// Set default language
    pub fn set_default_language(&mut self, language: String) -> &mut Self {
        self.default_language = language;
        self
    }
    
    /// Set confidence threshold (0-100)
    pub fn set_confidence_threshold(&mut self, threshold: f32) -> &mut Self {
        self.confidence_threshold = threshold.clamp(0.0, 100.0);
        self
    }
    
    /// Set OCR operation timeout
    pub fn set_timeout(&mut self, duration: Duration) -> &mut Self {
        self.timeout_duration = duration;
        self
    }
    
    /// Process a specific screen region with OCR
    pub async fn process_region(&self, region: &ScreenRegion, image: &DynamicImage) 
        -> Result<OCRResult> {
        if !self.tesseract_available {
            return Err(OCRError::TesseractNotInstalled.into());
        }
        
        if !region.is_valid() {
            return Err(OCRError::InvalidRegion(
                format!("Invalid region dimensions: {}x{}", region.width, region.height)
            ).into());
        }
        
        // Check cache first
        let cache_key = self.generate_cache_key(region, image);
        if let Some(cached) = self.get_from_cache(&cache_key) {
            return Ok(cached.result);
        }
        
        let start = Instant::now();
        
        // Extract region from image
        let region_image = self.extract_region(image, region)?;
        
        // Preprocess image for better OCR
        let preprocessed = self.preprocess_image(&region_image)?;
        
        // Perform OCR with timeout
        let text = self.perform_ocr_with_timeout(&preprocessed, &self.default_language)
            .await?;
        
        // Calculate confidence (simplified - Tesseract 4+ has better confidence APIs)
        let confidence = self.estimate_confidence(&text);
        
        let processing_time = start.elapsed();
        
        let result = OCRResult {
            text: self.cleanup_text(&text),
            confidence,
            region: region.clone(),
            language: self.default_language.clone(),
            timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            processing_time_ms: processing_time.as_millis() as u64,
        };
        
        // Cache the result
        let perceptual_hash = self.compute_perceptual_hash(&region_image);
        self.cache_result(cache_key, result.clone(), perceptual_hash);
        
        Ok(result)
    }
    
    /// Process an entire screenshot and return OCR results
    pub async fn process_screenshot(&self, image_path: &Path) 
        -> Result<Vec<OCRResult>> {
        if !self.tesseract_available {
            return Err(OCRError::TesseractNotInstalled.into());
        }
        
        // Load image
        let image = image::open(image_path)
            .context("Failed to load screenshot")?;
        
        // Detect text regions
        let regions = self.detect_text_regions(&image)?;
        
        // Process each region in batch
        let results = self.batch_process_regions(&regions, &image).await?;
        
        Ok(results)
    }
    
    /// Detect text regions in an image
    pub fn detect_text_regions(&self, image: &DynamicImage) -> Result<Vec<Region>> {
        let mut regions = Vec::new();
        
        // Convert to grayscale for analysis
        let gray = image.to_luma8();
        let (width, height) = gray.dimensions();
        
        // Divide image into grid and analyze each cell
        let grid_size = 100; // pixels
        let cols = (width + grid_size - 1) / grid_size;
        let rows = (height + grid_size - 1) / grid_size;
        
        for row in 0..rows {
            for col in 0..cols {
                let x = col * grid_size;
                let y = row * grid_size;
                let w = grid_size.min(width - x);
                let h = grid_size.min(height - y);
                
                // Calculate variance (text regions have high variance)
                let variance = self.calculate_region_variance(&gray, x, y, w, h);
                
                // If variance is high enough, it likely contains text
                if variance > 500.0 {
                    regions.push(Region {
                        bounds: ScreenRegion::new(x, y, w, h),
                        confidence: (variance / 5000.0).min(1.0),
                    });
                }
            }
        }
        
        // Merge adjacent regions
        let merged_regions = self.merge_adjacent_regions(regions);
        
        Ok(merged_regions)
    }
    
    /// Batch process multiple regions for efficiency
    pub async fn batch_process_regions(
        &self,
        regions: &[Region],
        image: &DynamicImage,
    ) -> Result<Vec<OCRResult>> {
        let mut results = Vec::new();
        
        for region in regions {
            match self.process_region(&region.bounds, image).await {
                Ok(result) => {
                    if result.confidence >= self.confidence_threshold {
                        results.push(result);
                    }
                }
                Err(e) => {
                    // Log error but continue processing other regions
                    eprintln!("Error processing region {:?}: {}", region.bounds, e);
                }
            }
        }
        
        Ok(results)
    }
    
    /// Detect language in text (simplified implementation)
    pub fn detect_language(&self, _text: &str) -> Result<String> {
        // For now, return default language
        // A full implementation would use language detection libraries
        Ok(self.default_language.clone())
    }
    
    // Private helper methods
    
    fn extract_region(&self, image: &DynamicImage, region: &ScreenRegion) 
        -> Result<DynamicImage> {
        let (img_width, img_height) = image.dimensions();
        
        // Validate region bounds
        if region.x + region.width > img_width || region.y + region.height > img_height {
            return Err(OCRError::InvalidRegion(
                format!("Region {}x{} at ({},{}) exceeds image bounds {}x{}",
                    region.width, region.height, region.x, region.y,
                    img_width, img_height)
            ).into());
        }
        
        let cropped = image.crop_imm(region.x, region.y, region.width, region.height);
        Ok(cropped)
    }
    
    fn preprocess_image(&self, image: &DynamicImage) -> Result<DynamicImage> {
        // Convert to grayscale
        let mut gray = image.to_luma8();
        
        // Apply contrast enhancement for better OCR
        // Simple contrast stretching
        let (min, max) = gray.pixels().fold((255u8, 0u8), |(min, max), p| {
            (min.min(p.0[0]), max.max(p.0[0]))
        });
        
        if max > min {
            for pixel in gray.pixels_mut() {
                let normalized = ((pixel.0[0] as f32 - min as f32) / (max - min) as f32 * 255.0) as u8;
                pixel.0[0] = normalized;
            }
        }
        
        Ok(DynamicImage::ImageLuma8(gray))
    }
    
    async fn perform_ocr_with_timeout(&self, image: &DynamicImage, language: &str) 
        -> Result<String> {
        let image_clone = image.clone();
        let language = language.to_string();
        let timeout_duration = self.timeout_duration;
        
        // Perform OCR in a separate task with timeout
        let result = timeout(timeout_duration, tokio::task::spawn_blocking(move || {
            Self::perform_ocr_sync(&image_clone, &language)
        })).await;
        
        match result {
            Ok(Ok(text_result)) => text_result,
            Ok(Err(e)) => Err(anyhow::anyhow!("OCR task failed: {}", e)),
            Err(_) => Err(OCRError::Timeout(timeout_duration).into()),
        }
    }
    
    fn perform_ocr_sync(image: &DynamicImage, language: &str) -> Result<String> {
        // Convert DynamicImage to bytes
        let rgba_image = image.to_rgba8();
        let (width, height) = rgba_image.dimensions();
        let bytes = rgba_image.into_raw();
        
        // Save temporary image for Tesseract
        let temp_path = std::env::temp_dir().join(format!("ocr_temp_{}.png", 
            std::process::id()));
        image.save(&temp_path)?;
        
        // Create Tesseract args optimized for screen text
        let args = Args {
            lang: language.to_string(),
            dpi: Some(150),
            psm: Some(3), // Fully automatic page segmentation
            oem: Some(3), // Default, based on what is available
            config_variables: HashMap::from([
                ("tessedit_pageseg_mode".to_string(), "3".to_string()),
                ("tessedit_char_whitelist".to_string(), "".to_string()),
            ]),
        };
        
        // Load image and perform OCR
        let tess_image = TessImage::from_path(&temp_path)
            .map_err(|e| OCRError::ProcessingError(e.to_string()))?;
        
        let text = rusty_tesseract::image_to_string(&tess_image, &args)
            .map_err(|e| OCRError::ProcessingError(e.to_string()))?;
        
        // Clean up temp file
        let _ = std::fs::remove_file(&temp_path);
        
        Ok(text)
    }
    
    fn estimate_confidence(&self, text: &str) -> f32 {
        // Simplified confidence estimation based on text characteristics
        if text.is_empty() {
            return 0.0;
        }
        
        let mut score = 50.0;
        
        // Higher confidence for longer text
        score += (text.len() as f32 / 10.0).min(20.0);
        
        // Higher confidence for text with normal word patterns
        let words: Vec<&str> = text.split_whitespace().collect();
        if !words.is_empty() {
            score += (words.len() as f32 * 2.0).min(20.0);
        }
        
        // Lower confidence for excessive special characters
        let special_chars = text.chars().filter(|c| !c.is_alphanumeric() && !c.is_whitespace()).count();
        let special_ratio = special_chars as f32 / text.len() as f32;
        if special_ratio > 0.3 {
            score -= 20.0;
        }
        
        score.clamp(0.0, 100.0)
    }
    
    fn cleanup_text(&self, text: &str) -> String {
        text.lines()
            .map(|line| line.trim())
            .filter(|line| !line.is_empty())
            .collect::<Vec<_>>()
            .join("\n")
    }
    
    fn generate_cache_key(&self, region: &ScreenRegion, image: &DynamicImage) -> String {
        format!("{}_{}_{}_{}_{}",
            region.x, region.y, region.width, region.height,
            image.dimensions().0)
    }
    
    fn compute_perceptual_hash(&self, image: &DynamicImage) -> String {
        // Simple perceptual hash using image data
        let small = image.resize(8, 8, image::imageops::FilterType::Lanczos3);
        let gray = small.to_luma8();
        
        let avg: f32 = gray.pixels().map(|p| p.0[0] as f32).sum::<f32>() / 64.0;
        
        let hash_bits: Vec<u8> = gray.pixels()
            .map(|p| if p.0[0] as f32 > avg { 1 } else { 0 })
            .collect();
        
        // Convert to hex string
        let mut hasher = Sha256::new();
        hasher.update(&hash_bits);
        format!("{:x}", hasher.finalize())
    }
    
    fn get_from_cache(&self, key: &str) -> Option<CachedResult> {
        let mut cache = self.cache.lock();
        if let Some(cached) = cache.get(key) {
            if !cached.is_expired() {
                return Some(cached.clone());
            }
        }
        None
    }
    
    fn cache_result(&self, key: String, result: OCRResult, perceptual_hash: String) {
        let mut cache = self.cache.lock();
        cache.put(key, CachedResult {
            result,
            expires_at: Instant::now() + self.cache_ttl,
            perceptual_hash,
        });
    }
    
    fn calculate_region_variance(&self, gray: &ImageBuffer<image::Luma<u8>, Vec<u8>>,
                                 x: u32, y: u32, w: u32, h: u32) -> f32 {
        let mut sum = 0u64;
        let mut sum_sq = 0u64;
        let mut count = 0u64;
        
        for py in y..(y + h).min(gray.height()) {
            for px in x..(x + w).min(gray.width()) {
                let pixel = gray.get_pixel(px, py).0[0] as u64;
                sum += pixel;
                sum_sq += pixel * pixel;
                count += 1;
            }
        }
        
        if count == 0 {
            return 0.0;
        }
        
        let mean = sum as f32 / count as f32;
        let mean_sq = sum_sq as f32 / count as f32;
        mean_sq - (mean * mean)
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
                    
                    if self.are_adjacent(&current.bounds, &regions[j].bounds) {
                        current.bounds = self.combine_regions(&current.bounds, &regions[j].bounds);
                        current.confidence = (current.confidence + regions[j].confidence) / 2.0;
                        used[j] = true;
                        changed = true;
                    }
                }
            }
            
            merged.push(current);
        }
        
        merged
    }
    
    fn are_adjacent(&self, r1: &ScreenRegion, r2: &ScreenRegion) -> bool {
        let threshold = 20; // pixels
        
        let horizontal_overlap = !(r1.x + r1.width + threshold < r2.x || 
                                   r2.x + r2.width + threshold < r1.x);
        let vertical_overlap = !(r1.y + r1.height + threshold < r2.y || 
                                r2.y + r2.height + threshold < r1.y);
        
        horizontal_overlap && vertical_overlap
    }
    
    fn combine_regions(&self, r1: &ScreenRegion, r2: &ScreenRegion) -> ScreenRegion {
        let min_x = r1.x.min(r2.x);
        let min_y = r1.y.min(r2.y);
        let max_x = (r1.x + r1.width).max(r2.x + r2.width);
        let max_y = (r1.y + r1.height).max(r2.y + r2.height);
        
        ScreenRegion::new(min_x, min_y, max_x - min_x, max_y - min_y)
    }
}

impl Default for TesseractEngine {
    fn default() -> Self {
        Self::new().expect("Failed to initialize TesseractEngine")
    }
}

// Tests
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_screen_region_creation() {
        let region = ScreenRegion::new(10, 20, 100, 50);
        assert_eq!(region.x, 10);
        assert_eq!(region.y, 20);
        assert_eq!(region.width, 100);
        assert_eq!(region.height, 50);
        assert_eq!(region.area(), 5000);
        assert!(region.is_valid());
    }
    
    #[test]
    fn test_invalid_region() {
        let region = ScreenRegion::new(0, 0, 0, 0);
        assert!(!region.is_valid());
    }
    
    #[test]
    fn test_engine_initialization() {
        let engine = TesseractEngine::new();
        assert!(engine.is_ok());
    }
    
    #[test]
    fn test_confidence_threshold() {
        let mut engine = TesseractEngine::new().unwrap();
        engine.set_confidence_threshold(75.0);
        assert_eq!(engine.confidence_threshold, 75.0);
        
        // Test clamping
        engine.set_confidence_threshold(150.0);
        assert_eq!(engine.confidence_threshold, 100.0);
        
        engine.set_confidence_threshold(-10.0);
        assert_eq!(engine.confidence_threshold, 0.0);
    }
    
    #[tokio::test]
    async fn test_graceful_fallback_no_tesseract() {
        let mut engine = TesseractEngine::new().unwrap();
        engine.tesseract_available = false;
        
        let image = DynamicImage::new_rgb8(100, 100);
        let region = ScreenRegion::new(0, 0, 50, 50);
        
        let result = engine.process_region(&region, &image).await;
        assert!(result.is_err());
    }
}
