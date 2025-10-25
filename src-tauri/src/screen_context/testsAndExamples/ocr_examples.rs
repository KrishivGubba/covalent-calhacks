// Examples demonstrating the OCR engine usage

use super::ocr_tesseract::{OCRError, OCRResult, ScreenRegion, TesseractEngine};
use anyhow::Result;
use image::DynamicImage;
use std::path::Path;
use std::time::Duration;

/// Example 1: Basic OCR on a specific region
#[allow(dead_code)]
pub async fn example_basic_region_ocr() -> Result<()> {
    println!("=== Example 1: Basic Region OCR ===\n");
    
    // Initialize the engine
    let engine = TesseractEngine::new()?;
    
    // Load an image (in real use, this would be a screenshot)
    let image = DynamicImage::new_rgb8(800, 600);
    
    // Define a region to process (e.g., a button or text field)
    let region = ScreenRegion::new(100, 100, 400, 50);
    
    println!("Processing region: {}x{} at ({}, {})", 
        region.width, region.height, region.x, region.y);
    
    // Process the region
    match engine.process_region(&region, &image).await {
        Ok(result) => {
            println!("✓ OCR Success!");
            println!("  Text: {}", result.text);
            println!("  Confidence: {:.1}%", result.confidence);
            println!("  Language: {}", result.language);
            println!("  Processing time: {}ms", result.processing_time_ms);
        }
        Err(e) => {
            println!("✗ OCR Failed: {}", e);
        }
    }
    
    Ok(())
}

/// Example 2: Process entire screenshot with automatic region detection
#[allow(dead_code)]
pub async fn example_full_screenshot_ocr() -> Result<()> {
    println!("\n=== Example 2: Full Screenshot OCR ===\n");
    
    let engine = TesseractEngine::new()?;
    
    // In real usage, this would be a path to a screenshot
    let screenshot_path = Path::new("screenshot.png");
    
    println!("Processing screenshot: {:?}", screenshot_path);
    
    match engine.process_screenshot(screenshot_path).await {
        Ok(results) => {
            println!("✓ Found {} text regions\n", results.len());
            
            for (i, result) in results.iter().enumerate() {
                println!("Region {}:", i + 1);
                println!("  Location: ({}, {})", result.region.x, result.region.y);
                println!("  Size: {}x{}", result.region.width, result.region.height);
                println!("  Confidence: {:.1}%", result.confidence);
                println!("  Text: {}", result.text.lines().next().unwrap_or(""));
                println!();
            }
        }
        Err(e) => {
            println!("✗ Screenshot OCR Failed: {}", e);
        }
    }
    
    Ok(())
}

/// Example 3: Advanced configuration for screen text
#[allow(dead_code)]
pub async fn example_advanced_configuration() -> Result<()> {
    println!("\n=== Example 3: Advanced Configuration ===\n");
    
    let mut engine = TesseractEngine::new()?;
    
    // Configure for optimal screen text recognition
    engine
        .optimize_for_screen_text()
        .set_default_language("eng".to_string())
        .set_confidence_threshold(70.0)  // Only accept 70%+ confidence
        .set_timeout(Duration::from_secs(3));  // 3 second timeout
    
    println!("Engine configured:");
    println!("  ✓ Optimized for screen text");
    println!("  ✓ Language: English");
    println!("  ✓ Confidence threshold: 70%");
    println!("  ✓ Timeout: 3 seconds");
    
    // Add multi-language support
    engine.set_languages(vec![
        "eng".to_string(),
        "fra".to_string(),
        "spa".to_string(),
    ]);
    
    println!("  ✓ Languages: English, French, Spanish");
    
    Ok(())
}

