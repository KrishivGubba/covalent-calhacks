use core_graphics::event::{
    CGEvent, CGEventTap, CGEventTapLocation, CGEventTapOptions, CGEventTapPlacement,
    CGEventTapProxy, CGEventType, EventField, EventMask, EventRef,
};
use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
use core_graphics::geometry::CGPoint;
use objc::rc::autoreleasepool;
use std::sync::mpsc::{channel, Sender};
use std::thread;
use std::time::Instant;

use super::super::activity_monitor::{ActivityEvent, ActivityEventType};

pub struct ActivityMonitor {
    event_sender: Sender<ActivityEvent>,
}

impl ActivityMonitor {
    pub fn new() -> anyhow::Result<Self> {
        let (tx, rx) = channel();
        
        // Start the event tap in a separate thread
        thread::spawn(move || {
            if let Err(e) = Self::run_event_tap(rx) {
                eprintln!("Error in event tap: {}", e);
            }
        });

        Ok(Self { event_sender: tx })
    }

    fn run_event_tap(rx: std::sync::mpsc::Receiver<()>) -> anyhow::Result<()> {
        // Create an event tap for keyboard and mouse events
        let event_tap = CGEventTap::new(
            CGEventTapLocation::HID, // Listen at the HID level
            CGEventTapPlacement::HeadInsertEventTap,
            CGEventTapOptions::Default,
            EventMask::ALL,
            |_proxy, event_type, event| {
                autoreleasepool(|| {
                    match event_type {
                        CGEventType::KeyDown | CGEventType::KeyUp => {
                            // Handle keyboard events
                            if event_type == CGEventType::KeyDown {
                                // You can get the key code if needed
                                // let keycode = event.get_integer_value_field(EventField::KEYBOARD_EVENT_KEYCODE);
                                let event = ActivityEvent {
                                    timestamp: Instant::now(),
                                    event_type: ActivityEventType::KeyPressed,
                                };
                                // Send the event through the channel
                                if let Err(e) = SELF.event_sender.send(event) {
                                    eprintln!("Error sending key event: {}", e);
                                }
                            }
                        }
                        CGEventType::LeftMouseDown | CGEventType::RightMouseDown | CGEventType::OtherMouseDown => {
                            // Handle mouse clicks
                            let location = event.location();
                            let event = ActivityEvent {
                                timestamp: Instant::now(),
                                event_type: ActivityEventType::MouseClicked {
                                    x: location.x,
                                    y: location.y,
                                },
                            };
                            if let Err(e) = SELF.event_sender.send(event) {
                                eprintln!("Error sending mouse click event: {}", e);
                            }
                        }
                        CGEventType::MouseMoved | CGEventType::LeftMouseDragged | CGEventType::RightMouseDragged => {
                            // Handle mouse movement
                            let location = event.location();
                            let event = ActivityEvent {
                                timestamp: Instant::now(),
                                event_type: ActivityEventType::MouseMoved {
                                    x: location.x,
                                    y: location.y,
                                },
                            };
                            if let Err(e) = SELF.event_sender.send(event) {
                                eprintln!("Error sending mouse move event: {}", e);
                            }
                        }
                        CGEventType::ScrollWheel => {
                            // Handle scroll events
                            let delta_x = event.get_integer_value_field(EventField::SCROLL_WHEEL_EVENT_POINT_DELTA_AXIS_1);
                            let delta_y = event.get_integer_value_field(EventField::SCROLL_WHEEL_EVENT_POINT_DELTA_AXIS_2);
                            
                            if delta_x != 0 || delta_y != 0 {
                                let event = ActivityEvent {
                                    timestamp: Instant::now(),
                                    event_type: ActivityEventType::ScrollEvent {
                                        delta_x: delta_x as f64,
                                        delta_y: delta_y as f64,
                                    },
                                };
                                if let Err(e) = SELF.event_sender.send(event) {
                                    eprintln!("Error sending scroll event: {}", e);
                                }
                            }
                        }
                        _ => {}
                    }
                });
                event
            },
        )?;

        // Create a run loop source for the event tap
        let source = event_tap.create_source();
        let run_loop = CFRunLoop::get_current();
        source.add_to_run_loop(run_loop, kCFRunLoopCommonModes);
        event_tap.enable();

        // Start the run loop
        CFRunLoop::run_current();

        Ok(())
    }

    pub fn get_activity_receiver(&self) -> std::sync::mpsc::Receiver<ActivityEvent> {
        self.event_sender.subscribe()
    }
}

// Helper function to get the current frontmost application
fn get_frontmost_application() -> Option<String> {
    use core_foundation::string::CFString;
    use core_foundation::dictionary::CFDictionary;
    use core_foundation::string::CFStringRef;
    use core_foundation::base::TCFType;
    
    unsafe {
        let workspace = objc::msg_send![class!(NSWorkspace), sharedWorkspace];
        let front_app: *mut Object = msg_send![workspace, frontmostApplication];
        
        if front_app.is_null() {
            return None;
        }
        
        let app_name: *mut Object = msg_send![front_app, localizedName];
        let app_name = CFString::wrap_under_create_rule(app_name as CFStringRef);
        
        Some(app_name.to_string())
    }
}
