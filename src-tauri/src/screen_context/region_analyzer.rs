use anyhow::Result;
use image::DynamicImage;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};

use crate::screen_context::context_data::VisualData;
use crate::screen_context::ocr_tesseract::ScreenRegion;

/// Analyzes changes in specific screen regions for context detection
pub struct RegionAnalyzer {
    previous_regions: HashMap<String, RegionSnapshot>,
    change_threshold: f32,
    max_tracked_regions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionSnapshot {
    pub region: ScreenRegion,
    pub content_hash: String,
    pub last_change: std::time::SystemTime,
    pub change_frequency: f32,
    pub text_content: Option<String>,
    pub dominant_colors: Vec<(u8, u8, u8)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionChangeAnalysis {
    pub changed_regions: Vec<ChangedRegion>,
    pub new_regions: Vec<ScreenRegion>,
    pub removed_regions: Vec<String>,
    pub total_change_percentage: f32,
    pub most_active_region: Option<String>,
    pub timestamp: std::time::SystemTime,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChangedRegion {
    pub region_id: String,
    pub region: ScreenRegion,
    pub change_type: RegionChangeType,
    pub change_intensity: f32, // 0.0 to 1.0
    pub previous_content: Option<String>,
    pub current_content: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RegionChangeType {
    TextChanged,
    ColorChanged,
    SizeChanged,
    PositionChanged,
    ContentAppeared,
    ContentDisappeared,
    IntensiveActivity,
}

impl RegionAnalyzer {
    pub fn new() -> Self {
        Self {
            previous_regions: HashMap::new(),
            change_threshold: 0.1, // 10% change threshold
            max_tracked_regions: 20,
        }
    }
    
    pub fn with_change_threshold(mut self, threshold: f32) -> Self {
        self.change_threshold = threshold;
        self
    }
    
    pub fn with_max_regions(mut self, max_regions: usize) -> Self {
        self.max_tracked_regions = max_regions;
        self
    }
    
    /// Analyze screen regions for changes
    pub fn analyze_screen_changes(
        &mut self,
        current_screenshot: &DynamicImage,
        visual_data: Option<&VisualData>,
    ) -> Result<RegionChangeAnalysis> {
        let _start_time = Instant::now();
        
        // Define regions to analyze (can be expanded)
        let regions_to_analyze = self.get_analysis_regions(current_screenshot, visual_data);
        
        let mut changed_regions = Vec::new();
        let mut new_regions = Vec::new();
        let mut removed_regions = Vec::new();
        let mut total_change_pixels = 0u32;
        let mut total_pixels = 0u32;
        


        // Analyze each region
        for region in &regions_to_analyze {
            let region_id = self.generate_region_id(&region);
            
            if let Ok(region_snapshot) = self.capture_region_snapshot(current_screenshot, &region) {
                total_pixels += (region.width * region.height) as u32;
                
                if let Some(previous) = self.previous_regions.get(&region_id) {
                    // Compare with previous snapshot
                    let change_analysis = self.compare_regions(previous, &region_snapshot)?;
                    
                    if change_analysis.change_intensity > self.change_threshold {
                        changed_regions.push(ChangedRegion {
                            region_id: region_id.clone(),
                            region: region.clone(),
                            change_type: change_analysis.change_type,
                            change_intensity: change_analysis.change_intensity,
                            previous_content: previous.text_content.clone(),
                            current_content: region_snapshot.text_content.clone(),
                        });
                        
                        total_change_pixels += (change_analysis.change_intensity * (region.width * region.height) as f32) as u32;
                    }
                } else {
                    // New region
                    new_regions.push(region.clone());
                    total_change_pixels += (region.width * region.height) as u32;
                }
                
                // Update the snapshot
                self.previous_regions.insert(region_id, region_snapshot);
            }
        }
        
        // Find removed regions (regions that were tracked but no longer present)
        let current_region_ids: std::collections::HashSet<String> = 
            regions_to_analyze.iter().map(|r| self.generate_region_id(r)).collect();
        
        let mut regions_to_remove = Vec::new();
        for (region_id, _) in &self.previous_regions {
            if !current_region_ids.contains(region_id) {
                removed_regions.push(region_id.clone());
                regions_to_remove.push(region_id.clone());
            }
        }
        
        // Clean up removed regions
        for region_id in regions_to_remove {
            self.previous_regions.remove(&region_id);
        }
        
        // Limit the number of tracked regions
        if self.previous_regions.len() > self.max_tracked_regions {
            self.cleanup_old_regions();
        }
        
        // Calculate total change percentage
        let total_change_percentage = if total_pixels > 0 {
            (total_change_pixels as f32 / total_pixels as f32) * 100.0
        } else {
            0.0
        };
        
        // Find most active region
        let most_active_region = changed_regions
            .iter()
            .max_by(|a, b| a.change_intensity.partial_cmp(&b.change_intensity).unwrap())
            .map(|cr| cr.region_id.clone());
        
        Ok(RegionChangeAnalysis {
            changed_regions,
            new_regions,
            removed_regions,
            total_change_percentage,
            most_active_region,
            timestamp: std::time::SystemTime::now(),
        })
    }


    
    /// Get regions to analyze based on screenshot and visual data
    fn get_analysis_regions(
        &self,
        screenshot: &DynamicImage,
        visual_data: Option<&VisualData>,
    ) -> Vec<ScreenRegion> {
        let mut regions = Vec::new();
        
        let width = screenshot.width();
        let height = screenshot.height();
        
        // Always analyze these key regions
        regions.extend(vec![
            // Top bar (menu/title area)
            ScreenRegion {
                x: 0,
                y: 0,
                width: width,
                height: height / 10,
            },
            // Center area (main content)
            ScreenRegion {
                x: width / 8,
                y: height / 4,
                width: (width * 3) / 4,
                height: height / 2,
            },
            // Bottom area (dock/status)
            ScreenRegion {
                x: 0,
                y: (height * 9) / 10,
                width: width,
                height: height / 10,
            },
            // Left sidebar
            ScreenRegion {
                x: 0,
                y: height / 4,
                width: width / 8,
                height: height / 2,
            },
            // Right sidebar
            ScreenRegion {
                x: (width * 7) / 8,
                y: height / 4,
                width: width / 8,
                height: height / 2,
            },
        ]);
        
        // Add regions from visual data if available
        if let Some(visual) = visual_data {
            // Add text regions
            for text_region in &visual.text_regions {
                if self.is_significant_region(text_region) {
                    regions.push(text_region.clone());
                }
            }
            
            // Add changed regions from previous analysis
            for changed_region in &visual.changed_regions {
                if self.is_significant_region(changed_region) {
                    regions.push(changed_region.clone());
                }
            }
        }
        
        // Remove overlapping regions and limit count
        self.deduplicate_regions(regions)
    }
    
    /// Check if a region is significant enough to track
    fn is_significant_region(&self, region: &ScreenRegion) -> bool {
        let area = region.width * region.height;
        // Minimum 100x100 pixels, maximum 1/4 of screen
        area >= 10000 && area <= 1920 * 1080 / 4
    }
    
    /// Remove overlapping and duplicate regions
    fn deduplicate_regions(&self, mut regions: Vec<ScreenRegion>) -> Vec<ScreenRegion> {
        regions.sort_by(|a, b| {
            let area_a = a.width * a.height;
            let area_b = b.width * b.height;
            area_b.cmp(&area_a) // Sort by area, largest first
        });
        
        let mut deduplicated = Vec::new();
        
        for region in regions {
            let mut is_duplicate = false;
            
            for existing in &deduplicated {
                if self.regions_overlap(&region, existing, 0.5) {
                    is_duplicate = true;
                    break;
                }
            }
            
            if !is_duplicate && deduplicated.len() < self.max_tracked_regions {
                deduplicated.push(region);
            }
        }
        
        deduplicated
    }
    
    /// Check if two regions overlap significantly
    fn regions_overlap(&self, region1: &ScreenRegion, region2: &ScreenRegion, threshold: f32) -> bool {
        // Use saturating_sub to avoid overflow when regions don't overlap
        let x_overlap = std::cmp::min(region1.x + region1.width, region2.x + region2.width)
            .saturating_sub(std::cmp::max(region1.x, region2.x));
        let y_overlap = std::cmp::min(region1.y + region1.height, region2.y + region2.height)
            .saturating_sub(std::cmp::max(region1.y, region2.y));

        let overlap_area = x_overlap * y_overlap;
        let total_area = std::cmp::min(region1.width * region1.height, region2.width * region2.height);

        if total_area == 0 {
            return false;
        }

        (overlap_area as f32 / total_area as f32) > threshold
    }
    
    /// Capture a snapshot of a specific region
    fn capture_region_snapshot(
        &self,
        screenshot: &DynamicImage,
        region: &ScreenRegion,
    ) -> Result<RegionSnapshot> {
        // Extract the region from the screenshot
        let region_image = screenshot.crop_imm(
            region.x,
            region.y,
            region.width,
            region.height,
        );
        
        // Calculate content hash (simple approach)
        let content_hash = self.calculate_image_hash(&region_image);
        
        // Extract dominant colors
        let dominant_colors = self.extract_dominant_colors(&region_image);
        
        Ok(RegionSnapshot {
            region: region.clone(),
            content_hash,
            last_change: std::time::SystemTime::now(),
            change_frequency: 0.0,
            text_content: None, // Could be enhanced with OCR
            dominant_colors,
        })
    }
    
    /// Compare two region snapshots
    fn compare_regions(&self, previous: &RegionSnapshot, current: &RegionSnapshot) -> Result<RegionChangeComparison> {
        // Hash comparison
        let hash_different = previous.content_hash != current.content_hash;
        
        // Color comparison
        let color_similarity = self.compare_color_palettes(&previous.dominant_colors, &current.dominant_colors);
        
        // Determine change type and intensity
        let (change_type, change_intensity) = if !hash_different {
            (RegionChangeType::TextChanged, 0.0)
        } else if color_similarity < 0.7 {
            (RegionChangeType::ColorChanged, 1.0 - color_similarity)
        } else {
            (RegionChangeType::TextChanged, 0.5)
        };
        
        Ok(RegionChangeComparison {
            change_type,
            change_intensity,
        })
    }
    
    /// Calculate a simple hash for an image
    fn calculate_image_hash(&self, image: &DynamicImage) -> String {
        // Simple hash based on average color and structure
        let rgb_image = image.to_rgb8();
        let (width, height) = rgb_image.dimensions();
        
        let mut hash_components = Vec::new();
        
        // Sample colors from a grid
        let grid_size = 8;
        for y in 0..grid_size {
            for x in 0..grid_size {
                let sample_x = (x * width) / grid_size;
                let sample_y = (y * height) / grid_size;
                
                if sample_x < width && sample_y < height {
                    let pixel = rgb_image.get_pixel(sample_x, sample_y);
                    hash_components.push(format!("{:02x}{:02x}{:02x}", pixel[0], pixel[1], pixel[2]));
                }
            }
        }
        
        hash_components.join("")
    }
    
    /// Extract dominant colors from an image
    fn extract_dominant_colors(&self, image: &DynamicImage) -> Vec<(u8, u8, u8)> {
        let rgb_image = image.to_rgb8();
        let mut color_counts: HashMap<(u8, u8, u8), u32> = HashMap::new();
        
        // Sample pixels and count colors (quantized to reduce noise)
        for pixel in rgb_image.pixels() {
            let quantized = (
                (pixel[0] / 32) * 32, // Quantize to reduce color space
                (pixel[1] / 32) * 32,
                (pixel[2] / 32) * 32,
            );
            *color_counts.entry(quantized).or_insert(0) += 1;
        }
        
        // Get top 5 most common colors
        let mut colors: Vec<_> = color_counts.into_iter().collect();
        colors.sort_by(|a, b| b.1.cmp(&a.1));
        colors.into_iter().take(5).map(|(color, _)| color).collect()
    }
    
    /// Compare color palettes
    fn compare_color_palettes(&self, colors1: &[(u8, u8, u8)], colors2: &[(u8, u8, u8)]) -> f32 {
        if colors1.is_empty() && colors2.is_empty() {
            return 1.0;
        }
        
        if colors1.is_empty() || colors2.is_empty() {
            return 0.0;
        }
        
        // Simple intersection-based similarity
        let set1: std::collections::HashSet<_> = colors1.iter().collect();
        let set2: std::collections::HashSet<_> = colors2.iter().collect();
        
        let intersection = set1.intersection(&set2).count();
        let union = set1.union(&set2).count();
        
        if union == 0 {
            1.0
        } else {
            intersection as f32 / union as f32
        }
    }
    
    /// Generate a unique ID for a region
    fn generate_region_id(&self, region: &ScreenRegion) -> String {
        format!("{}_{}_{}_{}", region.x, region.y, region.width, region.height)
    }
    
    /// Clean up old regions that haven't changed recently
    fn cleanup_old_regions(&mut self) {
        let cutoff_time = std::time::SystemTime::now() - Duration::from_secs(300); // 5 minutes
        
        let region_ids_to_remove: Vec<String> = self.previous_regions
            .iter()
            .filter(|(_, snapshot)| snapshot.last_change < cutoff_time)
            .map(|(id, _)| id.clone())
            .collect();
        
        for region_id in region_ids_to_remove {
            self.previous_regions.remove(&region_id);
        }
    }
    
    /// Get statistics about tracked regions
    pub fn get_region_stats(&self) -> RegionAnalyzerStats {
        RegionAnalyzerStats {
            tracked_regions: self.previous_regions.len(),
            max_regions: self.max_tracked_regions,
            change_threshold: self.change_threshold,
        }
    }
    
    /// Clear all tracked regions
    pub fn clear_regions(&mut self) {
        self.previous_regions.clear();
    }
}

#[derive(Debug, Clone)]
struct RegionChangeComparison {
    pub change_type: RegionChangeType,
    pub change_intensity: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionAnalyzerStats {
    pub tracked_regions: usize,
    pub max_regions: usize,
    pub change_threshold: f32,
}

impl Default for RegionAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::{ImageBuffer, Rgb};
    
    #[test]
    fn test_region_analyzer_creation() {
        let analyzer = RegionAnalyzer::new();
        assert_eq!(analyzer.max_tracked_regions, 20);
        assert_eq!(analyzer.change_threshold, 0.1);
    }
    
    #[test]
    fn test_region_id_generation() {
        let analyzer = RegionAnalyzer::new();
        let region = ScreenRegion {
            x: 10,
            y: 20,
            width: 100,
            height: 200,
        };
        
        let id = analyzer.generate_region_id(&region);
        assert_eq!(id, "10_20_100_200");
    }
    
    #[test]
    fn test_region_overlap_detection() {
        let analyzer = RegionAnalyzer::new();
        
        let region1 = ScreenRegion { x: 0, y: 0, width: 100, height: 100 };
        let region2 = ScreenRegion { x: 50, y: 50, width: 100, height: 100 };
        let region3 = ScreenRegion { x: 200, y: 200, width: 100, height: 100 };
        
        assert!(analyzer.regions_overlap(&region1, &region2, 0.2));
        assert!(!analyzer.regions_overlap(&region1, &region3, 0.2));
    }
    
    #[test]
    fn test_significant_region_check() {
        let analyzer = RegionAnalyzer::new();
        
        let small_region = ScreenRegion { x: 0, y: 0, width: 50, height: 50 };
        let good_region = ScreenRegion { x: 0, y: 0, width: 200, height: 200 };
        let huge_region = ScreenRegion { x: 0, y: 0, width: 5000, height: 5000 };
        
        assert!(!analyzer.is_significant_region(&small_region));
        assert!(analyzer.is_significant_region(&good_region));
        assert!(!analyzer.is_significant_region(&huge_region));
    }
    
    #[test]
    fn test_color_palette_comparison() {
        let analyzer = RegionAnalyzer::new();
        
        let colors1 = vec![(255, 0, 0), (0, 255, 0), (0, 0, 255)];
        let colors2 = vec![(255, 0, 0), (0, 255, 0), (0, 0, 255)];
        let colors3 = vec![(128, 128, 128), (64, 64, 64)];
        
        assert_eq!(analyzer.compare_color_palettes(&colors1, &colors2), 1.0);
        assert!(analyzer.compare_color_palettes(&colors1, &colors3) < 0.5);
        assert_eq!(analyzer.compare_color_palettes(&[], &[]), 1.0);
        assert_eq!(analyzer.compare_color_palettes(&colors1, &[]), 0.0);
    }
}