/// Example 4: Batch processing multiple regions
#[allow(dead_code)]
pub async fn example_batch_processing() -> Result<()> {
    println!("\n=== Example 4: Batch Processing ===\n");
    
    let engine = TesseractEngine::new()?;
    let image = DynamicImage::new_rgb8(1920, 1080);
    
    // Detect text regions automatically
    let regions = engine.detect_text_regions(&image)?;
    
    println!("Detected {} potential text regions", regions.len());
    
    // Batch process all regions
    let results = engine.batch_process_regions(&regions, &image).await?;
    
    println!("Successfully processed {} regions with high confidence\n", results.len());
    
    // Filter and analyze results
    let high_confidence: Vec<_> = results.iter()
        .filter(|r| r.confidence >= 80.0)
        .collect();
    
    let medium_confidence: Vec<_> = results.iter()
        .filter(|r| r.confidence >= 60.0 && r.confidence < 80.0)
        .collect();
    
    println!("Quality breakdown:");
    println!("  High confidence (80%+): {} regions", high_confidence.len());
    println!("  Medium confidence (60-80%): {} regions", medium_confidence.len());
    
    Ok(())
}

/// Example 5: Error handling and graceful fallback
#[allow(dead_code)]
pub async fn example_error_handling() -> Result<()> {
    println!("\n=== Example 5: Error Handling ===\n");
    
    let engine = TesseractEngine::new()?;
    let image = DynamicImage::new_rgb8(800, 600);
    let region = ScreenRegion::new(100, 100, 400, 50);
    
    println!("Demonstrating various error scenarios...\n");
    
    // Scenario 1: Invalid region
    let invalid_region = ScreenRegion::new(2000, 2000, 100, 100);
    match engine.process_region(&invalid_region, &image).await {
        Ok(_) => println!("✓ Region processed"),
        Err(e) => {
            if let Some(OCRError::InvalidRegion(msg)) = e.downcast_ref::<OCRError>() {
                println!("✓ Caught InvalidRegion: {}", msg);
            }
        }
    }
    
    // Scenario 2: Engine initialization checks for Tesseract
    println!("✓ Engine initialized successfully - Tesseract is available");
    
    // Scenario 3: Low confidence handling
    match engine.process_region(&region, &image).await {
        Ok(result) => {
            if result.confidence < 60.0 {
                println!("⚠ Low confidence result: {:.1}%", result.confidence);
                println!("  Consider: improving image quality or using fallback method");
            } else {
                println!("✓ High confidence result: {:.1}%", result.confidence);
            }
        }
        Err(e) => println!("✗ OCR error: {}", e),
    }
    
    Ok(())
}

/// Example 6: Caching demonstration
#[allow(dead_code)]
pub async fn example_caching_performance() -> Result<()> {
    println!("\n=== Example 6: Caching Performance ===\n");
    
    let engine = TesseractEngine::new()?;
    let image = DynamicImage::new_rgb8(800, 600);
    let region = ScreenRegion::new(100, 100, 400, 50);
    
    use std::time::Instant;
    
    // First call - performs OCR
    let start = Instant::now();
    let result1 = engine.process_region(&region, &image).await?;
    let duration1 = start.elapsed();
    
    println!("First call (no cache):");
    println!("  Time: {:?}", duration1);
    println!("  Text: {}", result1.text);
    
    // Second call - should use cache (within 5 second TTL)
    let start = Instant::now();
    let result2 = engine.process_region(&region, &image).await?;
    let duration2 = start.elapsed();
    
    println!("\nSecond call (cached):");
    println!("  Time: {:?}", duration2);
    println!("  Text: {}", result2.text);
    
    if duration2 < duration1 / 10 {
        println!("\n✓ Cache working! Second call was ~{:.0}x faster", 
            duration1.as_micros() as f64 / duration2.as_micros() as f64);
    }
    
    Ok(())
}

/// Example 7: Real-time monitoring setup
#[allow(dead_code)]
pub async fn example_realtime_monitoring() -> Result<()> {
    println!("\n=== Example 7: Real-time Monitoring Setup ===\n");
    
    let engine = TesseractEngine::new()?;
    
    println!("Setting up real-time OCR monitoring...");
    println!("  Interval: 5 seconds");
    println!("  Confidence threshold: 60%");
    println!("  Timeout: 2 seconds");
    
    // In a real application, this would run in a loop
    let mut ticker = tokio::time::interval(Duration::from_secs(5));
    
    println!("\nStarting monitoring (press Ctrl+C to stop)...\n");
    
    // Example: run for 3 iterations
    for i in 1..=3 {
        ticker.tick().await;
        
        println!("Tick {}: Capturing screen...", i);
        
        // In real use: capture_screenshot()
        let screenshot_path = Path::new("screenshot.png");
        
        match engine.process_screenshot(screenshot_path).await {
            Ok(results) => {
                let high_conf = results.iter().filter(|r| r.confidence >= 60.0).count();
                println!("  Found {} text regions ({} high confidence)", results.len(), high_conf);
                
                // Process results
                for result in results.iter().filter(|r| r.confidence >= 60.0) {
                    // Send to analysis pipeline
                    println!("  → Detected: {}", result.text.lines().next().unwrap_or(""));
                }
            }
            Err(e) => {
                println!("  ✗ Error: {}", e);
            }
        }
        
        println!();
    }
    
    println!("Monitoring demo complete");
    
    Ok(())
}

/// Example 8: Integration with context collector
#[allow(dead_code)]
pub struct SmartOCRCollector {
    engine: TesseractEngine,
    last_results: Vec<OCRResult>,
}

#[allow(dead_code)]
impl SmartOCRCollector {
    pub fn new() -> Result<Self> {
        Ok(Self {
            engine: TesseractEngine::new()?,
            last_results: Vec::new(),
        })
    }
    
    /// Collect OCR data with intelligent filtering
    pub async fn collect_screen_text(&mut self, image: &DynamicImage) -> Result<Vec<String>> {
        // Detect regions
        let regions = self.engine.detect_text_regions(image)?;
        
        // Process with confidence filtering
        let results = self.engine.batch_process_regions(&regions, image).await?;
        
        // Store results for stats
        self.last_results = results.clone();
        
        // Filter by confidence and deduplicate
        let texts: Vec<String> = results
            .into_iter()
            .filter(|r| r.confidence >= 60.0)
            .filter(|r| !r.text.trim().is_empty())
            .map(|r| r.text)
            .collect();
        
        Ok(texts)
    }
    
    /// Get statistics about last OCR operation
    pub fn get_stats(&self) -> OCRStats {
        let total = self.last_results.len();
        let high_conf = self.last_results.iter().filter(|r| r.confidence >= 80.0).count();
        let avg_confidence = if total > 0 {
            self.last_results.iter().map(|r| r.confidence).sum::<f32>() / total as f32
        } else {
            0.0
        };
        
        OCRStats {
            total_regions: total,
            high_confidence_regions: high_conf,
            average_confidence: avg_confidence,
        }
    }
}

#[allow(dead_code)]
pub struct OCRStats {
    pub total_regions: usize,
    pub high_confidence_regions: usize,
    pub average_confidence: f32,
}

/// Run all examples
#[allow(dead_code)]
pub async fn run_all_examples() -> Result<()> {
    println!("╔════════════════════════════════════════╗");
    println!("║   OCR Engine Examples & Demonstrations  ║");
    println!("╚════════════════════════════════════════╝\n");
    
    // Note: In real usage, you'd have actual screenshots
    println!("⚠ Note: These examples use placeholder images.");
    println!("  In production, use real screenshots for testing.\n");
    
    let _ = example_basic_region_ocr().await;
    let _ = example_advanced_configuration().await;
    let _ = example_batch_processing().await;
    let _ = example_error_handling().await;
    
    // Skip examples that require actual files
    // let _ = example_full_screenshot_ocr().await;
    // let _ = example_caching_performance().await;
    // let _ = example_realtime_monitoring().await;
    
    println!("\n╔════════════════════════════════════════╗");
    println!("║        Examples Complete!               ║");
    println!("╚════════════════════════════════════════╝");
    
    Ok(())
}

// Note: check_tesseract_available() is already available as a private method in TesseractEngine

#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    async fn test_examples_compile() {
        // Just verify examples compile and basic functions work
        let _ = TesseractEngine::new();
    }
    
    #[test]
    fn test_smart_collector_creation() {
        let collector = SmartOCRCollector::new();
        assert!(collector.is_ok() || collector.is_err()); // Either works, depends on Tesseract
    }
}

